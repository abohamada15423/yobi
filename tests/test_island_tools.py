# -*- coding: utf-8 -*-
"""Island tools logic on temp folders: python tests/test_island_tools.py"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import island_tools as it  # noqa: E402


def make(tmp):
    sent = []
    with mock.patch.object(it, "CONFIG_PATH", os.path.join(tmp, "config.json")), \
            mock.patch.object(it, "SHELF_PATH", os.path.join(tmp, "shelf.json")):
        t = it.IslandTools(sent.append)
    return t, sent


class TestSettings(unittest.TestCase):
    def test_wake_key_from_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"hotkey": "ctrl+alt+j"}, f)          # the old top-level key still counts
            t, sent = make(tmp)
            self.assertEqual(t.cfg["wake_key"], "ctrl+alt+j")
            got = []
            t.on_wake_key = got.append
            with mock.patch.object(it, "CONFIG_PATH", path):
                t._apply_settings("island", {"wake_key": "f8"})
                t._apply_settings("island", {"wake_key": "ctrl"})   # refused
            self.assertEqual((got, t.cfg["wake_key"]), (["f8"], "f8"))
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["island"]["wake_key"], "f8")
            self.assertEqual(make(tmp)[0].cfg["wake_key"], "f8")

    def test_only_valid_values_pass(self):
        self.assertEqual(it.clean_settings("island", {"theme": "night", "downloads": False, "x": 1}),
                         {"theme": "night", "downloads": False})
        self.assertEqual(it.clean_settings("island", {"theme": "hacker", "downloads": "yes"}), {})
        d = it.clean_settings("daily", {"focus_min": 999, "break_min": 0, "method": "EGYPT", "asr": "maliki",
                                        "lat": 30.04, "lon": 200, "quiet_hours": "23:00-07:00"})
        self.assertEqual(d, {"focus_min": 120, "break_min": 1, "method": "EGYPT", "lat": 30.04,
                             "quiet_hours": "23:00-07:00"})

    def test_calendar_link_must_be_https(self):
        self.assertEqual(it.clean_settings("daily", {"calendar_ical": "webcal://x.com/a.ics"}),
                         {"calendar_ical": "https://x.com/a.ics"})
        self.assertEqual(it.clean_settings("daily", {"calendar_ical": "file:///C:/secret"}), {})
        self.assertEqual(it.clean_settings("daily", {"calendar_ical": "javascript:alert(1)"}), {})

    def test_saving_keeps_other_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"wake_words": ["يوبي"], "island": {"downloads": False}}, f, ensure_ascii=False)
            with mock.patch.object(it, "CONFIG_PATH", path):
                it.save_section("island", {"theme": "nile"})
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            self.assertEqual(cfg["wake_words"], ["يوبي"])
            self.assertEqual(cfg["island"], {"downloads": False, "theme": "nile"})


class TestDownloads(unittest.TestCase):
    def test_partial_then_finished_file_is_announced(self):
        with tempfile.TemporaryDirectory() as tmp:
            t, sent = make(tmp)
            t._dl_folder, t._dl_folder_at = tmp, time.monotonic()
            part = os.path.join(tmp, "movie.mkv.crdownload")
            with open(part, "wb") as f:
                f.write(b"x" * 1000)
            t._downloads_tick()
            t._dl[part]["first"] -= 5                        # pretend it's been downloading a while
            with open(part, "ab") as f:
                f.write(b"x" * 5000)
            t._downloads_tick()
            live = [m for m in sent if m["t"] == "downloads" and m["items"]]
            self.assertEqual(live[-1]["items"][0]["name"], "movie.mkv")
            self.assertEqual(live[-1]["items"][0]["bytes"], 6000)
            os.replace(part, part[:-len(".crdownload")])
            t._downloads_tick()
            done = [m for m in sent if m.get("kind") == "download_done"]
            self.assertEqual(done[0]["name"], "movie.mkv")
            self.assertEqual(sent[-1], {"t": "downloads", "items": []})

    def test_cancelled_download_is_not_announced(self):
        with tempfile.TemporaryDirectory() as tmp:
            t, sent = make(tmp)
            t._dl_folder, t._dl_folder_at = tmp, time.monotonic()
            part = os.path.join(tmp, "big.zip.part")
            open(part, "wb").close()
            t._downloads_tick()
            os.remove(part)
            t._downloads_tick()
            self.assertFalse(any(m.get("kind") == "download_done" for m in sent))


class TestShelfAndPrivacy(unittest.TestCase):
    def test_shelf_keeps_only_real_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(it, "SHELF_PATH", os.path.join(tmp, "shelf.json")):
                t, sent = make(tmp)
                real = os.path.join(tmp, "a.txt")
                open(real, "w").close()
                t.shelf_add([real, "relative.txt", os.path.join(tmp, "missing.txt"), real])
                self.assertEqual(t._shelf, [real])
                t.handle({"t": "shelf_remove", "i": 0})
                self.assertEqual(t._shelf, [])

    def test_privacy_labels(self):
        self.assertEqual(it.privacy_label(r"C:#Users#me#AppData#Local#Discord#app-1.0#Discord.exe"), "Discord")
        self.assertEqual(it.privacy_label("Microsoft.WindowsCamera_8wekyb3d8bbwe"), "الكاميرا")

    def test_english(self):
        self.assertEqual(it.clean_settings("island", {"lang": "en"}), {"lang": "en"})
        self.assertEqual(it.clean_settings("island", {"lang": "fr"}), {})
        self.assertEqual(it.clean_settings("island", {"position": "left", "idle_info": False}), {"position": "left", "idle_info": False})
        self.assertEqual(it.clean_settings("island", {"position": "bottom"}), {})
        self.assertEqual(it.clean_settings("island", {"wake": "key"}), {"wake": "key"})
        self.assertEqual(it.clean_settings("island", {"wake": "never"}), {})
        self.assertEqual(it.ISLAND_DEFAULTS["wake"], "voice")
        # the wake key: any key hotkey.py knows
        self.assertTrue(it.wake_key_ok(it.ISLAND_DEFAULTS["wake_key"]))
        for good in ("f8", "f9", "f24", "y", "5", "space", "home", "pause", "scroll lock", "shift+f2", "ctrl+space", "alt+shift+y",
                     "ctrl+alt+shift+1", "alt+page up", "num 0", "comma", "ctrl+-", "windows+y", "tab", "caps lock", "=", "[", "semicolon"):
            self.assertEqual(it.clean_settings("island", {"wake_key": good}), {"wake_key": good}, good)
        for bad in ("ctrl", "ctrl+shift", "", "Ctrl+Alt+Y", "ctrl+alt+y, f8", "ctrl+ctrl+y", "win+y", "no such key", "x" * 41, 5, None):
            self.assertEqual(it.clean_settings("island", {"wake_key": bad}), {}, bad)
        try:
            it._ui["lang"] = "en"
            self.assertEqual(it.privacy_label("Microsoft.WindowsCamera_8wekyb3d8bbwe"), "Camera")
            self.assertEqual(it.tr("النت رجع", "The internet came back"), "The internet came back")
        finally:
            it._ui["lang"] = "ar"


if __name__ == "__main__":
    unittest.main()
