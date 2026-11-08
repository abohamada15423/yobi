# -*- coding: utf-8 -*-
"""
Launcher opener + auto-fill.

Auto-fill strategy for Riot Client (CEF-based, so UIA is unreliable):

  1. Check if the game itself is already running — if so, skip auto-fill so
     we never click/paste on top of a running game or logged-in dashboard.
  2. Bring Riot Client window to front.
  3. Click username field (from calibration).
  4. Clear it, paste username via clipboard.
  5. Click password field (from calibration if present, else Tab).
  6. Clear it, paste password via clipboard.
  7. Press Enter to submit.

Credentials are keyed PER-GAME, not per-launcher, so a Riot account for
League of Legends and one for Valorant can coexist:

  • "riot:league"   → League of Legends / Teamfight Tactics
  • "riot:valorant" → Valorant
  • "riot:lor"      → Legends of Runeterra
  • "riot"          → fallback (generic Riot account)

LOGIN_MODE:
  • "auto"   — fills credentials from Windows Credential Manager
  • "manual" — just opens the launcher and lets you type
"""

import os
import subprocess
import time

from credentials import load_credentials, has_credentials
from login_calibration import load_calibration


LOGIN_MODE = "auto"


LAUNCHERS = {
    "riot": {
        "exe_candidates": [
            r"C:\Riot Games\Riot Client\RiotClientServices.exe",
            r"C:\Program Files\Riot Games\Riot Client\RiotClientServices.exe",
        ],
        "process_keywords": ["riotclient", "riot client"],
        "window_title_keywords": ["Riot"],
        "window_class_names": ["RiotClientMainWindow", "RiotClient"],
        "account_key": "riot",
    },
    "steam": {
        "exe_candidates": [
            r"C:\Program Files (x86)\Steam\steam.exe",
            r"C:\Program Files\Steam\steam.exe",
        ],
        "process_keywords": ["steam.exe"],
        "window_title_keywords": ["Steam"],
        "window_class_names": ["Steam"],
        "account_key": "steam",
    },
    "epic": {
        "exe_candidates": [
            r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
            r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        ],
        "process_keywords": ["epicgameslauncher"],
        "window_title_keywords": ["Epic Games Launcher"],
        "window_class_names": ["UnrealWindow"],
        "account_key": "epic",
    },
}


GAME_ACCOUNT_KEYS = {
    # League of Legends & TFT
    "league of legends": "riot:league",
    "teamfight tactics": "riot:league",
    "league": "riot:league",
    "tft": "riot:league",
    "تيم فايت": "riot:league",
    "لول": "riot:league",
    "لوول": "riot:league",
    "ليق": "riot:league",
    "ليج": "riot:league",
    # Valorant
    "valorant": "riot:valorant",
    "فالو": "riot:valorant",
    "فالورنت": "riot:valorant",
    "فالورانت": "riot:valorant",
    # Legends of Runeterra
    "legends of runeterra": "riot:lor",
    "runeterra": "riot:lor",
    "لور": "riot:lor",
}

ACCOUNT_LABELS = {
    "riot:league": "League of Legends",
    "riot:valorant": "Valorant",
    "riot:lor": "Legends of Runeterra",
    "riot": "Riot (عام)",
    "steam": "Steam",
    "epic": "Epic Games",
}

_RIOT_GAME_PROCESSES = {
    "leagueclient.exe",
    "leagueclientux.exe",
    "league of legends.exe",
    "tftclient.exe",
    "valorant.exe",
    "valorant-win64-shipping.exe",
}


def resolve_account_key(launcher_key, game_name=None):
    if game_name:
        g = (game_name or "").lower().strip()
        for pattern in sorted(GAME_ACCOUNT_KEYS, key=len, reverse=True):
            if pattern in g:
                return GAME_ACCOUNT_KEYS[pattern]
    return LAUNCHERS.get(launcher_key, {}).get("account_key", launcher_key)


def label_for_account_key(key):
    return ACCOUNT_LABELS.get(key, key)


