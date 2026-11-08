# -*- coding: utf-8 -*-
"""
Startup Manager — يقرا/يعطل برامج البدء، ويعرض العمليات الشغالة.
"""

import os
import winreg


def list_startup_items():
    items = []

    for root, path, label in (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "HKLM 32-bit"),
    ):
        try:
            with winreg.OpenKey(root, path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        items.append({
                            "name": name, "command": value,
                            "source": f"registry ({label})",
                            "registry_root": root, "registry_path": path,
                        })
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue

    for folder in (
        os.path.join(os.environ.get("APPDATA", ""),
                     r"Microsoft\Windows\Start Menu\Programs\Startup"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup",
    ):
        if not os.path.isdir(folder):
            continue
        try:
            for fname in os.listdir(folder):
                items.append({
                    "name": fname, "command": os.path.join(folder, fname),
                    "source": "startup folder", "folder": folder,
                })
        except OSError:
            continue

    return items


def disable_startup_item(item):
    try:
        if "registry_root" in item and "registry_path" in item:
            with winreg.OpenKey(item["registry_root"], item["registry_path"],
                                0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, item["name"])
            return True, f"عطلت {item['name']} من الستارت اب ✅"
        if "folder" in item:
            backup = os.path.join(item["folder"], "_yobi_disabled")
            os.makedirs(backup, exist_ok=True)
            os.rename(
                os.path.join(item["folder"], item["name"]),
                os.path.join(backup, item["name"]),
            )
            return True, f"عطلت {item['name']} من الستارت اب ✅"
    except Exception as e:
        return False, f"فشل: {e}"
    return False, "مش قادر أحدد نوع العنصر"


def list_running_processes(minimal=True, min_mb=30):
    import psutil
    result = []
    for proc in psutil.process_iter(["pid", "name", "exe", "memory_info"]):
        try:
            info = proc.info
            mem_mb = (info["memory_info"].rss / (1024 * 1024)
                      if info["memory_info"] else 0)
            if minimal and mem_mb < min_mb:
                continue
            result.append({
                "pid": info["pid"],
                "name": info["name"],
                "exe": info["exe"],
                "mem_mb": round(mem_mb, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(result, key=lambda x: -x["mem_mb"])