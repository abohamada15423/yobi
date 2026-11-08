# -*- coding: utf-8 -*-
"""
Smart Full Scan — فحص شامل للجهاز عند أول تشغيل.

يغطي:
  • البرامج المثبتة (من app_scanner)
  • الألعاب من كل الـ launchers (من game_scanner)
  • برامج البدء (Registry Run + Startup folder)
  • المتصفحات المثبتة
  • شبكات الواي فاي المحفوظة
  • عدد ملفات الفولدرات المهمة

بيحفظ النتيجة في smart_scan_cache.json عشان مايعيدهاش كل مرة.
"""

import json
import os
import platform
import subprocess
import time
import winreg

CURRENT_OS = platform.system().lower()
_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "smart_scan_cache.json")


def _scan_startup_programs():
    items = []
    locations = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        items.append({"name": name, "command": value, "source": path})
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue

    for folder in [
        os.path.join(os.environ.get("APPDATA", ""),
                     r"Microsoft\Windows\Start Menu\Programs\Startup"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup",
    ]:
        if os.path.isdir(folder):
            try:
                for f in os.listdir(folder):
                    if not f.startswith("."):
                        items.append({
                            "name": f,
                            "command": os.path.join(folder, f),
                            "source": "startup_folder",
                        })
            except OSError:
                pass
    return items


def _scan_browsers():
    browsers = []
    candidates = {
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "firefox": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "brave": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
    }
    for name, paths in candidates.items():
        for p in paths:
            if os.path.exists(p):
                browsers.append({"name": name, "path": p})
                break
    return browsers


def _scan_wifi_networks():
    try:
        out = subprocess.run(
            ["netsh", "wlan", "show", "profiles"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="ignore",
        ).stdout
        profiles = []
        for line in out.splitlines():
            if ":" in line and ("All User Profile" in line or "الملف الشخصي" in line):
                name = line.split(":", 1)[1].strip()
                if name:
                    profiles.append(name)
        return profiles
    except Exception:
        return []


def _scan_user_folders():
    home = os.path.expanduser("~")
    counts = {}
    for folder in ("Downloads", "Documents", "Desktop", "Pictures", "Videos", "Music"):
        for path in (os.path.join(home, folder), os.path.join(home, "OneDrive", folder)):
            if os.path.isdir(path):
                try:
                    counts[folder] = len(os.listdir(path))
                except OSError:
                    counts[folder] = 0
                break
    return counts


def run_full_scan(force=False):
    if not force and os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    print("🔍 فحص شامل للجهاز...")

    from app_scanner import load_or_scan_installed_apps
    from game_scanner import scan_all_games
    try:
        from launcher_discovery import scan_all_other_launchers
    except ImportError:
        scan_all_other_launchers = lambda: {}

    apps_cache = os.path.join(_HERE, "installed_apps_cache.json")
    apps = load_or_scan_installed_apps(apps_cache, CURRENT_OS, force_rescan=force)

    games = scan_all_games()
    try:
        games.update(scan_all_other_launchers())
    except Exception:
        pass

    startup = _scan_startup_programs()
    browsers = _scan_browsers()
    wifi = _scan_wifi_networks()
    folders = _scan_user_folders()

    result = {
        "timestamp": time.time(),
        "apps_count": len(apps),
        "games_count": len(games),
        "apps": list(apps.keys()),
        "games": list(games.keys()),
        "startup_programs": startup,
        "browsers": browsers,
        "wifi_networks": wifi,
        "user_folders": folders,
    }

    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

    return result


def get_scan_summary():
    data = run_full_scan()
    return (
        f"عدد البرامج: {data['apps_count']} | "
        f"الألعاب: {data['games_count']} | "
        f"برامج البدء: {len(data['startup_programs'])} | "
        f"المتصفحات: {', '.join(b['name'] for b in data['browsers'])}"
    )