def _is_riot_game_running():
    """Return True if an actual Riot game client (League/Valorant/TFT) is already running."""
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if n in _RIOT_GAME_PROCESSES:
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Clipboard helpers
# ---------------------------------------------------------------------------
def _private_formats(win32clipboard):
    """Windows' own markers that keep a copy out of clipboard history (Win+V), cloud sync and
    clipboard monitors (the island's history included). Used for usernames and passwords."""
    return [
        (win32clipboard.RegisterClipboardFormat("ExcludeClipboardContentFromMonitorProcessing"), b"\0"),
        (win32clipboard.RegisterClipboardFormat("CanIncludeInClipboardHistory"), b"\0\0\0\0"),
        (win32clipboard.RegisterClipboardFormat("CanUploadToCloudClipboard"), b"\0\0\0\0"),
    ]


def _clipboard_set(text):
    try:
        import win32clipboard
        import win32con
        for _ in range(3):
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                for fmt, data in _private_formats(win32clipboard):
                    win32clipboard.SetClipboardData(fmt, data)
                win32clipboard.CloseClipboard()
                return True
            except Exception:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
                time.sleep(0.1)
    except ImportError:
        pass

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        GMEM_MOVEABLE = 0x0002
        CF_UNICODETEXT = 13

        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE

        if not user32.OpenClipboard(None):
            raise RuntimeError("OpenClipboard failed")

        try:
            user32.EmptyClipboard()
            buf_size = (len(text) + 1) * 2
            h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, buf_size)
            if not h_global:
                raise RuntimeError("GlobalAlloc failed")
            p_global = kernel32.GlobalLock(h_global)
            if not p_global:
                raise RuntimeError("GlobalLock failed")
            ctypes.memmove(p_global, text.encode("utf-16-le"), buf_size)
            kernel32.GlobalUnlock(h_global)
            user32.SetClipboardData(CF_UNICODETEXT, h_global)
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        pass

    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def _clipboard_get():
    try:
        import win32clipboard
        import win32con
        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return data or ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        return ""


def _send_ctrl_v():
    try:
        import keyboard
        keyboard.send("ctrl+v")
        return True
    except Exception:
        pass
    try:
        import pyautogui
        pyautogui.keyDown("ctrl")
        time.sleep(0.05)
        pyautogui.press("v")
        time.sleep(0.05)
        pyautogui.keyUp("ctrl")
        return True
    except Exception:
        return False


def _paste(pyautogui, text, on_step=None, tag=""):
    if not _clipboard_set(text):
        if on_step:
            on_step(f"❌ مش قادر أكتب في الكليبورد ({tag})")
        return False

    time.sleep(0.2)
    check = _clipboard_get()
    if check != text:
        _clipboard_set(text)
        time.sleep(0.2)

    if not _send_ctrl_v():
        if on_step:
            on_step(f"❌ مش قادر أبعت Ctrl+V ({tag})")
        return False

    time.sleep(0.3)
    if on_step:
        on_step(f"📋 لصقت {tag} ({len(text)} حرف)")
    return True


# ---------------------------------------------------------------------------
# Window discovery
# ---------------------------------------------------------------------------
def _find_launcher_exe(launcher_key):
    for candidate in LAUNCHERS[launcher_key]["exe_candidates"]:
        if os.path.exists(candidate):
            return candidate
    return None


def _is_launcher_running(launcher_key):
    try:
        import psutil
        keys = LAUNCHERS[launcher_key]["process_keywords"]
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if any(k in n for k in keys):
                return True
    except Exception:
        pass
    return False


def _scan_all_windows_for(keywords, class_names):
    try:
        import uiautomation as auto
    except ImportError:
        return None

    keywords_l = [k.lower() for k in keywords]
    classes_l = [c.lower() for c in class_names]

    try:
        root = auto.GetRootControl()
        for child in root.GetChildren():
            try:
                name = (child.Name or "").strip().lower()
                cls = (child.ClassName or "").strip().lower()
                if any(k in name for k in keywords_l):
                    return child
                if any(c in cls for c in classes_l):
                    return child
            except Exception:
                continue
    except Exception:
        pass
    return None


