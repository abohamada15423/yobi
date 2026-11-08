# -*- coding: utf-8 -*-
"""
Island tools — شغلك على الجزيرة: التحميلات، الرف (Shelf)، الحافظة، لقطات الشاشة،
نقط المايك والكاميرا، الإخفاء وقت الـ fullscreen، والإعدادات.

Privacy rules kept here:
  • clipboard history lives in memory only and skips anything marked private
    (passwords from auto_login.py, password managers);
  • downloads are seen from file names and sizes in the Downloads folder; no file is read;
  • the shelf stores paths only; nothing is copied.
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_HERE, "config.json")
SHELF_PATH = os.path.join(_HERE, "shelf.json")

# ── settings: what the settings window may change, and the allowed values ──
THEMES = ("faience", "night", "papyrus", "nile", "carnelian")
LANGS = ("ar", "en")            # the island's language (Yobi's own replies stay as the brain writes them)
ISLAND_DEFAULTS = {
    "theme": "faience", "lang": "ar", "hide_fullscreen": True, "reduce_motion": False,
    "clipboard_history": True, "screenshot_toast": True, "privacy_dots": True,
    "downloads": True, "music_tab": True, "track_peek": True,
    # batch 5
    "weather": True, "net_toasts": True, "smart_clipboard": True, "morning_brief": True,
    "welcome_back": True, "wellbeing": True, "celebrate": True, "battery_saver": False,
    "radio_pause_prayer": True,
    "battery_saver_at": 20, "radio_volume": 70, "radio_station": "", "pinned_apps": [],
    # polish
    "shortcut": "Ctrl+Alt+I", "display": "primary", "position": "top", "idle_clock": True, "idle_info": True, "autostart": False,
}
SHORTCUTS = ("Ctrl+Alt+I", "Ctrl+Alt+Space", "Ctrl+Shift+Space", "Alt+Shift+Y", "")
ISLAND_RANGES = {"battery_saver_at": (10, 100), "radio_volume": (0, 100)}
DAILY_RANGES = {
    "prayer_soon_min": (0, 30), "focus_min": (5, 120), "break_min": (1, 60),
    "long_break_min": (5, 60), "remind_every_min": (1, 240), "remind_for_s": (5, 300),
}
DAILY_CHOICES = {"method": ("EGYPT", "MWL", "MAKKAH", "KARACHI", "ISNA"), "asr": ("standard", "hanafi")}
DAILY_BOOLS = ("prayer_alerts", "reminders", "remind_ayah", "remind_dua", "remind_dhikr")
CITIES = [  # name, lat, lon, usual method
    ("القاهرة", 30.0444, 31.2357, "EGYPT"), ("الجيزة", 30.0131, 31.2089, "EGYPT"),
    ("الإسكندرية", 31.2001, 29.9187, "EGYPT"), ("المنصورة", 31.0409, 31.3785, "EGYPT"),
    ("طنطا", 30.7865, 31.0004, "EGYPT"), ("الزقازيق", 30.5877, 31.5020, "EGYPT"),
    ("بورسعيد", 31.2653, 32.3019, "EGYPT"), ("السويس", 29.9668, 32.5498, "EGYPT"),
    ("الإسماعيلية", 30.5965, 32.2715, "EGYPT"), ("دمياط", 31.4165, 31.8133, "EGYPT"),
    ("الفيوم", 29.3084, 30.8428, "EGYPT"), ("بني سويف", 29.0661, 31.0994, "EGYPT"),
    ("المنيا", 28.1099, 30.7503, "EGYPT"), ("أسيوط", 27.1783, 31.1859, "EGYPT"),
    ("سوهاج", 26.5591, 31.6957, "EGYPT"), ("الأقصر", 25.6872, 32.6396, "EGYPT"),
    ("أسوان", 24.0889, 32.8998, "EGYPT"), ("الغردقة", 27.2579, 33.8116, "EGYPT"),
    ("شرم الشيخ", 27.9158, 34.3299, "EGYPT"), ("كفر الشيخ", 31.1107, 30.9388, "EGYPT"),
    ("مكة المكرمة", 21.4225, 39.8262, "MAKKAH"), ("المدينة المنورة", 24.4672, 39.6111, "MAKKAH"),
    ("الرياض", 24.7136, 46.6753, "MAKKAH"), ("جدة", 21.4858, 39.1925, "MAKKAH"),
    ("دبي", 25.2048, 55.2708, "MWL"), ("الكويت", 29.3759, 47.9774, "MWL"),
    ("الدوحة", 25.2854, 51.5310, "MWL"), ("عمّان", 31.9539, 35.9106, "MWL"),
    ("بيروت", 33.8938, 35.5018, "MWL"), ("بغداد", 33.3152, 44.3661, "MWL"),
    ("الخرطوم", 15.5007, 32.5599, "EGYPT"), ("تونس", 36.8065, 10.1815, "MWL"),
    ("الجزائر", 36.7538, 3.0588, "MWL"), ("الدار البيضاء", 33.5731, -7.5898, "MWL"),
]
_QUIET_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


_ui = {"lang": "ar"}


def tr(ar, en):
    """A word the island shows, in its language (Settings → Look → Language)."""
    return en if _ui["lang"] == "en" else ar


def clean_settings(section, patch):
    """Keep only known keys with valid values (numbers clamped to their range)."""
    out = {}
    for k, v in (patch or {}).items():
        if section == "island":
            if k == "theme":
                if v in THEMES:
                    out[k] = v
            elif k == "lang":
                if v in LANGS:
                    out[k] = v
            elif k in ISLAND_RANGES and isinstance(v, (int, float)) and not isinstance(v, bool):
                lo, hi = ISLAND_RANGES[k]
                out[k] = int(min(max(round(v), lo), hi))
            elif k == "radio_station" and isinstance(v, str):
                from island_extras import radio_url_ok
                if v == "" or radio_url_ok(v):
                    out[k] = v
            elif k == "position" and v in ("top", "right", "left"):
                out[k] = v
            elif k == "shortcut" and v in SHORTCUTS:
                out[k] = v
            elif k == "display" and isinstance(v, str) and (v in ("primary", "cursor") or re.fullmatch(r"[0-9]{1,12}", v)):
                out[k] = v
            elif k == "pinned_apps" and isinstance(v, list):
                out[k] = [str(x)[:80] for x in v if isinstance(x, str) and x.strip()][:12]
            elif k in ISLAND_DEFAULTS and isinstance(ISLAND_DEFAULTS[k], bool) and isinstance(v, bool):
                out[k] = v
        elif section == "daily":
            if k in DAILY_BOOLS and isinstance(v, bool):
                out[k] = v
            elif k in DAILY_RANGES and isinstance(v, (int, float)) and not isinstance(v, bool):
                lo, hi = DAILY_RANGES[k]
                out[k] = int(min(max(round(v), lo), hi))
            elif k in DAILY_CHOICES and v in DAILY_CHOICES[k]:
                out[k] = v
            elif k == "city" and isinstance(v, str) and 0 < len(v.strip()) <= 40:
                out[k] = v.strip()
            elif k == "lat" and isinstance(v, (int, float)) and -66 <= v <= 66:
                out[k] = round(float(v), 4)          # no high-latitude correction beyond this
            elif k == "lon" and isinstance(v, (int, float)) and -180 <= v <= 180:
                out[k] = round(float(v), 4)
            elif k == "quiet_hours" and isinstance(v, str) and (v == "" or _QUIET_RE.match(v)):
                out[k] = v
            elif k == "calendar_ical" and isinstance(v, str) and len(v) <= 2000:
                url = v.strip().replace("webcal://", "https://", 1)
                if url == "" or re.match(r"^https://\S+$", url):
                    out[k] = url
    return out


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    """pythonw (no console window) running agent.py."""
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(exe):
        exe = sys.executable
    return f'"{exe}" "{os.path.join(_HERE, "agent.py")}"'


def autostart_on():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, "Yobi")[0] == autostart_command()
    except OSError:
        return False


def set_autostart(on):
    """Start Yobi when you sign in to Windows (your account only). Returns the real state."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "Yobi", 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, "Yobi")
                except FileNotFoundError:
                    pass
    except OSError:
        pass
    return autostart_on()


