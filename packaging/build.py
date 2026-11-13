# -*- coding: utf-8 -*-
"""Build Yobi for friends: a folder with its own Python, only the libraries Yobi uses, the app
(no personal files), the island, and a setup script — then Yobi-Setup.zip.

    python packaging/build.py              (build the island first: cd island-tauri && npx tauri build)

Output (outside OneDrive, it's big):  ~/.yobi/dist/Yobi/  and  ~/.yobi/dist/Yobi-Setup.zip
Nothing here downloads anything: it copies what's already installed on this PC.
"""
import compileall
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from deps import needed            # noqa: E402
from manifest import NEVER, app_files   # noqa: E402

DIST = os.path.join(os.path.expanduser("~"), ".yobi", "dist")
OUT = os.path.join(DIST, "Yobi")
PAYLOAD = os.path.join(OUT, "payload")
RUNTIME = os.path.join(PAYLOAD, "runtime")
APP = os.path.join(PAYLOAD, "app")
ISLAND = os.path.join(os.path.expanduser("~"), ".yobi", "tauri-target", "release", "yobi-island.exe")

PY_SKIP = {"test", "idlelib", "turtledemo", "ensurepip", "lib2to3", "site-packages", "venv", "__phello__"}
VC_DLLS = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll")

# a friend's PC: no GPU libraries in the build, nothing preloaded, no debug spam
FRIEND_HEARING = {"wake_debug": False, "stt_warmup_local": False, "stt_local_model": "small",
                  "stt_local_device": "cpu", "stt_local_compute": "int8", "latency_log": False}


def step(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ignore_cache(_d, names):
    return [n for n in names if n in ("__pycache__",) or n.endswith((".pyc", ".pdb"))]


def copy_python():
    base = sys.base_prefix
    os.makedirs(RUNTIME)
    for f in os.listdir(base):
        p = os.path.join(base, f)
        if os.path.isfile(p) and f.lower().endswith((".exe", ".dll")) or f == "LICENSE.txt":
            shutil.copy2(p, RUNTIME)
    shutil.copytree(os.path.join(base, "DLLs"), os.path.join(RUNTIME, "DLLs"), ignore=ignore_cache)
    shutil.copytree(os.path.join(base, "tcl"), os.path.join(RUNTIME, "tcl"), ignore=ignore_cache)
    lib = os.path.join(RUNTIME, "Lib")
    os.makedirs(lib)
    for f in os.listdir(os.path.join(base, "Lib")):
        if f in PY_SKIP or f == "__pycache__":
            continue
        src = os.path.join(base, "Lib", f)
        (shutil.copytree(src, os.path.join(lib, f), ignore=ignore_cache) if os.path.isdir(src)
         else shutil.copy2(src, lib))
    # the C++ runtime some libraries need (onnxruntime, ctranslate2): app-local, in case the PC lacks it
    for dll in VC_DLLS:
        src = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", dll)
        if os.path.exists(src) and not os.path.exists(os.path.join(RUNTIME, dll)):
            shutil.copy2(src, RUNTIME)


def copy_packages(py_files):
    sp = os.path.join(RUNTIME, "Lib", "site-packages")
    os.makedirs(sp)
    dists, missing = needed(py_files)
    tops = set()
    for d in dists.values():
        for f in d.files or []:
            parts = str(f).replace("\\", "/").split("/")
            if parts[0] in ("..", "") or parts[0].endswith(".data"):
                continue
            tops.add(parts[0])
    src_sp = os.path.dirname(os.path.dirname(dists["numpy"].locate_file("numpy/__init__.py")))
    for t in sorted(tops):
        src = os.path.join(src_sp, t)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(sp, t), ignore=ignore_cache, dirs_exist_ok=True)
        elif os.path.isfile(src):
            shutil.copy2(src, sp)
    return len(dists), missing


def copy_app():
    os.makedirs(APP)
    files = app_files()
    for f in files:
        dst = os.path.join(APP, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, f), dst)
    os.makedirs(os.path.join(APP, "bin"))
    shutil.copy2(ISLAND, os.path.join(APP, "bin", "yobi-island.exe"))
    shutil.copy2(os.path.join(ROOT, "island-tauri", "src-tauri", "icons", "icon.ico"), os.path.join(APP, "yobi.ico"))
    for f in ("install.ps1", "uninstall.ps1", "shortcuts.py"):
        shutil.copy2(os.path.join(HERE, f), os.path.join(APP, f))
    ex = os.path.join(APP, "config.example.json")
    with open(ex, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.setdefault("hearing", {}).update(FRIEND_HEARING)
    with open(ex, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return files


REQUIRED = ("agent.py", "launcher.pyw", "first_run.py", "config.example.json", "install.ps1", "uninstall.ps1", "shortcuts.py",
            "yobi.ico", "bin/yobi-island.exe", "models/ya_yobi.onnx",
            "models/yobi-whisper/model.bin")


def check_clean():
    """Last guard: everything Yobi needs is there, and no personal file or key anywhere."""
    bad = [f"missing: {f}" for f in REQUIRED if not os.path.exists(os.path.join(APP, f))]
    for d, _dirs, names in os.walk(APP):
        for n in names:
            p = os.path.join(d, n)
            if n in NEVER and os.path.basename(d) != "yobi-whisper":      # the model's own config.json
                bad.append(p)
            elif n.endswith((".py", ".json", ".txt", ".md", ".ps1", ".pyw")):
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    t = fh.read()
                if "AIza" in t and "AIza[" not in t and "startswith(\"AIza\")" not in t and "بـ AIza" not in t:
                    bad.append(p + "  (looks like a Gemini key)")
                if "gsk_" in t and any(len(w) > 40 and w.startswith("gsk_") for w in t.replace('"', " ").split()):
                    bad.append(p + "  (looks like a Groq key)")
    if bad:
        raise SystemExit("build check failed:\n  " + "\n  ".join(bad))


def folder_mb(p):
    return sum(os.path.getsize(os.path.join(d, n)) for d, _x, ns in os.walk(p) for n in ns) / 2**20


def main():
    if not os.path.exists(ISLAND):
        raise SystemExit(f"build the island first: {ISLAND} is missing")
    step(f"clean {OUT}")
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(PAYLOAD)
    step("python runtime")
    copy_python()
    step("app files")
    files = copy_app()
    step("libraries")
    n, missing = copy_packages([os.path.join(ROOT, f) for f in files if f.endswith((".py", ".pyw"))])
    step(f"  {n} packages" + (f" (not installed here, skipped: {', '.join(missing)})" if missing else ""))
    step("compile")
    compileall.compile_dir(APP, quiet=1, workers=0)
    compileall.compile_dir(os.path.join(RUNTIME, "Lib"), quiet=1, workers=0)
    shutil.copy2(os.path.join(HERE, "Install Yobi.cmd"), OUT)
    shutil.copy2(os.path.join(HERE, "README.txt"), OUT)
    check_clean()
    step(f"folder ready: {OUT}  ({folder_mb(OUT):.0f} MB)")
    if "--no-zip" not in sys.argv:
        z = os.path.join(DIST, "Yobi-Setup.zip")
        if os.path.exists(z):
            os.remove(z)
        step("zip")
        subprocess.run([os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe"), "-a", "-c", "-f", z, "-C", DIST, "Yobi"], check=True)
        step(f"zip ready: {z}  ({os.path.getsize(z) / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