def _find_window_by_pygetwindow(keywords):
    try:
        import pygetwindow as gw
    except ImportError:
        return None
    try:
        for w in gw.getAllWindows():
            title = (w.title or "").strip()
            if title and any(k.lower() in title.lower() for k in keywords):
                if w.width > 200 and w.height > 100:
                    return w
    except Exception:
        pass
    return None


def _wait_for_window(keywords, class_names, timeout=30, min_width=200):
    start = time.time()
    while time.time() - start < timeout:
        ctrl = _scan_all_windows_for(keywords, class_names)
        if ctrl is not None:
            try:
                if ctrl.BoundingRectangle.width() >= min_width:
                    return ("uia", ctrl)
            except Exception:
                return ("uia", ctrl)

        pygw = _find_window_by_pygetwindow(keywords)
        if pygw is not None:
            return ("pygw", pygw)

        time.sleep(0.5)
    return (None, None)


def _bring_to_front_and_get_rect(kind, ctrl):
    if kind == "uia":
        try:
            ctrl.SetActive()
            ctrl.SetFocus()
            time.sleep(0.5)
        except Exception:
            pass
        try:
            r = ctrl.BoundingRectangle
            return (r.left, r.top, r.width(), r.height())
        except Exception:
            return (0, 0, 1920, 1080)
    else:
        try:
            ctrl.activate()
            time.sleep(0.5)
            return (ctrl.left, ctrl.top, ctrl.width, ctrl.height)
        except Exception:
            return (0, 0, 1920, 1080)


def _focus_username_only(left, top, width, height, on_step=None):
    try:
        import pyautogui
    except ImportError:
        return False

    pyautogui.FAILSAFE = False

    cal = load_calibration().get("riot")
    if cal and "username" in cal:
        ux = cal["username"]
        x = left + int(width * ux.get("x_frac", 0.0638))
        y = top + int(height * ux.get("y_frac", 0.3079))
        try:
            pyautogui.click(x, y)
            if on_step:
                on_step("ركّزت على خانة اليوزر — اكتب بياناتك بنفسك ⌨️")
            return True
        except Exception:
            pass

    try:
        pyautogui.click(left + width // 2, top + 12)
        if on_step:
            on_step("فتحت النافذة — اكتب بياناتك بنفسك")
        return True
    except Exception:
        return False


def _auto_fill_via_calibration(left, top, width, height, username, password,
                               on_step=None):
    try:
        import pyautogui
    except ImportError:
        if on_step:
            on_step("pyautogui مش متثبت")
        return False

    pyautogui.FAILSAFE = False

    cal = load_calibration().get("riot")
    if not cal or "username" not in cal:
        if on_step:
            on_step("❌ مفيش معايرة — شغّل python calibrate_login.py الأول")
        return False

    ux = cal["username"]
    user_x = left + int(width * ux.get("x_frac", 0.0638))
    user_y = top + int(height * ux.get("y_frac", 0.3079))

    px_cal = cal.get("password")
    if px_cal and "x_frac" in px_cal and "y_frac" in px_cal:
        pass_x = left + int(width * px_cal["x_frac"])
        pass_y = top + int(height * px_cal["y_frac"])
    else:
        pass_x = pass_y = None

    if on_step:
        on_step(f"هبدأ الإدخال — الكليبورد فيه {len(username)} حرف")

    saved_clip = _clipboard_get()

    try:
        pyautogui.click(left + width // 2, top + 12)
        time.sleep(0.5)

        # 1. Username field
        pyautogui.click(user_x, user_y)
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.15)
        pyautogui.press("delete")
        time.sleep(0.15)

        if not _paste(pyautogui, username, on_step=on_step, tag="اليوزر"):
            return False
        time.sleep(0.5)

        # 2. Password field: click calibrated coordinates if available, else Tab
        if pass_x is not None and pass_y is not None:
            pyautogui.click(pass_x, pass_y)
            time.sleep(0.4)
        else:
            pyautogui.press("tab")
            time.sleep(0.5)

        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.15)
        pyautogui.press("delete")
        time.sleep(0.15)

        if not _paste(pyautogui, password, on_step=on_step, tag="الباسورد"):
            return False
        time.sleep(0.5)

        pyautogui.press("enter")
        if on_step:
            on_step("دوست Enter — بستنى اللوجين...")

        time.sleep(2.5)
        return True

    except Exception as e:
        if on_step:
            on_step(f"❌ فشل الإدخال: {e}")
        return False
    finally:
        if saved_clip is not None:
            _clipboard_set(saved_clip)