def read_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_section(section, values):
    """Merge into config.json without touching any other setting."""
    cfg = read_config()
    cfg.setdefault(section, {}).update(values)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def downloads_folder():
    try:
        from file_ops import _resolve_common_folder
        p = _resolve_common_folder("Downloads")
        if p:
            return p
    except Exception:
        pass
    p = os.path.join(os.path.expanduser("~"), "Downloads")
    return p if os.path.isdir(p) else None


def pictures_folder():
    try:
        from file_ops import _resolve_common_folder
        p = _resolve_common_folder("Pictures")
        if p:
            return p
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Pictures")


PARTIAL_RE = re.compile(r"\.(crdownload|part|partial|download|opdownload|!ut|!qb)$", re.I)
SHOW_AFTER_S = 1.5          # a download that ends sooner never shows as "downloading"
SHELF_MAX = 24
CLIPS_MAX = 20

PRIVACY_BASE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
PRIVACY_NAMES = {
    "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "brave": "Brave", "opera": "Opera",
    "discord": "Discord", "teams": "Teams", "ms-teams": "Teams", "zoom": "Zoom", "slack": "Slack",
    "obs64": "OBS", "telegram": "Telegram", "whatsapp": "WhatsApp", "windowscamera": ("الكاميرا", "Camera"),
    "skype": "Skype", "steam": "Steam", "riotclientservices": "Riot",
}


