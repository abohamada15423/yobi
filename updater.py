# -*- coding: utf-8 -*-
"""Yobi updates itself from GitHub Releases.

Only an installed Yobi checks (runtime\\ next to app\\); running from the source folder never does.
A while after start it asks the GitHub API for the newest release. If it is newer, the island asks
"حدّث؟"; on yes it downloads Yobi-Setup.zip, unpacks it and starts its install.ps1 -Silent, which
closes Yobi, copies the new files over the old ones (keys, settings and what Yobi learned stay)
and opens Yobi again. The next start removes the leftovers and says the update worked.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile

from version import VERSION

REPO = "abohamada15423/yobi"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "Yobi-Setup.zip"
HERE = os.path.dirname(os.path.abspath(__file__))
_TMP = "yobi-update-"          # what an update leaves in %TEMP% until the next start


def parse(v):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def newer(tag, current=VERSION):
    a, b = parse(tag), parse(current)
    return bool(a and b and a > b)


def install_dir(app=HERE):
    """The install folder (it holds runtime\\ and app\\), or None when Yobi runs from source."""
    root = os.path.dirname(app)
    if os.path.basename(app).lower() == "app" and os.path.isfile(os.path.join(root, "runtime", "python.exe")):
        return root
    return None


def latest(current=VERSION, timeout=10):
    """(version, zip url) of the newest release when it is newer than `current`, else None."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "Yobi-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.load(r)
    if rel.get("draft") or rel.get("prerelease") or not newer(rel.get("tag_name"), current):
        return None
    url = next((a.get("browser_download_url") for a in rel.get("assets") or [] if a.get("name") == ASSET), None)
    return (str(rel["tag_name"]).lstrip("v"), url) if url else None


def download(url, path, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Yobi-updater"})
    with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
        total, done, last = int(r.headers.get("Content-Length") or 0), 0, -1
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            pct = done * 100 // total if total else 0
            if progress and pct != last:
                progress(pct)
                last = pct
    if total and done != total:
        raise IOError(f"التحميل اتقطع ({done} من {total})")


def run_installer(zip_path, dest, launch=True):
    """Unpack the new version and start its installer on its own: it closes this Yobi first."""
    out = tempfile.mkdtemp(prefix=_TMP)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    script = next((os.path.join(r, "install.ps1") for r, _, fs in os.walk(out)
                   if "install.ps1" in fs and os.path.basename(r) == "app"), None)
    if not script:
        raise IOError("ملف التحديث ناقص (install.ps1)")
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    args = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script, "-Silent"]
    default = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Yobi")
    if os.path.normcase(os.path.abspath(dest)) != os.path.normcase(os.path.abspath(default)):
        args += ["-Dest", dest]                 # an install somewhere else (the installer's own option)
    if not launch:
        args.append("-NoLaunch")
    # no console window; not DETACHED_PROCESS: PowerShell started that way exits 0 without running anything
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        return subprocess.Popen(args, creationflags=flags | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0), close_fds=True)
    except OSError:                              # a job that forbids breaking away: the installer still outlives us
        return subprocess.Popen(args, creationflags=flags, close_fds=True)


def cleanup(tmp=None):
    """Remove what an earlier update left in %TEMP%. True when there was something (= we just updated)."""
    tmp = tmp or tempfile.gettempdir()
    found = False
    for name in os.listdir(tmp):
        if name.startswith(_TMP) or (name.startswith("Yobi-Setup-") and name.endswith(".zip")):
            p = os.path.join(tmp, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
            found = True
    return found


def _update(island, url, ver, dest, log):
    def show(text, state="executing"):
        island.after(0, lambda: island.set_state(state, text))
    try:
        path = os.path.join(tempfile.gettempdir(), f"Yobi-Setup-{ver}.zip")
        download(url, path, lambda p: show(f"بنزّل التحديث… {p}%"))
        show("بجهّز التحديث…")
        run_installer(path, install_dir())
        show("يوبي هيقفل ويفتح تاني بالنسخة الجديدة", "info")
    except Exception as e:
        log(f"⚠️ التحديث: {e}")
        show("التحديث ما نجحش، هجرّب تاني المرة الجاية", "error")


def watch(island, log=print, delay=45):
    """Background thread: after start, offer a newer version once."""
    dest = install_dir()
    if not dest:
        return
    try:
        if cleanup():
            island.after(3000, lambda: island.say(f"يوبي اتحدّث لـ {VERSION} ✅", state="success"))
    except OSError:
        pass
    time.sleep(delay)
    try:
        found = latest()
    except Exception as e:                       # no internet, GitHub busy: next start tries again
        log(f"⚠️ مش قادر أشوف التحديثات: {e}")
        return
    if not found:
        return
    ver, url = found
    log(f"⬆️ فيه نسخة جديدة: {ver}")
    while not getattr(island, "is_free", lambda: True)():     # never in the middle of a conversation
        time.sleep(20)

    def answer(value):
        if value == "update":
            threading.Thread(target=_update, args=(island, url, ver, dest, log), name="update", daemon=True).start()

    island.after(0, lambda: island.ask(f"فيه نسخة جديدة من يوبي ({ver}). أحدّثه دلوقتي؟",
                                       [("حدّث ⬇️", "update"), ("بعدين", "later")], answer, timeout_ms=60000))