# ---------------------------------------------------------------------------
# Main login flow
# ---------------------------------------------------------------------------
def login_riot(username=None, password=None, on_step=None):
    # If the game client itself is already running, user is already signed in!
    if _is_riot_game_running():
        if on_step:
            on_step("اللعبة شغالة بالفعل ومفتوحة بحسابك ✅")
        return True

    exe = _find_launcher_exe("riot")
    if not exe:
        if on_step:
            on_step("مش لاقي Riot Client على الجهاز")
        return False

    already = _is_launcher_running("riot")
    if not already:
        try:
            subprocess.Popen([exe])
        except Exception as e:
            if on_step:
                on_step(f"مش قادر أشغل Riot Client: {e}")
            return False
        if on_step:
            on_step("بستنى Riot Client يفتح...")
    else:
        if on_step:
            on_step("Riot Client مفتوح — بتأكد من حالة الدخول...")

    # Wait briefly in case Riot auto-launches the game (Stay Signed In)
    for _ in range(6):
        if _is_riot_game_running():
            if on_step:
                on_step("تم الدخول تلقائياً واللعبة فتحت ✅")
            return True
        time.sleep(0.5)

    kind, ctrl = _wait_for_window(
        keywords=LAUNCHERS["riot"]["window_title_keywords"],
        class_names=LAUNCHERS["riot"]["window_class_names"],
        timeout=25,
    )
    if kind is None:
        if _is_riot_game_running():
            return True
        if on_step:
            on_step("مش لاقي نافذة Riot Client بعد 25 ثانية")
        return False

    if on_step:
        on_step(f"لقيت النافذة ({kind})")

    time.sleep(1.5)
    if _is_riot_game_running():
        return True

    left, top, width, height = _bring_to_front_and_get_rect(kind, ctrl)

    if LOGIN_MODE == "manual":
        return _focus_username_only(left, top, width, height, on_step=on_step)

    if not username or not password:
        if on_step:
            on_step("مفيش بيانات محفوظة — اكتب بنفسك")
        return _focus_username_only(left, top, width, height, on_step=on_step)

    return _auto_fill_via_calibration(
        left, top, width, height, username, password, on_step=on_step,
    )


def try_auto_login(launcher_key, game_name=None, on_step=None):
    if launcher_key not in LAUNCHERS:
        return False

    account_key = resolve_account_key(launcher_key, game_name)

    user = pwd = None
    if LOGIN_MODE == "auto" and has_credentials(account_key):
        user, pwd = load_credentials(account_key)
        if on_step:
            on_step(f"لقيت بيانات {label_for_account_key(account_key)} محفوظة")
    else:
        fallback = LAUNCHERS[launcher_key]["account_key"]
        if fallback != account_key and has_credentials(fallback):
            account_key = fallback
            if LOGIN_MODE == "auto":
                user, pwd = load_credentials(account_key)
                if on_step:
                    on_step("مفيش بيانات للعبة — هستخدم حساب Riot العام")
        else:
            if on_step:
                on_step(f"مفيش بيانات محفوظة ({account_key})")

    if launcher_key == "riot":
        return login_riot(user, pwd, on_step=on_step)
    return False


def launcher_for_game(game_name):
    g = (game_name or "").lower()
    riot_games = [
        "league of legends", "teamfight tactics", "tft", "تيم فايت",
        "لول", "لوول", "ليق", "ليج",
        "valorant", "فالو", "فالورنت", "فالورانت",
        "legends of runeterra", "لور",
    ]
    if any(name in g for name in riot_games):
        return "riot"
    return None


def debug_dump_windows():
    try:
        import uiautomation as auto
    except ImportError:
        print("uiautomation مش متثبت")
        return
    root = auto.GetRootControl()
    for child in root.GetChildren():
        try:
            print(f"  Name='{child.Name}'  ClassName='{child.ClassName}'")
        except Exception:
            pass