# -*- coding: utf-8 -*-
"""Publish a new Yobi version to your friends in one command:

    python packaging/release.py                      (1.0.0 -> 1.0.1)
    python packaging/release.py 1.2.0 --notes "إيه الجديد"

Commit your changes first and close Yobi (its island locks the build). It then: runs the tests,
raises version.py, builds the island and Yobi-Setup.zip, commits + pushes, and creates the GitHub
release with the zip. Every installed Yobi sees it on its next start and offers to update.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import updater  # noqa: E402
from version import VERSION  # noqa: E402

VERSION_FILE = os.path.join(ROOT, "version.py")
ZIP = os.path.join(os.path.expanduser("~"), ".yobi", "dist", "Yobi-Setup.zip")


def run(cmd, cwd=ROOT, **kw):
    print(">", " ".join(cmd) if isinstance(cmd, list) else cmd, flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True, **kw)


def out(cmd):
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def find_gh():
    gh = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    if not os.path.isfile(gh):
        raise SystemExit("ثبّت GitHub CLI الأول:  winget install GitHub.cli   وبعدين  gh auth login")
    return gh


def bump(v):
    a, b, c = updater.parse(v)
    return f"{a}.{b}.{c + 1}"


def write_version(v):
    with open(VERSION_FILE, encoding="utf-8") as f:
        s = f.read()
    with open(VERSION_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(s.replace(f'VERSION = "{VERSION}"', f'VERSION = "{v}"'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?", help="the new version (default: raise the last number)")
    ap.add_argument("--notes", default="", help="what changed, shown on the release page")
    ap.add_argument("--skip-tests", action="store_true")
    a = ap.parse_args()

    new = a.version or bump(VERSION)
    if not updater.newer(new, VERSION):
        raise SystemExit(f"النسخة الجديدة ({new}) لازم تبقى أكبر من الحالية ({VERSION})")
    gh = find_gh()
    if out(["git", "status", "--porcelain"]):
        raise SystemExit("فيه تعديلات مش متعملها commit. اعمل commit الأول، وبعدين شغّل الأمر ده تاني.")
    if "yobi-island.exe" in out(["tasklist", "/FI", "IMAGENAME eq yobi-island.exe"]).lower():
        raise SystemExit("اقفل يوبي الأول (الجزيرة شغالة وماسكة ملف البناء).")

    if not a.skip_tests:
        tests = sorted(f for f in os.listdir(os.path.join(ROOT, "tests")) if f.startswith("test_") and f.endswith(".py"))
        for t in tests:
            r = subprocess.run([sys.executable, "-X", "utf8", os.path.join("tests", t)], cwd=ROOT, capture_output=True)
            if r.returncode != 0:
                raise SystemExit(f"اختبار وقع: tests/{t}\n{r.stdout.decode('utf-8', 'replace')[-1500:]}{r.stderr.decode('utf-8', 'replace')[-1500:]}")
        print(f"✓ {len(tests)} test files", flush=True)

    write_version(new)
    try:
        run("npx tauri build", cwd=os.path.join(ROOT, "island-tauri"), shell=True)
        run([sys.executable, "-X", "utf8", os.path.join(HERE, "build.py")])
    except BaseException:
        write_version(VERSION)                    # nothing published: put the old number back
        raise

    run(["git", "commit", "-q", "-m", f"Release {new}", "--", "version.py"])
    run(["git", "push", "origin", "HEAD"])
    notes = a.notes or f"Yobi {new}"
    notes += ("\n\nاللي عنده يوبي هيطلعله «حدّث» لوحده. أول مرة: نزّل Yobi-Setup.zip، فك الضغط، ودوس على Install Yobi.cmd."
              "\nFirst time: download Yobi-Setup.zip, extract it and run Install Yobi.cmd.")
    run([gh, "release", "create", f"v{new}", ZIP, "--title", f"Yobi {new}", "--notes", notes,
         "--target", out(["git", "rev-parse", "HEAD"])])
    print(f"\n✅ Yobi {new} اتنشر. أصحابك هيشوفوا «حدّث» أول ما يفتحوا يوبي.")


if __name__ == "__main__":
    main()
