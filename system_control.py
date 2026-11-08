# -*- coding: utf-8 -*-
"""
System-level controls: volume (including exact percentage), brightness
(including exact percentage), lock screen, screenshots, media keys, and
power actions (shutdown/restart/sleep/log off).
"""

import ctypes
import datetime
import os
import re
import subprocess
import time

try:
    import keyboard
    _HAS_KEYBOARD = True
except ImportError:
    keyboard = None
    _HAS_KEYBOARD = False

try:
    import screen_brightness_control as sbc
    _HAS_BRIGHTNESS = True
except ImportError:
    _HAS_BRIGHTNESS = False


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_AR_NUM_WORDS = {
    "صفر": 0, "عشرة": 10, "عشره": 10, "عشرين": 20, "تلاتين": 30, "ثلاثين": 30,
    "اربعين": 40, "أربعين": 40, "خمسين": 50, "النص": 50, "للنص": 50, "نص": 50,
    "ستين": 60, "سبعين": 70, "تمانين": 80, "ثمانين": 80, "تسعين": 90,
    "مية": 100, "ميه": 100, "مائة": 100,
}


def _extract_percentage(cmd: str):
    t = (cmd or "").translate(_AR_DIGITS).lower()
    # Explicit percentage unit ("50%", "50 في المية")
    m = re.search(r"(\d{1,3})\s*(?:%|في المية|في الميه|بالمية|بالميه|percent)", t)
    if m:
        return max(0, min(100, int(m.group(1))))
    # Absolute setting verb/preposition ("خلي الصوت 50", "ظبط السطوع على 70", "set volume to 40")
    if re.search(r"(?:خلي|خلى|ظبط|اضبط|اعمل|على|لـ|ل\s|set\b|to\b)", t) and not re.search(r"(?:زود|قلل|ارفع|اخفض)", t):
        m2 = re.search(r"(\d{1,3})(?!\s*(?:درج[ةه]|درجات))", t)
        if m2:
            return max(0, min(100, int(m2.group(1))))
    for word, val in _AR_NUM_WORDS.items():
        if re.search(rf"(?:^|\s){re.escape(word)}(?:\s|$)", t):
            return val
    return None


def _get_endpoint_volume():
    """Return pycaw IAudioEndpointVolume interface (thread-safe with CoInitialize)."""
    try:
        import comtypes
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        devices = AudioUtilities.GetSpeakers()
        if hasattr(devices, "EndpointVolume"):
            return devices.EndpointVolume
        raw_dev = getattr(devices, "_dev", devices)
        interface = raw_dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception:
        return None


def _set_mute_state(mute: bool) -> bool:
    vol = _get_endpoint_volume()
    if vol is not None:
        try:
            vol.SetMute(1 if mute else 0, None)
            return True
        except Exception:
            pass
    return False


