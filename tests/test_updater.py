# -*- coding: utf-8 -*-
"""Self-update logic without the network or a real install: python tests/test_updater.py"""
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import updater as up  # noqa: E402


class Resp(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def release(tag, assets=("Yobi-Setup.zip",), **kw):
    rel = {"tag_name": tag, "assets": [{"name": n, "browser_download_url": f"https://x/{n}"} for n in assets]}
    rel.update(kw)
    return Resp(json.dumps(rel).encode())


class TestVersions(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(up.newer("v1.0.1", "1.0.0"))
        self.assertTrue(up.newer("1.10.0", "1.9.9"))          # numbers, not text
        self.assertFalse(up.newer("v1.0.0", "1.0.0"))
        self.assertFalse(up.newer("v0.9.9", "1.0.0"))
        self.assertFalse(up.newer("latest", "1.0.0"))
        self.assertFalse(up.newer(None, "1.0.0"))
        self.assertIsNotNone(up.parse(up.VERSION))

    def test_only_an_installed_yobi_checks(self):
        with tempfile.TemporaryDirectory() as d:
            app = os.path.join(d, "app")
            os.makedirs(os.path.join(d, "runtime"))
            os.makedirs(app)
            self.assertIsNone(up.install_dir(app))            # no python.exe yet
            open(os.path.join(d, "runtime", "python.exe"), "w").close()
            self.assertEqual(up.install_dir(app), d)
            self.assertIsNone(up.install_dir(os.path.join(d, "files")))
        self.assertIsNone(up.install_dir())                   # this source folder


class TestLatest(unittest.TestCase):
    def test_newer_release_with_the_zip(self):
        with mock.patch("urllib.request.urlopen", return_value=release("v1.2.0")):
            self.assertEqual(up.latest("1.0.0"), ("1.2.0", "https://x/Yobi-Setup.zip"))

    def test_nothing_to_offer(self):
        for rel in (release("v1.0.0"), release("v2.0.0", assets=("other.zip",)),
                    release("v2.0.0", draft=True), release("v2.0.0", prerelease=True)):
            with mock.patch("urllib.request.urlopen", return_value=rel):
                self.assertIsNone(up.latest("1.0.0"))


class TestDownload(unittest.TestCase):
    def test_progress_and_cut_off(self):
        with tempfile.TemporaryDirectory() as d:
            seen = []
            with mock.patch("urllib.request.urlopen", return_value=Resp(b"x" * (3 << 20))):
                up.download("https://x/z", os.path.join(d, "z"), seen.append)
            self.assertEqual((seen[-1], os.path.getsize(os.path.join(d, "z"))), (100, 3 << 20))
            with mock.patch("urllib.request.urlopen", return_value=Resp(b"x" * 10, length=99)):
                with self.assertRaises(IOError):
                    up.download("https://x/z", os.path.join(d, "z"))


class TestInstall(unittest.TestCase):
    def make_zip(self, d):
        z = os.path.join(d, "Yobi-Setup-9.9.9.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("Yobi/Install Yobi.cmd", "")
            f.writestr("Yobi/payload/app/install.ps1", "# new")
        return z

    def test_runs_the_new_installer(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"LOCALAPPDATA": d}), \
                mock.patch.object(up.tempfile, "tempdir", d), mock.patch("subprocess.Popen") as popen:
            z = self.make_zip(d)
            up.run_installer(z, os.path.join(d, "Programs", "Yobi"))
            args = popen.call_args[0][0]
            self.assertTrue(args[args.index("-File") + 1].endswith(os.path.join("payload", "app", "install.ps1")))
            self.assertIn("-Silent", args)
            self.assertNotIn("-Dest", args)                    # the normal place: a normal install
            self.assertNotIn("-NoLaunch", args)
            up.run_installer(z, os.path.join(d, "Other"), launch=False)
            args = popen.call_args[0][0]
            self.assertEqual(args[args.index("-Dest") + 1], os.path.join(d, "Other"))
            self.assertIn("-NoLaunch", args)
            # the next start clears what the update left, and knows it just updated
            self.assertTrue(up.cleanup(d))
            self.assertEqual([n for n in os.listdir(d) if n.startswith(("yobi-update-", "Yobi-Setup-"))], [])
            self.assertFalse(up.cleanup(d))

    def test_broken_zip(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(up.tempfile, "tempdir", d), \
                mock.patch("subprocess.Popen") as popen:
            z = os.path.join(d, "bad.zip")
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("Yobi/readme.txt", "")
            with self.assertRaises(IOError):
                up.run_installer(z, d)
            popen.assert_not_called()


class Island:
    def __init__(self):
        self.shown, self.asked = [], []

    def after(self, ms, fn=None, *a):
        fn()

    def set_state(self, state, text=""):
        self.shown.append((state, text))

    def ask(self, q, options, cb, timeout_ms=0):
        self.asked.append((q, cb))

    def say(self, text, state=None):
        self.shown.append((state, text))

    def is_free(self):
        return True


class TestWatch(unittest.TestCase):
    def test_asks_then_updates_on_yes(self):
        isl = Island()
        with mock.patch.object(up, "install_dir", return_value="C:/Y"), mock.patch.object(up, "cleanup", return_value=False), \
                mock.patch.object(up, "latest", return_value=("9.9.9", "https://x/z")), \
                mock.patch.object(up, "download") as dl, mock.patch.object(up, "run_installer") as inst, \
                mock.patch.object(up.threading, "Thread") as th:
            up.watch(isl, log=lambda m: None, delay=0)
            self.assertIn("9.9.9", isl.asked[0][0])
            isl.asked[0][1]("later")
            th.assert_not_called()
            isl.asked[0][1]("update")
            kw = th.call_args.kwargs
            kw["target"](*kw["args"])                          # run the update thread here
            dl.assert_called_once()
            inst.assert_called_once()
            self.assertEqual(isl.shown[-1][0], "info")

    def test_source_folder_never_checks(self):
        with mock.patch.object(up, "latest") as latest:
            up.watch(Island(), delay=0)
            latest.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=1)