def privacy_label(key):
    """Registry key -> a short app name."""
    k = key.replace("#", "\\")
    stem = os.path.splitext(os.path.basename(k))[0] if "\\" in k else k.split("_")[0].split(".")[-1]
    name = PRIVACY_NAMES.get(stem.lower(), stem[:20] or ("تطبيق", "An app"))
    return tr(*name) if isinstance(name, tuple) else name   # (Arabic, English) where it differs


class IslandTools:
    TICK_S = 0.4

    def __init__(self, send, daily=None, log=print):
        self._send = send
        self._daily = daily
        self._log = log
        self._stop = threading.Event()
        self._panel = threading.Event()
        cfg = read_config()
        self.cfg = dict(ISLAND_DEFAULTS, **clean_settings("island", cfg.get("island")))
        _ui["lang"] = self.cfg["lang"]
        # downloads
        self._dl = {}               # partial path -> info
        self._dl_done = {}          # id -> final path
        self._dl_folder = None
        self._dl_folder_at = 0.0
        self._dl_sent = False
        # clipboard
        self._clips = []
        self._seq = None
        self._own_seq = None
        self._image = None
        self.extras = None          # island_extras.IslandExtras, set by electron_island
        # shelf
        self._shelf = self._load_shelf()
        # privacy, fullscreen
        self._privacy = None
        self._fullscreen = None

    # ── lifecycle ─────────────────────────────────────────────
    def start(self):
        self._send_island_settings()
        threading.Thread(target=self._loop, name="island-tools", daemon=True).start()

    def stop(self):
        self._stop.set()

    def handle(self, msg):
        t = msg.get("t")
        try:
            if t == "panel":
                (self._panel.set if msg.get("open") else self._panel.clear)()
                if msg.get("open"):
                    self._send_clips()
                    self._send_shelf()
            elif t == "clip_copy":
                self._copy_clip(int(msg.get("i", -1)))
            elif t == "clip_clear":
                self._clips = []
                self._send_clips()
            elif t == "shelf_add":
                self.shelf_add([p for p in msg.get("paths", []) if isinstance(p, str)][:SHELF_MAX])
            elif t in ("shelf_open", "shelf_folder", "shelf_remove"):
                self._shelf_action(t, int(msg.get("i", -1)))
            elif t == "shelf_clear":
                self._shelf = []
                self._save_shelf()
                self._send_shelf()
            elif t in ("dl_open", "dl_folder"):
                path = self._dl_done.get(str(msg.get("id")))
                if path and os.path.exists(path):
                    self._open(path, folder=(t == "dl_folder"))
            elif t == "notice_action" and msg.get("action") == "shot_save":
                threading.Thread(target=self._save_shot, daemon=True).start()
            elif t == "settings_get":
                self._send_settings()
            elif t == "preview":
                self._preview(str(msg.get("what", "")))
            elif t == "settings_set":
                self._apply_settings(msg.get("section"), msg.get("values") or {})
        except (TypeError, ValueError):
            pass

    def _loop(self):
        n = 0
        while not self._stop.wait(self.TICK_S):
            n += 1
            for step, every in ((self._clipboard_tick, 1), (self._downloads_tick, 3),
                                (self._fullscreen_tick, 3), (self._privacy_tick, 5)):
                if n % every == 0:
                    try:
                        step()
                    except Exception as e:
                        self._log(f"⚠️ island tools: {type(e).__name__}: {e}")

    # ── settings ──────────────────────────────────────────────
    def _send_island_settings(self):
        self._send({"t": "island_settings", "values": dict(self.cfg)})

    def _send_settings(self):
        self.cfg["autostart"] = autostart_on()           # what Windows really has, not what was saved
        daily = dict(self._daily.cfg) if self._daily is not None else {}
        daily.pop("tune", None)
        self._send({"t": "settings", "island": dict(self.cfg), "daily": daily,
                    "themes": list(THEMES), "methods": list(DAILY_CHOICES["method"]),
                    "cities": [{"name": c[0], "lat": c[1], "lon": c[2], "method": c[3]} for c in CITIES]})

    def _apply_settings(self, section, values):
        if section not in ("island", "daily"):
            return
        good = clean_settings(section, values)
        if not good:
            self._send_settings()
            return
        save_section(section, good)
        if section == "island":
            if "autostart" in good:
                good["autostart"] = set_autostart(good["autostart"])
            self.cfg.update(good)
            _ui["lang"] = self.cfg["lang"]
            self._send_island_settings()
            if not self.cfg["clipboard_history"]:
                self._clips = []
            if not self.cfg["privacy_dots"]:
                self._privacy = None
                self._send({"t": "privacy", "mic": [], "cam": []})
        elif self._daily is not None:
            self._daily.cfg.update(good)
            self._daily._day = None                   # recalculate prayer times now
            if self.extras is not None and ("lat" in good or "lon" in good):
                self.extras.refresh_weather()         # the weather follows the prayer location
        self._send_settings()
        self._send({"t": "settings_saved"})

    def _preview(self, what):
        """Settings' "try it" buttons: show a sample on the island now."""
        import random
        import time as _t
        if what == "reply":
            self._send({"t": "say", "text": tr("تمام، فتحت ديسكورد ✅", "Done, Discord is open ✅"), "state": "success", "chime": True})
        elif what == "adhan":
            times = getattr(self._daily, "_times", {}) or {}
            now = _t.time() * 1000
            nxt = next((k for k in ("fajr", "dhuhr", "asr", "maghrib", "isha") if times.get(k, 0) > now), "fajr")
            self._send({"t": "notice", "kind": "adhan", "prayer": nxt, "at": times.get(nxt) or int(now)})
        elif what == "reminder":
            from island_daily import reminder_notice, reminder_pool
            cfg = self._daily.cfg if self._daily else {}
            self._send(reminder_notice(random.choice(reminder_pool(cfg)), cfg.get("remind_for_s", 20)))
        elif what == "brief" and self.extras is not None:
            self._send(self.extras._brief())

    # ── fullscreen ────────────────────────────────────────────
    def _fullscreen_tick(self):
        on = False
        if self.cfg["hide_fullscreen"]:
            try:
                from island_widgets import foreground_fullscreen
                on = foreground_fullscreen()
            except Exception:
                on = False
        try:
            import ctypes
            maxed = bool(ctypes.windll.user32.IsZoomed(ctypes.windll.user32.GetForegroundWindow()))
        except Exception:
            maxed = False
        if (on, maxed) != self._fullscreen:
            self._fullscreen = (on, maxed)
            self._send({"t": "fullscreen", "on": on, "max": maxed})

    # ── downloads seen in the Downloads folder ────────────────
    def _downloads_tick(self):
        now = time.monotonic()
        if not self.cfg["downloads"]:
            if self._dl:
                self._dl = {}
                self._send({"t": "downloads", "items": []})
            return
        if self._dl_folder is None or now - self._dl_folder_at > 60:
            self._dl_folder, self._dl_folder_at = downloads_folder(), now
        if not self._dl_folder:
            return
        seen = {}
        try:
            for e in os.scandir(self._dl_folder):
                if PARTIAL_RE.search(e.name) and e.is_file():
                    # os.stat, not the cached directory entry: a browser holding the file open
                    # doesn't update the entry's size until it closes it
                    seen[e.path] = os.stat(e.path).st_size
        except OSError:
            return
        for p, size in seen.items():
            d = self._dl.get(p)
            if d is None:
                self._dl[p] = {"id": f"d{abs(hash((p, now))) % 10**9}", "first": now, "size": size,
                               "at": now, "speed": 0.0}
                continue
            dt_s = max(0.1, now - d["at"])
            rate = max(0.0, (size - d["size"]) / dt_s)
            d["speed"] = rate if d["speed"] == 0 else d["speed"] * 0.6 + rate * 0.4
            d["size"], d["at"] = size, now
        for p in [p for p in self._dl if p not in seen]:
            d = self._dl.pop(p)
            final = PARTIAL_RE.sub("", p)
            # finished = the partial file left a real file behind; otherwise it was cancelled or renamed
            if os.path.isfile(final):
                self._dl_done[d["id"]] = final
                self._send({"t": "notice", "kind": "download_done", "id": d["id"],
                            "name": os.path.basename(final), "size": os.path.getsize(final)})
                if self.extras is not None:
                    self.extras.note(tr(f"اتحمّل {os.path.basename(final)}", f"Downloaded {os.path.basename(final)}"))
        items = [{"id": d["id"], "name": PARTIAL_RE.sub("", os.path.basename(p)),
                  "bytes": d["size"], "speed": round(d["speed"])}
                 for p, d in self._dl.items() if now - d["first"] >= SHOW_AFTER_S]
        if items or self._dl_sent:
            self._send({"t": "downloads", "items": items})
        self._dl_sent = bool(items)

    # ── clipboard: text history and copied images ─────────────
    def _clipboard_tick(self):
        import ctypes
        seq = ctypes.windll.user32.GetClipboardSequenceNumber()
        if seq == self._seq:
            return
        first = self._seq is None
        self._seq = seq
        if first or seq == self._own_seq:        # what was there before Yobi started, or our own copy
            return
        want_text = self.cfg["clipboard_history"]
        want_smart = self.cfg.get("smart_clipboard", True)
        want_image = self.cfg["screenshot_toast"]
        if not (want_text or want_smart or want_image):
            return
        kind, text = self._read_clipboard()
        if kind == "text" and text.strip():
            if want_text:
                self._clips = [text] + [c for c in self._clips if c != text]
                self._clips = self._clips[:CLIPS_MAX]
                self._send_clips()
            if want_smart:
                from island_extras import classify
                smart = classify(text)
                if smart:                                # a link, a colour, a sum, a long text
                    self._send({"t": "notice", "kind": "smart", "what": smart.pop("kind"), **smart})
        elif kind == "image" and want_image:
            self._image_notice()

    @staticmethod
    def _read_clipboard():
        """('text', str) | ('image', None) | (None, None); private copies count as nothing."""
        import win32clipboard as wc
        import win32con
        for _ in range(3):
            try:
                wc.OpenClipboard()
                break
            except Exception:
                time.sleep(0.05)
        else:
            return None, None
        try:
            if wc.IsClipboardFormatAvailable(wc.RegisterClipboardFormat("ExcludeClipboardContentFromMonitorProcessing")):
                return None, None
            if wc.IsClipboardFormatAvailable(wc.RegisterClipboardFormat("Clipboard Viewer Ignore")):
                return None, None
            hist = wc.RegisterClipboardFormat("CanIncludeInClipboardHistory")
            if wc.IsClipboardFormatAvailable(hist):
                data = wc.GetClipboardData(hist)
                if isinstance(data, (bytes, bytearray)) and data[:4] == b"\0\0\0\0":
                    return None, None
            if wc.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return "text", str(wc.GetClipboardData(win32con.CF_UNICODETEXT))[:4000]
            if wc.IsClipboardFormatAvailable(win32con.CF_DIB):
                return "image", None
        except Exception:
            return None, None
        finally:
            try:
                wc.CloseClipboard()
            except Exception:
                pass
        return None, None

    def _image_notice(self):
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
        except Exception:
            return
        if img is None or not hasattr(img, "size"):
            return
        self._image = img.copy()
        from island_widgets import art_data_url
        import io
        thumb = img.convert("RGB")
        thumb.thumbnail((240, 140))
        buf = io.BytesIO()
        thumb.save(buf, "PNG")
        self._send({"t": "notice", "kind": "screenshot", "w": img.size[0], "h": img.size[1],
                    "thumb": art_data_url(buf.getvalue(), size=240)})

    def _save_shot(self):
        img = self._image
        if img is None:
            return
        folder = os.path.join(pictures_folder(), "Yobi")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, dt.datetime.now().strftime("لقطة-%Y%m%d-%H%M%S.png"))
        img.save(path, "PNG")
        self.shelf_add([path])
        self._send({"t": "say", "text": tr("حفظت اللقطة على الرف 📌", "Saved the screenshot to the shelf 📌"), "state": "success", "chime": False})

    def _send_clips(self):
        self._send({"t": "clips", "enabled": self.cfg["clipboard_history"],
                    "items": [c[:300] for c in self._clips]})

    def _copy_clip(self, i):
        if not (0 <= i < len(self._clips)):
            return
        self.copy_text(self._clips[i])

    def copy_text(self, text):
        import ctypes
        import win32clipboard as wc
        import win32con
        try:
            wc.OpenClipboard()
            wc.EmptyClipboard()
            wc.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            wc.CloseClipboard()
        self._own_seq = ctypes.windll.user32.GetClipboardSequenceNumber()
        if self.cfg["clipboard_history"]:
            self._clips = [text] + [c for c in self._clips if c != text]
            self._send_clips()

    # ── shelf: paths of files you dropped on the island ───────
    def _load_shelf(self):
        try:
            with open(SHELF_PATH, encoding="utf-8") as f:
                items = json.load(f)
            return [p for p in items if isinstance(p, str) and os.path.exists(p)][:SHELF_MAX]
        except Exception:
            return []

    def _save_shelf(self):
        try:
            with open(SHELF_PATH, "w", encoding="utf-8") as f:
                json.dump(self._shelf, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def shelf_add(self, paths):
        new = list(dict.fromkeys(os.path.abspath(p) for p in paths if os.path.isabs(p) and os.path.exists(p)))
        if not new:
            return
        self._shelf = (new + [p for p in self._shelf if p not in new])[:SHELF_MAX]
        self._save_shelf()
        self._send_shelf()

    def _shelf_action(self, t, i):
        if not (0 <= i < len(self._shelf)):
            return
        path = self._shelf[i]
        if t == "shelf_remove" or not os.path.exists(path):
            self._shelf.pop(i)
            self._save_shelf()
            self._send_shelf()
            return
        self._open(path, folder=(t == "shelf_folder"))

    def _send_shelf(self):
        self._shelf = [p for p in self._shelf if os.path.exists(p)]
        self._send({"t": "shelf", "items": [
            {"i": i, "name": os.path.basename(p) or p, "path": p, "dir": os.path.isdir(p)}
            for i, p in enumerate(self._shelf)]})

    @staticmethod
    def _open(path, folder=False):
        if folder:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)

    # ── microphone / camera in use by other apps ──────────────
    def _privacy_tick(self):
        if not self.cfg["privacy_dots"]:
            return
        state = {"mic": self._in_use("microphone"), "cam": self._in_use("webcam")}
        if state != self._privacy:
            self._privacy = state
            self._send({"t": "privacy", **state})

    @staticmethod
    def _in_use(device):
        import winreg
        own = {os.path.normcase(p).replace("\\", "#") for p in (sys.executable, sys.executable.replace("python.exe", "pythonw.exe"))}
        names = []

        def check(root, sub):
            try:
                with winreg.OpenKey(root, sub) as k:
                    start = winreg.QueryValueEx(k, "LastUsedTimeStart")[0]
                    stop = winreg.QueryValueEx(k, "LastUsedTimeStop")[0]
                    return start > 0 and stop == 0
            except OSError:
                return False

        base = f"{PRIVACY_BASE}\\{device}"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as k:
                i = 0
                while True:
                    try:
                        app = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    if app == "NonPackaged":
                        with winreg.OpenKey(k, app) as np_:
                            j = 0
                            while True:
                                try:
                                    exe = winreg.EnumKey(np_, j)
                                except OSError:
                                    break
                                j += 1
                                if os.path.normcase(exe) in own:
                                    continue          # Yobi's own always-on microphone
                                if check(winreg.HKEY_CURRENT_USER, f"{base}\\NonPackaged\\{exe}"):
                                    names.append(privacy_label(exe))
                    elif check(winreg.HKEY_CURRENT_USER, f"{base}\\{app}"):
                        names.append(privacy_label(app))
        except OSError:
            pass
        return sorted(set(names))
