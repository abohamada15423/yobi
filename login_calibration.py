# -*- coding: utf-8 -*-
"""
Login Calibration — معايرة أماكن خانات الدخول مرة واحدة.

بيحفظ الإحداثيات كنِسَب من حجم النافذة، فبتشتغل على أي دقة.
"""

import json
import os
import time

CAL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "login_calibration.json"
)


def load_calibration():
    if os.path.exists(CAL_PATH):
        try:
            with open(CAL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_calibration(data):
    try:
        with open(CAL_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def _beep(freq=880, dur=80):
    try:
        import winsound
        winsound.Beep(freq, dur)
    except Exception:
        pass


def _wait_for_riot_window():
    try:
        from auto_login import (
            _scan_all_windows_for, LAUNCHERS,
        )
    except ImportError:
        return None

    ctrl = _scan_all_windows_for(
        LAUNCHERS["riot"]["window_title_keywords"],
        LAUNCHERS["riot"]["window_class_names"],
    )
    if ctrl is None:
        return None
    try:
        rect = ctrl.BoundingRectangle
        return (rect.left, rect.top, rect.width(), rect.height())
    except Exception:
        return None


def calibrate_riot():
    try:
        import keyboard
        import pyautogui
    except ImportError as e:
        print(f"❌ محتاج: pip install keyboard pyautogui ({e})")
        return None

    print()
    print("=" * 60)
    print("  معايرة Riot Client")
    print("=" * 60)

    rect = _wait_for_riot_window()
    if rect is None:
        print("❌ افتح Riot Client الأول وجرب تاني.")
        return None

    win_left, win_top, win_w, win_h = rect
    print(f"✅ النافذة: ({win_left}, {win_top}) — {win_w}x{win_h}")
    print()

    points = {}

    print("👉 حرّك الماوس على مركز خانة USERNAME ثم دوس F8")
    _beep(660, 120)
    keyboard.wait("f8")
    time.sleep(0.3)
    ux, uy = pyautogui.position()
    points["username"] = (ux, uy)
    print(f"   ✅ ({ux}, {uy})")
    _beep(880, 100)
    print()

    print("👉 حرّك الماوس على مركز خانة PASSWORD ثم دوس F8")
    _beep(660, 120)
    keyboard.wait("f8")
    time.sleep(0.3)
    px, py = pyautogui.position()
    points["password"] = (px, py)
    print(f"   ✅ ({px}, {py})")
    _beep(880, 100)
    print()

    data = {}
    for key, (x, y) in points.items():
        data[key] = {
            "x_frac": round((x - win_left) / win_w, 4),
            "y_frac": round((y - win_top) / win_h, 4),
        }

    cal = load_calibration()
    cal["riot"] = data
    if save_calibration(cal):
        print("=" * 60)
        print("✅ اتحفظت!")
        print("=" * 60)
        return data
    return None