def set_volume(level: int):
    """Set master volume to an exact percentage (0..100)."""
    level = max(0, min(100, int(level)))
    vol = _get_endpoint_volume()
    if vol is not None:
        try:
            vol.SetMute(0 if level > 0 else 1, None)
            vol.SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"تم ضبط الصوت على {level}% 🔊"
        except Exception:
            pass
    if _HAS_KEYBOARD:
        for _ in range(50):
            keyboard.send("volume down")
        for _ in range(level // 2):
            keyboard.send("volume up")
            time.sleep(0.01)
        return f"تم ضبط الصوت على {level}% 🔊"
    return "مش قادر أتحكم في الصوت"


def volume_up():
    vol = _get_endpoint_volume()
    if vol is not None:
        try:
            cur = float(vol.GetMasterVolumeLevelScalar())
            new_lvl = min(1.0, cur + 0.10)
            vol.SetMute(0, None)
            vol.SetMasterVolumeLevelScalar(new_lvl, None)
            return f"تم رفع الصوت ({int(round(new_lvl * 100))}%) 🔊"
        except Exception:
            pass
    if _HAS_KEYBOARD:
        for _ in range(5):
            keyboard.send("volume up")
            time.sleep(0.03)
    return "تم رفع الصوت 🔊"


def volume_down():
    vol = _get_endpoint_volume()
    if vol is not None:
        try:
            cur = float(vol.GetMasterVolumeLevelScalar())
            new_lvl = max(0.0, cur - 0.10)
            vol.SetMasterVolumeLevelScalar(new_lvl, None)
            return f"تم خفض الصوت ({int(round(new_lvl * 100))}%) 🔉"
        except Exception:
            pass
    if _HAS_KEYBOARD:
        for _ in range(5):
            keyboard.send("volume down")
            time.sleep(0.03)
    return "تم خفض الصوت 🔉"


def volume_mute():
    if _set_mute_state(True):
        return "تم كتم الصوت 🔇"
    if _HAS_KEYBOARD:
        keyboard.send("volume mute")
    return "تم تبديل حالة الكتم 🔇"


def volume_unmute():
    if _set_mute_state(False):
        return "تم إلغاء كتم الصوت 🔊"
    if _HAS_KEYBOARD:
        keyboard.send("volume mute")
    return "تم تبديل حالة الكتم 🔊"


def volume_max():
    return set_volume(100)


def volume_min():
    return set_volume(10)


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------
def set_brightness(level: int):
    if not _HAS_BRIGHTNESS:
        return "مكتبة التحكم في السطوع مش متثبتة (pip install screen-brightness-control)"
    level = max(0, min(100, int(level)))
    try:
        sbc.set_brightness(level)
        return f"تم ضبط السطوع على {level}% ☀️"
    except Exception as e:
        return f"معرفتش أغيّر السطوع: {e}"


def brightness_up(step=10):
    if not _HAS_BRIGHTNESS:
        return "مكتبة التحكم في السطوع مش متثبتة (pip install screen-brightness-control)"
    try:
        current = sbc.get_brightness(display=0)[0]
        new_val = min(current + step, 100)
        sbc.set_brightness(new_val)
        return f"تم رفع السطوع ({new_val}%) ☀️"
    except Exception as e:
        return f"معرفتش أغيّر السطوع: {e}"


def brightness_down(step=10):
    if not _HAS_BRIGHTNESS:
        return "مكتبة التحكم في السطوع مش متثبتة (pip install screen-brightness-control)"
    try:
        current = sbc.get_brightness(display=0)[0]
        new_val = max(current - step, 0)
        sbc.set_brightness(new_val)
        return f"تم خفض السطوع ({new_val}%) 🔅"
    except Exception as e:
        return f"معرفتش أغيّر السطوع: {e}"


# ---------------------------------------------------------------------------
# Lock / screenshot / power actions
# ---------------------------------------------------------------------------
def lock_screen():
    ctypes.windll.user32.LockWorkStation()
    return "تم قفل الشاشة 🔒"


def take_screenshot():
    import pyautogui
    save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Yobi Screenshots")
    os.makedirs(save_dir, exist_ok=True)
    filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(save_dir, filename)
    pyautogui.screenshot().save(path)
    return f"اتحفظت لقطة الشاشة في {path} 📸"


def shutdown_pc():
    subprocess.run(["shutdown", "/s", "/t", "5"])
    return "هيتم إطفاء الجهاز خلال 5 ثواني... (اعمل 'الغاء الاطفاء' لو غلط)"


def cancel_shutdown():
    subprocess.run(["shutdown", "/a"])
    return "اتلغى الإطفاء ✅"


def restart_pc():
    subprocess.run(["shutdown", "/r", "/t", "5"])
    return "هيتم إعادة تشغيل الجهاز خلال 5 ثواني... (اعمل 'الغاء الاطفاء' لو غلط)"


def sleep_pc():
    subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    return "الجهاز بينام 😴"


def log_off():
    subprocess.run(["shutdown", "/l"])
    return "تم تسجيل الخروج 👋"


# ---------------------------------------------------------------------------
# Media controls
# ---------------------------------------------------------------------------
def media_play_pause():
    if _HAS_KEYBOARD:
        keyboard.send("play/pause media")
    return "تم إيقاف / تشغيل الميديا ⏯️"


def media_next():
    if _HAS_KEYBOARD:
        keyboard.send("next track")
    return "التراك التالي ⏭️"


def media_previous():
    if _HAS_KEYBOARD:
        keyboard.send("previous track")
    return "التراك السابق ⏮️"


SYSTEM_COMMANDS = [
    (["علي الصوت للاخر", "علي الصوت ع الاخر", "ارفع الصوت للاخر", "max volume"], volume_max, "أعلى صوت", False),
    (["وطي الصوت للاخر", "وطي الصوت ع الاخر", "min volume"], volume_min, "أقل صوت", False),
    (["ارفع الصوت", "زود الصوت", "علي الصوت", "علي صوت", "علي شويه", "علي شوية", "عايز اعلي الصوت", "volume up", "sound up"], volume_up, "رفع الصوت", False),
    (["اخفض الصوت", "قلل الصوت", "وطي الصوت", "وطي صوت", "وطي شويه", "وطي شوية", "عايز اوطي الصوت", "volume down", "sound down"], volume_down, "خفض الصوت", False),
    (["الغي كتم الصوت", "إلغاء كتم الصوت", "الغاء الكتم", "فك الكتم", "شيل الميوت", "افتح الصوت", "unmute"], volume_unmute, "إلغاء كتم الصوت", False),
    (["اكتم الصوت", "كتم الصوت", "صامت", "سكت الصوت", "اعمل ميوت", "ميوت", "mute"], volume_mute, "كتم الصوت", False),
    (["وقف الفيديو", "وقف الاغاني", "وقف الأغاني", "وقف المزيكا", "وقف الميوزك", "بوز", "pause", "pause music"], media_play_pause, "إيقاف/تشغيل الميديا", False),
    (["كمل الاغاني", "كمل الأغاني", "كمل الفيديو", "شغل الاغاني تاني", "بلاي", "play music", "play media"], media_play_pause, "تشغيل الميديا", False),
    (["الاغنية اللي بعدها", "الأغنية اللي بعدها", "التراك اللي بعده", "هات التراك اللي بعده", "اللي بعده", "next track", "skip track"], media_next, "التراك التالي", False),
    (["الاغنية اللي فاتت", "الأغنية اللي فاتت", "التراك اللي فات", "اللي قبله", "previous track"], media_previous, "التراك السابق", False),
    (["زود السطوع", "ارفع السطوع", "علي السطوع", "علي إضاءة الشاشة", "brightness up"], brightness_up, "رفع السطوع", False),
    (["قلل السطوع", "خفض السطوع", "وطي السطوع", "وطي إضاءة الشاشة", "brightness down"], brightness_down, "خفض السطوع", False),
    (["اقفل الشاشة", "قفل الشاشة", "lock screen", "lock the screen"], lock_screen, "قفل الشاشة", False),
    (["خد سكرين شوت", "لقطة شاشة", "سكرين شوت", "screenshot"], take_screenshot, "أخذ لقطة شاشة", False),
    (["نوم الجهاز", "وضع السكون", "اعمل سليب", "sleep mode", "go to sleep"], sleep_pc, "تنويم الجهاز", False),
    (["سجل خروج", "log off", "sign out"], log_off, "تسجيل الخروج", False),
    (["الغاء الاطفاء", "الغاء الإطفاء", "cancel shutdown"], cancel_shutdown, "إلغاء الإطفاء/الريستارت", False),
    (["اطفي الجهاز", "قفل الجهاز خالص", "shutdown", "shut down"], shutdown_pc, "إطفاء الجهاز", True),
    (["اعمل ريستارت", "اعد تشغيل الجهاز", "restart"], restart_pc, "إعادة تشغيل الجهاز", True),
]


def match_system_command(command):
    """Returns (action_fn, description, needs_confirmation) or None."""
    command_l = (command or "").lower().strip()
    if not command_l:
        return None

    # 1. Explicit max/min extremes ("علي الصوت للاخر", "وطي الصوت للاخر", "وطي السطوع للاخر")
    if any(p in command_l for p in ("وطي السطوع للاخر", "وطي السطوع للآخر", "وطي السطوع ع الاخر", "اقل سطوع", "أقل سطوع", "min brightness")):
        return (lambda: set_brightness(10), "أقل سطوع", False)
    if any(p in command_l for p in ("علي السطوع للاخر", "علي السطوع للآخر", "علي السطوع ع الاخر", "ارفع السطوع للاخر", "اعلى سطوع", "أعلى سطوع", "max brightness")):
        return (lambda: set_brightness(100), "أعلى سطوع", False)

    # 2. Exact percentage volume / brightness ("خلي الصوت 50%", "ظبط السطوع على 70")
    lvl = _extract_percentage(command_l)
    if lvl is not None:
        if any(w in command_l for w in ("صوت", "الصوت", "volume")):
            return (lambda v=lvl: set_volume(v), f"ضبط الصوت على {lvl}%", False)
        if any(w in command_l for w in ("سطوع", "السطوع", "إضاءة", "اضاءة", "brightness")):
            return (lambda v=lvl: set_brightness(v), f"ضبط السطوع على {lvl}%", False)

    # 3. Standard phrase matching
    for phrases, fn, description, needs_confirm in SYSTEM_COMMANDS:
        if any(p in command_l for p in phrases):
            return fn, description, needs_confirm
    return None


def pick_processes(procs, candidates):
    """Which running processes "اقفل X" means: exact names first; only if none, a name that
    contains one of the candidates (4+ letters), so "اقفل chrome" closes chrome.exe and not
    every process that happens to have "chrome" in its name."""
    exact = [p for p, name in procs if name in candidates]
    if exact:
        return exact
    return [p for p, name in procs if any(len(c) >= 4 and c in name for c in candidates)]
