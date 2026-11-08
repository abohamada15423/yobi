# -*- coding: utf-8 -*-
"""Yobi Dynamic Island v8 — Obsidian Bioluminescence & Evolved Cartoon Edition."""
import json
import math
import os
import platform
import random
import sys
import threading
import time
import tkinter as tk
from collections import OrderedDict
from tkinter import Menu
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

try:
    import customtkinter as ctk
    _HAS_CTK = True
except ImportError:
    _HAS_CTK = False

try:
    from PIL import features as _pil_features
    _HAS_RAQM = bool(_pil_features.check("raqm"))
except Exception:
    _HAS_RAQM = False
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_BIDI = True
except ImportError:
    _HAS_BIDI = False
try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False
try:
    import sounddevice as sd
    _HAS_SD = True
except ImportError:
    _HAS_SD = False
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

CURRENT_OS = platform.system().lower()
IS_WIN = CURRENT_OS == "windows"
_HERE = os.path.dirname(os.path.abspath(__file__))
PREFS_PATH = os.path.join(_HERE, "ui_prefs.json")
KEY_COLOR = "#010203"          # colour-key for fallback transparency
KEY_RGB = (1, 2, 3)

THEMES = {
    "dark": {
        "idle_hi": "#38bdf8", "idle_lo": "#0c4a6e",
        "listen_bg": "#0a1e2a", "listen_acc": "#38bdf8",
        "think_bg": "#1c1308", "think_acc": "#fbbf24",
        "info_bg": "#130e22", "info_acc": "#a78bfa",
        "ok_bg": "#0a1c12", "ok_acc": "#34d399",
        "err_bg": "#1e0a0a", "err_acc": "#f87171",
        "border": "#222b3d", "text": "#f8fafc", "text_dim": "#94a3b8",
        "history_bg": "#080a0f", "card_bg": "#121722", "card_border": "#222b3d",
    },
    "light": {
        "idle_hi": "#22c55e", "idle_lo": "#86efac",
        "listen_bg": "#e0f2fe", "listen_acc": "#0284c7",
        "think_bg": "#fef3c7", "think_acc": "#d97706",
        "info_bg": "#ede9fe", "info_acc": "#7c3aed",
        "ok_bg": "#dcfce7", "ok_acc": "#16a34a",
        "err_bg": "#fee2e2", "err_acc": "#dc2626",
        "border": "#cbd5e1", "text": "#0f172a", "text_dim": "#64748b",
        "history_bg": "#f8fafc", "card_bg": "#ffffff", "card_border": "#e2e8f0",
    },
}

STYLES = {
    "idle":       ("#38bdf8", "#0c4a6e", "#e0f2fe", 0.25),
    "peek":       ("#38bdf8", "#075985", "#e0f2fe", 0.34),
    "actions":    ("#38bdf8", "#0369a1", "#bae6fd", 0.40),
    "listening":  ("#38bdf8", "#0284c7", "#e0f2fe", 0.72),
    "speaking":   ("#2dd4bf", "#0f766e", "#ccfbf1", 0.60),
    "thinking":   ("#fbbf24", "#b45309", "#fef3c7", 0.60),
    "executing":  ("#fb923c", "#c2410c", "#ffedd5", 0.60),
    "suggesting": ("#f472b6", "#be185d", "#fce7f3", 0.60),
    "account":    ("#818cf8", "#4338ca", "#e0e7ff", 0.60),
    "recording":  ("#fb7185", "#be123c", "#ffe4e6", 0.65),
    "success":    ("#34d399", "#047857", "#d1fae5", 0.62),
    "error":      ("#f87171", "#b91c1c", "#fee2e2", 0.72),
    "info":       ("#a78bfa", "#6d28d9", "#ede9fe", 0.54),
}

DEFAULT_TEXT = {
    "listening": "سامعك.. اتكلم 🎤",
    "thinking": "بفكر...",
    "executing": "بنفذ...",
    "account": "بجهزلك الحساب...",
    "recording": "بسجل...",
    "suggesting": "عندي فكرة ليك 💡",
}

STATE_ALIASES = {
    "hide": "idle", "hidden": "idle", "idle": "idle",
    "listen": "listening", "think": "thinking",
    "execute": "executing", "working": "executing", "doing": "executing",
    "speak": "speaking", "talking": "speaking",
    "suggest": "suggesting", "suggestion": "suggesting",
    "login": "account", "auth": "account",
    "record": "recording",
    "ok": "success", "done": "success",
    "fail": "error", "warning": "info", "warn": "info",
}

HISTORY_KIND = {"success": "success", "error": "error"}
EYE = (8, 11, 18)
TEXT_MAIN = (248, 250, 252)
TEXT_DIM = (148, 163, 184)
BASE_TOP = np.array([12, 16, 26], dtype=np.float32)
BASE_BOT = np.array([4, 6, 11], dtype=np.float32)


def _prefers_reduced_motion():
    if not IS_WIN:
        return False
    try:
        import ctypes
        anim = ctypes.c_bool(True)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(anim), 0)
        return not bool(anim.value)
    except Exception:
        return False


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _rgba(c, a=255):
    return (int(c[0]), int(c[1]), int(c[2]), int(max(0, min(255, a))))


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _smooth(t):
    t = _clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _detect_system_theme():
    if not IS_WIN:
        return "dark"
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if val == 1 else "dark"
    except Exception:
        return "dark"


def _load_prefs():
    if os.path.exists(PREFS_PATH):
        try:
            with open(PREFS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_prefs(prefs):
    try:
        with open(PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _enable_dpi_awareness():
    if not IS_WIN:
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class MicLevelReader:
    """Smoothed 0..1 microphone level. Falls back to a simulated level."""
    def __init__(self, interval=0.04, smooth=0.35):
        self._interval = interval
        self._smooth = smooth
        self._level = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._mode = "real" if _HAS_SD else "simulated"

    def start(self):
        try:
            import audio_io
            if audio_io.get_audio_engine() is not None:
                return
        except Exception:
            pass
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def level(self):
        try:
            import audio_io
            eng = audio_io.get_audio_engine()
            if eng is not None:
                return min(1.0, float(eng.level) * 1.8)
        except Exception:
            pass
        return self._level

    def _loop(self):
        if self._mode == "real":
            try:
                with sd.InputStream(channels=1, callback=self._on_audio):
                    while not self._stop.is_set():
                        time.sleep(self._interval)
                return
            except Exception:
                self._mode = "simulated"
        while not self._stop.is_set():
            t = time.time()
            target = 0.25 + 0.55 * abs(math.sin(t * 2.3)) * (0.6 + 0.4 * math.sin(t * 7.1))
            self._level += (target - self._level) * 0.2
            time.sleep(self._interval)
        self._level = 0.0

    def _on_audio(self, indata, frames, time_info, status):
        try:
            rms = float(np.sqrt((indata ** 2).mean()))
            target = min(1.0, rms * 5.0)
            self._level += (target - self._level) * self._smooth
        except Exception:
            pass


_SOFT_CACHE = {}
_last_soft = [0.0, ""]
_SOFT_NOTES = {
    "reply":   [(880, 70), (1175, 120)],
    "ask":     [(784, 70), (988, 70), (1175, 130)],
    "success": [(1047, 60), (1319, 110)],
    "error":   [(523, 110), (440, 170)],
    "info":    [(988, 110)],
}


def _soft_wav(kind, volume=0.16, rate=22050):
    """Build (and cache) a tiny WAV with soft sine notes."""
    if kind in _SOFT_CACHE:
        return _SOFT_CACHE[kind]
    import struct
    frames = bytearray()
    for freq, ms in _SOFT_NOTES.get(kind, _SOFT_NOTES["info"]):
        n = int(rate * ms / 1000)
        att = max(1, int(rate * 0.008))
        for i in range(n):
            env = min(1.0, i / att) * math.exp(-3.2 * i / n)
            v = math.sin(2 * math.pi * freq * i / rate) * env * volume
            frames += struct.pack("<h", int(v * 32767))
        frames += b"\x00\x00" * int(rate * 0.012)
    data = bytes(frames)
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
           struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) +
           b"data" + struct.pack("<I", len(data)))
    _SOFT_CACHE[kind] = hdr + data
    return _SOFT_CACHE[kind]


def _play_soft(kind):
    """Very soft notification sound. Repeats within 0.6 s are dropped."""
    if not _HAS_WINSOUND:
        return
    now = time.perf_counter()
    if now - _last_soft[0] < 0.6:
        return
    _last_soft[0], _last_soft[1] = now, kind
    try:
        wav = _soft_wav(kind)
    except Exception:
        return

    def _run():
        try:
            winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _play_notify(kind):
    _play_soft(kind)


class Spring:
    """Damped spring. Low damping = elastic overshoot."""
    __slots__ = ("v", "t", "vel", "k", "c")

    def __init__(self, v=0.0, k=210.0, c=19.0):
        self.v = float(v)
        self.t = float(v)
        self.vel = 0.0
        self.k = k
        self.c = c

    def step(self, dt):
        a = self.k * (self.t - self.v) - self.c * self.vel
        self.vel += a * dt
        self.v += self.vel * dt

    def settled(self, eps=0.3):
        return abs(self.t - self.v) < eps and abs(self.vel) < eps * 4

    def snap(self, v):
        self.v = self.t = float(v)
        self.vel = 0.0


def _is_emoji(ch):
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF
            or 0x2300 <= cp <= 0x23FF or 0x2B00 <= cp <= 0x2BFF
            or cp in (0x2139, 0x203C, 0x2049, 0x3030, 0x303D))


_EMOJI_JOINERS = {0xFE0F, 0xFE0E, 0x200D, 0x20E3}


def _is_rtl(s):
    for ch in s:
        if "\u0590" <= ch <= "\u08FF" or "\uFB1D" <= ch <= "\uFEFC":
            return True
    return False


class TextEngine:
    def __init__(self):
        win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        plex = "/usr/local/share/fonts/google/ibmplexsansarabic"
        self._paths = {
            "regular": self._first([
                os.path.join(win, "segoeui.ttf"), os.path.join(win, "tahoma.ttf"),
                os.path.join(plex, "IBMPlexSansArabic-Regular.ttf"),
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]),
            "semibold": self._first([
                os.path.join(win, "seguisb.ttf"), os.path.join(win, "segoeuib.ttf"),
                os.path.join(win, "tahomabd.ttf"),
                os.path.join(plex, "IBMPlexSansArabic-SemiBold.ttf"),
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]),
        }
        self._emoji_path = self._first([
            os.path.join(win, "seguiemj.ttf"),
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"])
        self._emoji_fixed = None
        self._fonts = {}
        self._cache = OrderedDict()
        self._emoji_cache = {}
        self._layout = (ImageFont.Layout.RAQM if _HAS_RAQM
                        else ImageFont.Layout.BASIC)

    @staticmethod
    def _first(paths):
        for p in paths:
            if p and os.path.exists(p):
                return p
        return None

    def font(self, size, weight="regular"):
        key = (int(round(size)), weight)
        f = self._fonts.get(key)
        if f is None:
            path = self._paths.get(weight) or self._paths.get("regular")
            try:
                f = ImageFont.truetype(path, key[0], layout_engine=self._layout)
            except Exception:
                try:
                    f = ImageFont.load_default(key[0])
                except Exception:
                    f = ImageFont.load_default()
            self._fonts[key] = f
        return f

    @staticmethod
    def _runs(s):
        runs, cur, cur_e = [], "", None
        for ch in s:
            cp = ord(ch)
            if cp in _EMOJI_JOINERS or 0x1F3FB <= cp <= 0x1F3FF:
                if cur_e:
                    continue
                cur += ch
                continue
            e = _is_emoji(ch)
            if cur_e is None:
                cur_e = e
            if e != cur_e:
                runs.append((cur_e, cur))
                cur, cur_e = "", e
            cur += ch
        if cur:
            runs.append((cur_e, cur))
        return runs

    def _visual(self, s, rtl):
        if _HAS_RAQM or not _HAS_BIDI or not rtl:
            return s
        try:
            return get_display(arabic_reshaper.reshape(s), base_dir="R")
        except Exception:
            return s

    def _text_len(self, s, f, rtl):
        if not s:
            return 0.0
        try:
            if _HAS_RAQM:
                return f.getlength(s, direction="rtl" if rtl else "ltr")
            return f.getlength(self._visual(s, rtl))
        except Exception:
            return f.getlength(s)

    def measure(self, s, size, weight="regular"):
        f = self.font(size, weight)
        rtl = _is_rtl(s)
        w = 0.0
        for is_e, run in self._runs(s):
            if is_e:
                if self._emoji_path:
                    w += len(run) * size * 1.22
            else:
                w += self._text_len(run, f, rtl)
        return w

    def _emoji_img(self, ch, px):
        key = (ch, px)
        im = self._emoji_cache.get(key)
        if im is not None:
            return im
        im = None
        try:
            if self._emoji_fixed is None:
                try:
                    ImageFont.truetype(self._emoji_path, px)
                    self._emoji_fixed = False
                except OSError:
                    self._emoji_fixed = True
            fsize = 109 if self._emoji_fixed else px
            f = ImageFont.truetype(self._emoji_path, fsize)
            canvas = Image.new("RGBA", (int(fsize * 1.6), int(fsize * 1.6)), (0, 0, 0, 0))
            ImageDraw.Draw(canvas).text((int(fsize * 0.1), int(fsize * 0.1)), ch,
                                        font=f, embedded_color=True)
            bb = canvas.getbbox()
            if bb:
                canvas = canvas.crop(bb)
                scale = (px * 1.08) / max(canvas.size)
                canvas = canvas.resize((max(1, int(canvas.width * scale)),
                                        max(1, int(canvas.height * scale))),
                                       Image.LANCZOS)
                im = canvas
        except Exception:
            im = None
        self._emoji_cache[key] = im
        return im

    def wrap(self, text, size, weight, max_w, max_lines):
        out = []
        for para in str(text).split("\n"):
            words = para.split(" ")
            line = ""
            for w in words:
                cand = (line + " " + w) if line else w
                if self.measure(cand, size, weight) <= max_w or not line:
                    line = cand
                else:
                    out.append(line)
                    line = w
            out.append(line)
        out = [l for l in out if l.strip()] or [""]
        if len(out) > max_lines:
            out = out[:max_lines]
            last = out[-1]
            while last and self.measure(last + "…", size, weight) > max_w:
                last = last[:-1]
            out[-1] = last.rstrip() + "…"
        fixed = []
        for l in out:
            while l and self.measure(l, size, weight) > max_w * 1.02:
                l = l[:-2] + "…" if len(l) > 2 else l[:-1]
            fixed.append(l)
        return fixed

    def block(self, text, size, weight="regular", max_w=300, max_lines=2,
              color=TEXT_MAIN, align="right", line_gap=1.38):
        """Return an RGBA image of wrapped text (cached)."""
        key = (text, int(size * 10), weight, int(max_w), max_lines, color, align)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        lines = self.wrap(text, size, weight, max_w, max_lines)
        widths = [self.measure(l, size, weight) for l in lines]
        lh = size * line_gap
        w = int(math.ceil(max(widths + [1]))) + 4
        h = int(math.ceil(lh * len(lines))) + 2
        f = self.font(size, weight)
        mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(mask)
        emojis = []
        for i, line in enumerate(lines):
            rtl = _is_rtl(line)
            lw = widths[i]
            if align == "right":
                x0 = w - 2 - lw
            elif align == "center":
                x0 = (w - lw) / 2
            else:
                x0 = 2
            ymid = lh * i + lh / 2 + 1
            runs = self._runs(line)
            rw = []
            for is_e, run in runs:
                if is_e:
                    rw.append(len(run) * size * 1.22 if self._emoji_path else 0)
                else:
                    rw.append(self._text_len(run, f, rtl))
            if rtl:
                cursor = x0 + lw
                order = [(r, wd, -1) for r, wd in zip(runs, rw)]
            else:
                cursor = x0
                order = [(r, wd, 1) for r, wd in zip(runs, rw)]
            for (is_e, run), wd, sign in order:
                px = cursor - wd if sign < 0 else cursor
                if is_e:
                    if self._emoji_path:
                        ex = px
                        for ch in (reversed(run) if sign < 0 else run):
                            emojis.append((ch, ex + size * 0.07, ymid))
                            ex += size * 1.22
                elif run.strip():
                    try:
                        if _HAS_RAQM:
                            md.text((px, ymid), run, font=f, fill=255, anchor="lm",
                                    direction="rtl" if rtl else "ltr")
                        else:
                            md.text((px, ymid), self._visual(run, rtl), font=f,
                                    fill=255, anchor="lm")
                    except Exception:
                        md.text((px, ymid), run, font=f, fill=255, anchor="lm")
                cursor = cursor - wd if sign < 0 else cursor + wd
        img = Image.new("RGBA", (w, h), _rgba(color, 0))
        img.putalpha(mask)
        for ch, ex, ey in emojis:
            em = self._emoji_img(ch, int(size * 1.08))
            if em is not None:
                _blit(img, em, int(ex), int(ey - em.height / 2))
        res = (img, len(lines))
        self._cache[key] = res
        if len(self._cache) > 180:
            self._cache.popitem(last=False)
        return res


def _blit(dst, src, x, y, alpha=1.0):
    """alpha_composite with clipping and an extra opacity factor."""
    if src is None or alpha <= 0.01:
        return
    x, y = int(round(x)), int(round(y))
    sx0 = max(0, -x)
    sy0 = max(0, -y)
    sx1 = min(src.width, dst.width - x)
    sy1 = min(src.height, dst.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    part = src if (sx0, sy0, sx1, sy1) == (0, 0, src.width, src.height) \
        else src.crop((sx0, sy0, sx1, sy1))
    if alpha < 0.999:
        part = part.copy()
        a = part.getchannel("A").point([int(i * alpha) for i in range(256)])
        part.putalpha(a)
    dst.alpha_composite(part, dest=(x + sx0, y + sy0))


class _LayeredWindow:
    def __init__(self, tkwin):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        u32 = ctypes.windll.user32
        g32 = ctypes.windll.gdi32
        self.u32, self.g32 = u32, g32

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                        ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

        self.BITMAPINFO, self.BLENDFUNCTION = BITMAPINFO, BLENDFUNCTION
        self.POINT, self.SIZE = wintypes.POINT, wintypes.SIZE
        u32.GetDC.restype = wintypes.HDC
        u32.GetDC.argtypes = [wintypes.HWND]
        u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        u32.GetAncestor.restype = wintypes.HWND
        u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u32.GetWindowLongW.restype = wintypes.LONG
        u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.SetWindowLongW.restype = wintypes.LONG
        u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        u32.UpdateLayeredWindow.restype = wintypes.BOOL
        u32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.HDC, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD]
        g32.CreateCompatibleDC.restype = wintypes.HDC
        g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        g32.CreateDIBSection.restype = wintypes.HBITMAP
        g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                         ctypes.POINTER(ctypes.c_void_p),
                                         wintypes.HANDLE, wintypes.DWORD]
        g32.SelectObject.restype = wintypes.HGDIOBJ
        g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        g32.DeleteDC.argtypes = [wintypes.HDC]
        tkwin.update_idletasks()
        self.hwnd = u32.GetAncestor(tkwin.winfo_id(), 2) or tkwin.winfo_id()
        ex = u32.GetWindowLongW(self.hwnd, -20)
        u32.SetWindowLongW(self.hwnd, -20, ex | 0x00080000 | 0x00000080)  # LAYERED|TOOLWINDOW
        self._size = None
        self._hdc = None
        self._bmp = None
        self._old = None
        self._bits = None

    def _ensure(self, w, h):
        if self._size == (w, h):
            return
        self.close()
        ct = self.ct
        screen = self.u32.GetDC(None)
        self._hdc = self.g32.CreateCompatibleDC(screen)
        self.u32.ReleaseDC(None, screen)
        bmi = self.BITMAPINFO()
        bmi.bmiHeader.biSize = ct.sizeof(bmi.bmiHeader)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = ct.c_void_p()
        self._bmp = self.g32.CreateDIBSection(self._hdc, ct.byref(bmi), 0,
                                              ct.byref(bits), None, 0)
        if not self._bmp:
            raise OSError("CreateDIBSection failed")
        self._old = self.g32.SelectObject(self._hdc, self._bmp)
        self._bits = bits
        self._size = (w, h)

    def update(self, img, x, y):
        w, h = img.size
        self._ensure(w, h)
        arr = np.asarray(img, dtype=np.uint8)
        a = arr[..., 3:4].astype(np.uint16)
        pm = ((arr[..., :3].astype(np.uint16) * a + 127) // 255).astype(np.uint8)
        bgra = np.empty((h, w, 4), dtype=np.uint8)
        bgra[..., 0] = pm[..., 2]
        bgra[..., 1] = pm[..., 1]
        bgra[..., 2] = pm[..., 0]
        bgra[..., 3] = arr[..., 3]
        buf = bgra.tobytes()
        self.ct.memmove(self._bits, buf, len(buf))
        blend = self.BLENDFUNCTION(0, 0, 255, 1)
        pt = self.POINT(int(x), int(y))
        sz = self.SIZE(w, h)
        src = self.POINT(0, 0)
        screen = self.u32.GetDC(None)
        ok = self.u32.UpdateLayeredWindow(self.hwnd, screen, self.ct.byref(pt),
                                          self.ct.byref(sz), self._hdc,
                                          self.ct.byref(src), 0,
                                          self.ct.byref(blend), 2)
        self.u32.ReleaseDC(None, screen)
        if not ok:
            raise OSError("UpdateLayeredWindow failed")

    def set_click_through(self, pass_through: bool):
        if getattr(self, "_pass_through", None) == pass_through:
            return
        self._pass_through = pass_through
        try:
            ex = self.u32.GetWindowLongW(self.hwnd, -20)
            if pass_through:
                ex |= 0x00000020
            else:
                ex &= ~0x00000020
            self.u32.SetWindowLongW(self.hwnd, -20, ex)
        except Exception:
            pass

    def close(self):
        try:
            if self._hdc and self._old:
                self.g32.SelectObject(self._hdc, self._old)
            if self._bmp:
                self.g32.DeleteObject(self._bmp)
            if self._hdc:
                self.g32.DeleteDC(self._hdc)
        except Exception:
            pass
        self._hdc = self._bmp = self._old = self._bits = None
        self._size = None


class DynamicIsland(tk.Tk):
    """Top-centre Dynamic Island v8 with an evolved cartoon Yobi character."""
    WIN_W = 680
    WIN_H = 390
    TOP = 14
    FPS = 60
    IDLE_FPS = 18
    MAX_W = 470
    SLEEP_AFTER = 150.0
    QUICK_ACTIONS = [
        ("🎤", "استمع", "listen"),
        ("💬", "محادثة", "chat"),
        ("⌘", "الأوامر", "palette"),
        ("🚀", "الرامات", "ram"),
        ("💻", "مذاكرة", "study"),
        ("💧", "مياه +1", "water"),
        ("📸", "لقطة شاشة", "screenshot"),
        ("⚙️", "إعدادات", "settings"),
    ]

    def __init__(self):
        _enable_dpi_awareness()
        super().__init__()
        self.title("Yobi")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            S = self.winfo_fpixels("1i") / 96.0
        except Exception:
            S = 1.0
        self._S = S = _clamp(S, 1.0, 3.0)
        self._W = int(self.WIN_W * S)
        self._H = int(self.WIN_H * S)
        self._top = int(self.TOP * S)
        self._prefs = _load_prefs()
        theme_choice = self._prefs.get("theme", "auto")
        self._theme_pref = theme_choice
        if theme_choice == "auto":
            theme_choice = _detect_system_theme()
        self._theme_name = theme_choice if theme_choice in THEMES else "dark"
        self._PAL = dict(THEMES[self._theme_name])
        self._sounds = bool(self._prefs.get("sounds", True))
        self._text_engine = TextEngine()
        sw = self.winfo_screenwidth()
        dx = (sw - self._W) // 2
        x = self._prefs.get("island_x", dx)
        y = self._prefs.get("island_y", 0)
        x, y = self._valid_pos(x, y, dx)
        self._win_x, self._win_y = x, y
        self.geometry(f"{self._W}x{self._H}+{x}+{y}")
        self.configure(bg=KEY_COLOR)
        self._canvas = tk.Canvas(self, width=self._W, height=self._H, bg=KEY_COLOR,
                                 highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._img_item = self._canvas.create_image(0, 0, anchor="nw")
        self._photo = None
        self._layered = None
        if IS_WIN and self._prefs.get("render", "layered") == "layered":
            try:
                self.update_idletasks()
                self.update()
                self._layered = _LayeredWindow(self)
            except Exception as e:
                print(f"⚠️ layered window unavailable, using colour-key: {e}")
                self._layered = None
        if IS_WIN and self._layered is None:
            try:
                self.attributes("-transparentcolor", KEY_COLOR)
            except Exception:
                pass
        self._fx_outside = self._layered is not None
        self._state = "idle"
        self._text = ""
        self._state_t = time.perf_counter()
        self._last_activity = time.perf_counter()
        self._hide_id = None
        self._last_notified_text = ""
        self._notification_history = []
        self._max_history = 40
        self._ui_mode = None          # None | "actions"
        self._hover = False
        self._hover_since = 0.0
        self._hover_idx = -1
        self._hover_chip = -1
        self._vs_t = 0.0
        self._wave_geom = None
        self._ar = 4.0
        self._mood_override = None
        self._suggestions = None
        self._suggestion_cb = None
        self._progress_mode = "hidden"   # hidden | det | indet
        self._progress_auto = False
        self._progress = Spring(0, 160, 24)
        self._speaking_override = None
        self._speaking = False
        self._auto_speaking = False
        self._rec_start = time.perf_counter()
        self._plan = {}
        self._hit = []
        self._island_rect = (0, 0, 0, 0)
        self._tw_full = ""
        self._tw_chars = 0
        self._tw_rate = 28.0
        self._tw_last_t = 0.0
        self._tw_active = False
        self._tw_done_t = 0.0
        self._tw_state = "info"
        self._tw_hist_text = ""
        self._ask_token = None
        self._talk_job = None
        self._companion_get = None
        self._companion_toggle = None

        # Core geometry springs
        self._mx = Spring(0, 240, 20)
        self._mw = Spring(42 * S, 270, 18)
        self._mh = Spring(42 * S, 270, 18)
        self._mr = Spring(21 * S, 270, 21)
        self._ax = Spring(0, 210, 19)
        self._aw = Spring(0, 230, 20)
        self._ah = Spring(0, 230, 20)
        self._ay = Spring(self._top, 230, 20)
        self._aa = Spring(0, 130, 18)          # aux presence 0..1
        self._shake = Spring(0, 720, 14)
        self._squash = Spring(0, 340, 11)
        self._lookx = Spring(0, 65, 11)
        self._looky = Spring(0, 65, 11)
        self._tilt = Spring(0, 140, 13)        # cartoon head tilt
        self._antenna_sway = Spring(0, 180, 9) # bouncy cartoon antenna
        self._action_springs = [Spring(0, 320, 17) for _ in range(len(self.QUICK_ACTIONS))]
        self._chip_springs = [Spring(1.0, 310, 18) for _ in range(4)]

        self._springs = ([self._mx, self._mw, self._mh, self._mr, self._ax, self._aw,
                          self._ah, self._ay, self._aa, self._shake, self._squash,
                          self._progress, self._tilt, self._antenna_sway]
                         + self._action_springs + self._chip_springs)

        st = STYLES["idle"]
        self._col_acc = _hex(st[0])
        self._col_deep = _hex(st[1])
        self._col_light = _hex(st[2])
        self._glow = st[3]
        self._blink_next = time.perf_counter() + random.uniform(2, 5)
        self._blink_t = -1.0
        self._wink_eye = -1          # -1 both blink, 0 left wink, 1 right wink
        self._look_next = time.perf_counter() + 2.0
        self._mouth = 0.0
        self._bars = [0.1] * 24
        self._vbars = [0.2] * 7
        self._particles = []
        self._ripples = []
        self._lut_cache = {}
        self._grad_cache = {}
        self._mic = MicLevelReader()
        self._history_panel = None
        self._history_visible = False
        self._chat_window = None
        self._overlay = None
        self._on_quick_action = None
        self._quick_actions = list(self.QUICK_ACTIONS)
        self._quick_actions_visible = False
        self._quick_actions_panel = None
        self._on_chat_send = lambda text: f"استلمت: {text}"
        self._press = None
        self._dragging = False
        self._click_job = None

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double)
        self.bind("<Button-2>", lambda e: self.show_inline_input())
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-3>", self._show_context_menu)
        self.bind("<Escape>", lambda e: self.set_state("hide"))
        self.bind("<Control-m>", lambda e: self._toggle_chat_window())
        self.bind("<Control-p>", lambda e: self._open_palette())
        self._inline_bar = None
        self._reduced_motion = _prefers_reduced_motion()
        self._layout()
        self._last_frame = time.perf_counter()
        self._poll_job = self.after(120, self._poll)
        self.after(16, self._tick)

    def _valid_pos(self, x, y, default_x):
        try:
            x, y = int(x), int(y)
        except Exception:
            return default_x, 0
        vx, vy, vw, vh = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        if IS_WIN:
            try:
                import ctypes
                g = ctypes.windll.user32.GetSystemMetrics
                vx, vy, vw, vh = g(76), g(77), g(78), g(79)
            except Exception:
                pass
        cx = x + self._W // 2
        if not (vx <= cx <= vx + vw and vy - 10 <= y <= vy + vh - 60):
            return default_x, 0
        return x, y

    def set_state(self, state, text="", quiet=False):
        """Public API: update visual state and optional message."""
        state = STATE_ALIASES.get(str(state or "").strip().lower(),
                                  str(state or "").strip().lower())
        text = "" if text is None else str(text)
        state = self._infer_state(state, text)
        if state not in STYLES or state in ("peek", "actions"):
            state = "info"
        if self._hide_id:
            try:
                self.after_cancel(self._hide_id)
            except Exception:
                pass
            self._hide_id = None
        prev = self._state
        now = time.perf_counter()
        self._last_activity = now
        if self._tw_active:
            self._tw_active = False
            self._speaking_override = None
        if not quiet and text and text != self._last_notified_text and state in (
                "success", "error", "info", "suggesting"):
            if self._sounds:
                _play_notify("success" if state == "success"
                             else "error" if state == "error" else "info")
            self._add_to_history(state, text)
            self._last_notified_text = text
            self._ripples.append((now, state))
        if state == "idle":
            self._last_notified_text = ""
        self._state = state
        self._text = text
        self._auto_speaking = False
        if state != prev:
            self._state_t = now
            self._squash.vel += 3.6
            self._antenna_sway.vel += random.choice([-1, 1]) * 8.5
            if state == "error":
                self._shake.vel += 920 * self._S
                self._tilt.t = -0.22
            elif state == "success":
                self._tilt.t = 0.14
                self._wink_eye = random.choice([0, 1])
                self._blink_t = now
                self._spawn_celebration(now)
            elif state == "suggesting":
                self._tilt.t = 0.18
            else:
                self._tilt.t = 0.0
            if state == "recording":
                self._rec_start = now
        if state != "idle":
            self._ui_mode = None
        if state == "listening":
            self._mic.start()
        else:
            self._mic.stop()
        if state == "executing" and self._progress_mode == "hidden":
            self._progress_mode = "indet"
            self._progress_auto = True
        elif state != "executing" and self._progress_auto:
            self._progress_mode = "hidden"
            self._progress_auto = False
        if state == "idle":
            self._progress_mode = "hidden"
            self._progress_auto = False
        if state != "suggesting":
            self._suggestions = None if prev == "suggesting" else self._suggestions
        if state == "success":
            self._schedule_hide(3800 + min(4000, len(text) * 25))
        elif state == "error":
            self._schedule_hide(4500 + min(4000, len(text) * 25))
        elif state == "suggesting":
            self._schedule_hide(14000)
        self._layout()

    def _spawn_celebration(self, now):
        """Spawn cheerful sparkle particles when Yobi succeeds."""
        if getattr(self, "_reduced_motion", False):
            return
        S = self._S
        cx = self._W / 2 + self._mx.v + self._mw.v / 2 - 26 * S
        cy = self._top + self._mh.v / 2
        cols = [(52, 211, 153), (56, 189, 248), (251, 191, 36), (167, 139, 250)]
        for _ in range(14):
            ang = random.uniform(0, 2 * math.pi)
            spd = random.uniform(35, 95) * S
            self._particles.append({
                "x": cx + random.uniform(-10, 10) * S,
                "y": cy + random.uniform(-10, 10) * S,
                "vx": math.cos(ang) * spd,
                "vy": math.sin(ang) * spd - 20 * S,
                "age": 0.0,
                "life": random.uniform(0.55, 1.05),
                "size": random.uniform(1.5, 3.0) * S,
                "col": random.choice(cols),
                "star": True,
            })

    def set_progress(self, value):
        """0..1 determinate, >1 indeterminate, <0 hidden."""
        try:
            v = float(value)
        except Exception:
            return
        self._progress_auto = False
        if v < 0:
            self._progress_mode = "hidden"
        elif v > 1.0:
            self._progress_mode = "indet"
        else:
            if self._progress_mode != "det":
                self._progress.snap(0)
            self._progress_mode = "det"
            self._progress.t = v
        self._layout()

    def set_suggestions(self, items, callback=None):
        """Show clickable suggestion chips (list of str or (label, id))."""
        norm = []
        for it in items or []:
            if isinstance(it, (tuple, list)) and len(it) >= 2:
                norm.append((str(it[0]), it[1]))
            else:
                norm.append((str(it), str(it)))
        self._suggestions = norm[:4] or None
        self._suggestion_cb = callback
        if self._state == "suggesting":
            self._layout()

    def set_speaking(self, speaking):
        """True/False to force the talking animation, None = auto (tts_engine)."""
        self._speaking_override = speaking

    SAY_MAX = 230

    def say(self, text, state=None, chime=True):
        """Yobi 'talks' by writing: the text types out with a talking cartoon mouth."""
        full = " ".join(str(text or "").split())
        if not full:
            return
        now = time.perf_counter()
        if state:
            st = STATE_ALIASES.get(str(state).strip().lower(), str(state).strip().lower())
        else:
            st = self._state if self._state in ("success", "error", "info") else "info"
        if st not in ("success", "error", "info"):
            st = "info"
        shown = full if len(full) <= self.SAY_MAX else full[:self.SAY_MAX - 1].rstrip() + "…"
        if (self._tw_full and shown != self._tw_full and shown.startswith(self._tw_full)
                and self._state == st and (self._tw_active or now - self._tw_done_t < 3.0)):
            self._tw_full = shown
            if self._history_tail_is(self._tw_hist_text):
                self._notification_history[-1]["text"] = full
                self._tw_hist_text = full
            if not self._tw_active:
                self._cancel_hide()
                self._tw_active = True
                self._tw_last_t = now
                self._speaking_override = True
            return
        if self._text == shown and self._state == st and not self._tw_active:
            if chime and self._sounds:
                _play_soft("reply")
            self._talk_for(min(2.5, 0.6 + len(shown) / 40.0))
            return
        self.set_state(st, "▍", quiet=True)
        if chime and self._sounds:
            _play_soft("reply" if st == "info" else st)
        self._add_to_history(st, full)
        self._tw_hist_text = full
        self._last_notified_text = shown
        self._ripples.append((now, st))
        self._tw_full = shown
        self._tw_chars = 0
        self._tw_rate = max(30.0, len(shown) / 3.5)
        self._tw_last_t = now
        self._tw_active = True
        self._tw_done_t = 0.0
        self._tw_state = st
        self._speaking_override = True

    def typewriter_text(self, text, state="info"):
        """Backward-compatible name for say()."""
        self.say(text, state=state)

    def ask(self, question, options=None, callback=None, timeout_ms=30000, chime=True):
        """Question with clickable answer buttons."""
        opts = options or [("أيوه 👍", "yes"), ("لا", "no")]
        token = object()
        self._ask_token = token

        def _answer(value):
            if self._ask_token is not token:
                return
            self._ask_token = None
            if callback:
                callback(value)

        self.set_suggestions(opts, _answer)
        self.set_state("suggesting", str(question), quiet=True)
        if chime and self._sounds:
            _play_soft("ask")
        self._add_to_history("suggesting", str(question))
        self._last_notified_text = str(question)
        self._ripples.append((time.perf_counter(), "suggesting"))
        self._talk_for(1.0)
        self._cancel_hide()
        self._schedule_hide(int(timeout_ms))

    def show_listening_soft(self, text=""):
        """Show 'listening' unless a written reply is still being read."""
        if self.reply_visible():
            return
        self.set_state("listening", text)

    def end_turn(self):
        """Conversation finished: hide, but never cut a reply that's on screen."""
        if self.reply_visible():
            return
        if self._state in ("listening", "thinking", "executing"):
            self.set_state("hide")

    def reply_visible(self):
        return self._tw_active or (
            self._state in ("success", "error", "info", "suggesting")
            and self._hide_id is not None)

    def is_free(self, min_idle_s=60):
        """True when Yobi is idle and you haven't talked to him for a while."""
        return (self._state == "idle" and self._ui_mode is None and not self._tw_active
                and not self._quick_actions_visible
                and time.perf_counter() - self._last_activity >= min_idle_s)

    def set_companion_toggle(self, get_enabled, toggle):
        """Adds 'أسئلة يوبي' on/off to the right-click menu."""
        self._companion_get = get_enabled
        self._companion_toggle = toggle

    def _talk_for(self, seconds):
        self._speaking_override = True
        if getattr(self, "_talk_job", None):
            try:
                self.after_cancel(self._talk_job)
            except Exception:
                pass

        def _done():
            self._talk_job = None
            if not self._tw_active:
                self._speaking_override = None

        self._talk_job = self.after(int(seconds * 1000), _done)

    def _cancel_hide(self):
        if self._hide_id:
            try:
                self.after_cancel(self._hide_id)
            except Exception:
                pass
            self._hide_id = None

    def _history_tail_is(self, text):
        return bool(self._notification_history) and \
            self._notification_history[-1].get("text") == text

    def pulse(self):
        self._ripples.append((time.perf_counter(), self._state))

    def show_notification_history(self):
        self._toggle_history_panel()

    def clear_notification_history(self):
        self._notification_history.clear()
        if self._history_panel is not None:
            self._history_panel.refresh(self._notification_history)

    def set_theme(self, name):
        """name in {'dark', 'light', 'auto'}."""
        self._theme_pref = name
        if name == "auto":
            name = _detect_system_theme()
        if name not in THEMES:
            return
        self._theme_name = name
        self._PAL = dict(THEMES[name])
        self._prefs["theme"] = self._theme_pref
        _save_prefs(self._prefs)
        if self._history_panel is not None:
            self._history_panel.apply_theme(self._PAL)

    def set_quick_action_callback(self, callback):
        self._on_quick_action = callback

    def set_avatar_mood(self, mood):
        m = {"neutral": None, "happy": "happy", "thinking": "think",
             "listening": "listen", "sad": "sad", "sleep": "sleep",
             "curious": "curious", "focus": "focus"}.get(mood, mood)
        self._mood_override = m

    @staticmethod
    def _infer_state(state, text):
        t = text or ""
        if state in ("thinking", "info", "executing"):
            if any(k in t for k in ("🔐", "حساب", "login", "تسجيل الدخول", "بدخل")):
                return "account"
            if "بسجل" in t or "⏺" in t:
                return "recording"
        if state == "thinking" and any(k in t for k in (
                "بنفذ", "⚙", "بشتغل", "بفتح", "بحمل", "بنزل", "بحدث", "بجهز")):
            return "executing"
        if state == "info":
            if any(k in t for k in ("💡", "اقترح", "إيه رأيك", "ايه رأيك", "ايه رايك",
                                    "تحب أ", "تحب ا", "تحب ت")):
                return "suggesting"
            if any(k in t for k in ("⏳", "بفحص", "بحدث")):
                return "executing"
        return state

    def _schedule_hide(self, ms):
        def _auto():
            self._hide_id = None
            if self._speaking or self._hover:
                self._hide_id = self.after(700, _auto)
                return
            self.set_state("hide")
        self._hide_id = self.after(int(ms), _auto)

    def _visual_state(self):
        if self._state == "idle":
            if self._ui_mode == "actions":
                return "actions"
            if self._auto_speaking:
                return "speaking"
            if self._hover and time.perf_counter() - self._hover_since > 0.16:
                return "peek"
            return "idle"
        return self._state

    def _mood(self, vs, now):
        if self._mood_override:
            return self._mood_override
        if vs == "idle" and now - self._last_activity > self.SLEEP_AFTER and not self._hover:
            return "sleep"
        if self._speaking and vs not in ("account", "error", "thinking"):
            return "talk"
        return {"idle": "idle", "peek": "happy", "actions": "curious",
                "listening": "listen", "speaking": "talk", "thinking": "think",
                "executing": "focus", "suggesting": "curious", "account": "private",
                "recording": "listen", "success": "happy", "error": "sad",
                "info": "idle"}.get(vs, "idle")

    def _layout(self):
        """Compute target geometry + static content for the visual state."""
        S = self._S
        te = self._text_engine
        vs = self._visual_state()
        st = STYLES.get(vs, STYLES["info"])
        self._style_target = (_hex(st[0]), _hex(st[1]), _hex(st[2]), st[3])
        T, Ts = 15 * S, 12.5 * S
        gap = 10 * S
        maxw = self.MAX_W * S
        text = self._text or DEFAULT_TEXT.get(vs, "")
        plan = {"vs": vs, "gap": gap, "title": None, "sub_kind": None, "wave_w": 0,
                "voice": False, "chips": [], "split": False, "spin": False,
                "progress": self._progress_mode != "hidden" and vs not in ("idle", "peek", "actions")}
        aux = None
        if vs == "idle":
            w = h = 42 * S
            r = h / 2
            plan.update(kind="orb", char_r=15 * S, h0=h)
        elif vs == "peek":
            lt = time.localtime()
            days = ["الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الحد"]
            label = f"{lt.tm_hour:02d}:{lt.tm_min:02d}  ·  {days[lt.tm_wday]}"
            extra = self._now_playing()
            if extra:
                label += f"  ·  {extra}"
            sub_info = self._peek_metrics()
            if sub_info:
                label += f"\n{sub_info}"
            img = te.block(label, 13.0 * S, "semibold", 360 * S, 2, TEXT_MAIN)
            h = max(46 * S, img[0].height + 18 * S)
            char_r = 16 * S if img[1] > 1 else 15 * S
            cpad = (h - 2 * char_r) / 2
            w = _clamp(18 * S + img[0].width + gap + 2 * char_r + cpad, 190 * S, 435 * S)
            r = min(h / 2, 26 * S)
            plan.update(kind="capsule", char_r=char_r, h0=h, cpad=cpad, lpad=18 * S, title=img)
        elif vs == "actions":
            n = len(self._quick_actions)
            d, sp, pad = 42 * S, 9 * S, 18 * S
            w = 2 * pad + n * d + (n - 1) * sp
            h = 84 * S
            r = 28 * S
            icons = [te.block(e, 19 * S, "regular", 60 * S, 1, TEXT_MAIN, "center")
                     for e, _, _ in self._quick_actions]
            labels = [te.block(lbl, Ts, "semibold", 200 * S, 1, TEXT_DIM, "center")
                      for _, lbl, _ in self._quick_actions]
            plan.update(kind="actions", d=d, sp=sp, pad=pad, icons=icons, labels=labels,
                        char_r=0, h0=h)
        elif vs == "thinking":
            d = 66 * S
            title = te.block(text, 14.5 * S, "semibold", 280 * S, 2, TEXT_MAIN)
            ah = max(48 * S, title[0].height + 22 * S)
            aw = _clamp(title[0].width + 36 * S, 115 * S, 335 * S)
            total = d + gap + aw
            left = -total / 2
            aux = (left + aw / 2, aw, ah, min(ah / 2, 24 * S),
                   self._top + max(0.0, (d - ah) / 2))
            w = h = d
            r = d / 2
            plan.update(kind="split", split=True, char_r=18 * S, h0=d, title=title,
                        main_cx=left + aw + gap + d / 2)
        elif vs == "suggesting":
            pad = 18 * S
            char_r = 21 * S
            w = 435 * S
            tmax = w - 2 * pad - 2 * char_r - gap
            title = te.block(text, T, "semibold", tmax, 3, TEXT_MAIN)
            chips = []
            items = self._suggestions or [("قول «أيوه» 👍", None), ("أو «لا» ✋", None)]
            used = 0.0
            for label, cid in items:
                img = te.block(label, 13 * S, "semibold", 200 * S, 1,
                               TEXT_MAIN if self._suggestions else TEXT_DIM, "center")
                cw = img[0].width + 26 * S
                if used + cw > w - 2 * pad:
                    break
                chips.append((label, cid, img, cw))
                used += cw + 8 * S
            chip_h = 33 * S
            head = max(2 * char_r, title[0].height)
            h = pad + head + 12 * S + chip_h + pad
            r = 28 * S
            plan.update(kind="card", char_r=char_r, pad=pad, title=title, chips=chips,
                        chip_h=chip_h, head=head, h0=h,
                        clickable=bool(self._suggestions))
        else:
            if vs == "speaking" and not self._text:
                h = 46 * S
                char_r = 15 * S
                cpad = (h - 2 * char_r) / 2
                w = 175 * S
                r = h / 2
                plan.update(kind="capsule", char_r=char_r, h0=h, cpad=cpad, lpad=18 * S,
                            voice=True)
            else:
                char_r = {"listening": 22 * S, "executing": 20 * S,
                          "account": 20 * S}.get(vs, 20 * S)
                ring = 5 * S if vs in ("executing", "account") else 0
                cpad = 11 * S + ring
                h0 = 2 * char_r + 2 * cpad
                if vs == "listening":
                    h0 = max(h0, 74 * S)
                    cpad = (h0 - 2 * char_r) / 2
                lpad = 20 * S
                extra = 0.0
                if vs == "listening":
                    plan["wave_w"] = 122 * S
                    extra = plan["wave_w"] + gap
                elif vs == "speaking":
                    plan["voice"] = True
                    extra = 38 * S + gap
                right = cpad + 2 * char_r + gap
                tmax = maxw - lpad - extra - right
                lines = {"info": 4, "success": 3, "error": 3, "suggesting": 3}.get(vs, 2)
                title = te.block(text, T, "semibold", tmax, lines, TEXT_MAIN)
                sub_h = 0.0
                if vs == "account":
                    plan["sub_kind"] = "dots"
                    sub_h = 14 * S
                elif vs == "recording":
                    plan["sub_kind"] = "timer"
                    sub_h = 18 * S
                text_h = title[0].height + sub_h
                prog = 10 * S if plan["progress"] else 0
                h = max(h0, text_h + 28 * S) + prog
                tw = max(title[0].width, 70 * S if sub_h else 0)
                minw = {"listening": 330 * S, "executing": 255 * S, "account": 285 * S,
                        "recording": 245 * S}.get(vs, 215 * S)
                w = _clamp(lpad + extra + tw + right, minw, maxw)
                r = h / 2 if h <= h0 + prog + 1 and not prog else min(h / 2, 30 * S)
                plan.update(kind="capsule", char_r=char_r, h0=h0, cpad=cpad, lpad=lpad,
                            title=title, extra=extra, spin=vs in ("executing",),
                            prog_h=prog)
        main_cx = plan.get("main_cx", 0.0)
        first = not self._plan
        self._mx.t, self._mw.t, self._mh.t, self._mr.t = main_cx, w, h, r
        if aux:
            self._ax.t, self._aw.t, self._ah.t, self._ar = aux[0], aux[1], aux[2], aux[3]
            self._ay.t = aux[4]
            self._aa.t = 1.0
            if self._aa.v < 0.05:
                for spr, val in ((self._ax, main_cx), (self._aw, 10 * S), (self._ah, 10 * S),
                                 (self._ay, self._top + h / 2 - 5 * S)):
                    spr.v, spr.vel = val, 0.0
        else:
            self._ax.t = self._mx.t
            self._aw.t = 8 * S
            self._ah.t = 8 * S
            self._ay.t = self._top + h / 2 - 4 * S
            self._aa.t = 0.0
            self._ar = 4 * S
        if first:
            for s_ in (self._mx, self._mw, self._mh, self._mr):
                s_.snap(s_.t)
        plan["w"], plan["h"] = w, h
        self._plan = plan

    def _now_playing(self):
        if not _HAS_PSUTIL:
            return ""
        now = time.perf_counter()
        if now - getattr(self, "_np_t", 0) < 5:
            return getattr(self, "_np_v", "")
        self._np_t = now
        v = ""
        try:
            spotify_pids = set()
            for p in psutil.process_iter(["pid", "name"]):
                n = (p.info.get("name") or "").lower()
                if n == "spotify.exe":
                    spotify_pids.add(p.info["pid"])
            if spotify_pids and IS_WIN:
                import ctypes
                u32 = ctypes.windll.user32
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                tracks = []

                def _cb(hwnd, _lp):
                    if not u32.IsWindowVisible(hwnd):
                        return True
                    pid = ctypes.c_ulong()
                    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in spotify_pids:
                        ln = u32.GetWindowTextLengthW(hwnd)
                        if ln > 0:
                            buf = ctypes.create_unicode_buffer(ln + 1)
                            u32.GetWindowTextW(hwnd, buf, ln + 1)
                            t = buf.value.strip()
                            if t and t.lower() not in ("spotify", "spotify free", "spotify premium", "gdi+ window", "default ime"):
                                tracks.append(t)
                                return False
                    return True
                u32.EnumWindows(WNDENUMPROC(_cb), 0)
                v = f"🎵 {tracks[0][:28]}" if tracks else "🎵 Spotify"
            elif spotify_pids:
                v = "🎵 Spotify"
        except Exception:
            pass
        self._np_v = v
        return v

    def _peek_metrics(self):
        now = time.perf_counter()
        if now - getattr(self, "_pm_t", 0) < 6:
            return getattr(self, "_pm_v", "")
        self._pm_t = now
        parts = []
        try:
            comp_path = os.path.join(_HERE, "companion_data.json")
            if os.path.exists(comp_path):
                with open(comp_path, "r", encoding="utf-8") as f:
                    cd = json.load(f)
                cups = int(cd.get("water_cups", 0))
                parts.append(f"💧 {cups}/8")
        except Exception:
            pass
        if _HAS_PSUTIL:
            try:
                ram = int(round(psutil.virtual_memory().percent))
                parts.append(f"🧠 {ram}%")
            except Exception:
                pass
        self._pm_v = "  ·  ".join(parts)
        return self._pm_v

    def _ramp(self, goo):
        key = int(goo * 20)
        lut = self._lut_cache.get(key)
        if lut is None:
            gain = 2.2 + 2.6 * (key / 20.0)
            lut = [int(_clamp((i - 128) * gain + 128, 0, 255)) for i in range(256)]
            self._lut_cache[key] = lut
        return lut

    def _gradient(self, bw, bh, deep, acc):
        key = (bw, bh, tuple(int(c) // 3 for c in deep), tuple(int(c) // 3 for c in acc))
        g = self._grad_cache.get(key)
        if g is not None:
            return g
        top = BASE_TOP + (np.array(deep, np.float32) - BASE_TOP) * 0.14
        bot = BASE_BOT + (np.array(deep, np.float32) - BASE_BOT) * 0.34
        v = np.linspace(0, 1, bh, dtype=np.float32)[:, None, None]
        hx = np.linspace(0, 1, bw, dtype=np.float32)[None, :, None] ** 2
        tint = np.array(acc, np.float32) * 0.085
        arr = top * (1 - v) + bot * v + tint * hx
        g = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        if len(self._grad_cache) > 24:
            self._grad_cache.clear()
        self._grad_cache[key] = g
        return g

    def _blobs(self):
        S = self._S
        cx0 = self._W / 2 + self._shake.v
        mw, mh = max(8.0, self._mw.v), max(8.0, self._mh.v)
        mx = cx0 + self._mx.v
        main = (mx - mw / 2, self._top, mx + mw / 2, self._top + mh,
                max(2.0, min(self._mr.v, mh / 2, mw / 2)))
        blobs = [main]
        aux = None
        if self._aa.v > 0.03 and self._aw.v > 3 * S:
            aw, ah = self._aw.v, max(4.0, self._ah.v)
            ax = cx0 + self._ax.v
            aux = (ax - aw / 2, self._ay.v, ax + aw / 2, self._ay.v + ah,
                   max(2.0, min(getattr(self, "_ar", ah / 2), ah / 2, aw / 2)))
            blobs.append(aux)
        return main, aux, blobs

    def _render_frame(self, now, vs):
        S = self._S
        W, H = self._W, self._H
        main, aux, blobs = self._blobs()
        M = int(42 * S)
        x0 = int(max(0, min(b[0] for b in blobs) - M))
        y0 = int(max(0, min(b[1] for b in blobs) - M))
        x1 = int(min(W, max(b[2] for b in blobs) + M))
        y1 = int(min(H, max(b[3] for b in blobs) + M))
        bw, bh = max(1, x1 - x0), max(1, y1 - y0)
        self._island_rect = (min(b[0] for b in blobs), min(b[1] for b in blobs),
                             max(b[2] for b in blobs), max(b[3] for b in blobs))
        mask = Image.new("L", (bw, bh), 0)
        md = ImageDraw.Draw(mask)
        for b in blobs:
            md.rounded_rectangle([b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0],
                                 radius=b[4], fill=255)
        goo = _clamp(self._aa.v, 0, 1) if aux else 0.0
        goo = goo * (1 - goo) * 4 if aux else 0.0
        mask = mask.filter(ImageFilter.GaussianBlur((0.9 + 5.0 * goo) * S)).point(self._ramp(goo))
        acc, deep, light = self._col_acc, self._col_deep, self._col_light
        layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        if self._fx_outside:
            g = self._glow * (0.80 + 0.20 * math.sin(now * 2.4))
            if vs == "listening":
                g *= 0.58 + 0.92 * self._mic.level()
            age = now - self._state_t
            if vs in ("success", "error", "suggesting", "info"):
                g *= 1.0 + 0.9 * math.exp(-age * 2.2)
            if g > 0.02:
                sw, sh = max(1, bw // 4), max(1, bh // 4)
                small = mask.resize((sw, sh), Image.BILINEAR).filter(
                    ImageFilter.GaussianBlur(3.4 * S))
                glow = small.resize((bw, bh), Image.BILINEAR)
                ga = min(1.0, g)
                glow = glow.point([int(i * ga) for i in range(256)])
                gimg = Image.new("RGBA", (bw, bh), _rgba(acc, 0))
                gimg.putalpha(glow)
                layer.alpha_composite(gimg)
            shadow = mask.resize((max(1, bw // 4), max(1, bh // 4)), Image.BILINEAR) \
                .filter(ImageFilter.GaussianBlur(2.6 * S)).resize((bw, bh), Image.BILINEAR)
            shadow = shadow.point([int(i * 0.48) for i in range(256)])
            simg = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            simg.putalpha(shadow)
            layer.alpha_composite(simg, dest=(0, int(3 * S)))
        body = self._gradient(bw, bh, deep, acc).convert("RGBA")
        body.putalpha(mask)
        layer.alpha_composite(body)

        # Animated Bioluminescent Rim
        rim_a = 0.36 + 0.14 * math.sin(now * 2.2)
        for t0, _st in self._ripples:
            p = (now - t0) / 0.8
            if 0 <= p <= 1:
                rim_a = max(rim_a, 0.96 * (1 - p))
        if vs == "idle":
            rim_a *= 0.65
        eroded = mask.filter(ImageFilter.MinFilter(3))
        rim = ImageChops.subtract(mask, eroded).point([int(i * rim_a) for i in range(256)])
        rimg = Image.new("RGBA", (bw, bh), _rgba(_mix(acc, light, 0.28), 0))
        rimg.putalpha(rim)
        layer.alpha_composite(rimg)

        c2 = Image.new("RGBA", (bw * 2, bh * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(c2, "RGBA")
        texts = []
        self._hit = []
        ca = _smooth((now - self._state_t - 0.04) / 0.22)
        if vs in ("idle", "peek", "actions"):
            ca = 1.0 if vs == "idle" else _smooth((now - getattr(self, "_vs_t", 0) - 0.03) / 0.20)
        self._draw_content(d, c2, texts, now, vs, main, aux, x0, y0, ca)
        c1 = c2.reduce(2)
        for img, tx, ty, ta, shimmer in texts:
            if shimmer:
                img = self._shimmer(img, now)
            _blit(c1, img, tx - x0, ty - y0, ta)
        cm = ImageChops.multiply(c1.getchannel("A"), mask)
        c1.putalpha(cm)
        layer.alpha_composite(c1)

        if self._ripples or self._particles:
            f2 = Image.new("RGBA", (bw * 2, bh * 2), (0, 0, 0, 0))
            fd = ImageDraw.Draw(f2, "RGBA")
            if self._fx_outside:
                for t0, st in self._ripples:
                    p = (now - t0) / 0.85
                    if not 0 <= p <= 1:
                        continue
                    e = (4 + 26 * (1 - (1 - p) ** 3)) * S
                    col = _hex(STYLES.get(st, STYLES["info"])[0])
                    a = 195 * (1 - p) ** 2
                    for b in blobs[:1]:
                        fd.rounded_rectangle(
                            [(b[0] - e - x0) * 2, (b[1] - e - y0) * 2,
                             (b[2] + e - x0) * 2, (b[3] + e - y0) * 2],
                            radius=(b[4] + e) * 2, outline=_rgba(col, a), width=int(3 * S))
            for pt in self._particles:
                life = 1 - pt["age"] / pt["life"]
                rr = pt["size"] * (0.6 + 0.4 * life) * 2
                px, py = (pt["x"] - x0) * 2, (pt["y"] - y0) * 2
                if pt.get("star"):
                    # 4-point cartoon sparkle star
                    fd.polygon([
                        (px, py - rr * 1.4), (px + rr * 0.4, py - rr * 0.4),
                        (px + rr * 1.4, py), (px + rr * 0.4, py + rr * 0.4),
                        (px, py + rr * 1.4), (px - rr * 0.4, py + rr * 0.4),
                        (px - rr * 1.4, py), (px - rr * 0.4, py - rr * 0.4),
                    ], fill=_rgba(pt["col"], 245 * life))
                else:
                    fd.ellipse([px - rr, py - rr, px + rr, py + rr],
                               fill=_rgba(pt["col"], 235 * life))
            f1 = f2.reduce(2)
            if not self._fx_outside:
                f1.putalpha(ImageChops.multiply(f1.getchannel("A"), mask))
            layer.alpha_composite(f1)
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        frame.paste(layer, (x0, y0))
        return frame

    def _shimmer(self, img, now):
        a = np.asarray(img.getchannel("A"), dtype=np.float32)
        w = a.shape[1]
        pos = ((now * 0.58) % 1.6 - 0.3) * w
        xs = np.arange(w, dtype=np.float32)
        band = 0.45 + 0.55 * np.exp(-((xs - pos) / (w * 0.16 + 1)) ** 2)
        out = img.copy()
        out.putalpha(Image.fromarray((a * band[None, :]).astype(np.uint8), "L"))
        return out

    def _draw_content(self, d, c2, texts, now, vs, main, aux, x0, y0, ca):
        S = self._S
        p = self._plan
        acc, deep, light = self._col_acc, self._col_deep, self._col_light
        L, Tp, R, B, rad = main
        mw, mh = R - L, B - Tp
        X = lambda x: (x - x0) * 2
        Y = lambda y: (y - y0) * 2
        kind = p.get("kind")
        mood = self._mood(vs, now)
        if kind == "orb":
            r = max(6 * S, min(mw, mh) / 2 - 5.5 * S)
            self._draw_char(c2, d, X((L + R) / 2), Y(Tp + mh / 2), r * 2, mood, now, 255)
            return
        if kind == "actions":
            dd, sp, pad = p["d"], p["sp"], p["pad"]
            cy = Tp + 13 * S + dd / 2
            for i, (emoji, label, aid) in enumerate(self._quick_actions):
                cx = R - pad - dd / 2 - i * (dd + sp)
                hov = (i == self._hover_idx)
                scale = max(0.05, self._action_springs[i].v)
                rr = (dd / 2) * scale
                fill_a = int((95 if hov else 26) * ca * min(1.0, scale))
                fill = _rgba(acc, fill_a) if hov else (255, 255, 255, fill_a)
                d.ellipse([X(cx - rr), Y(cy - rr), X(cx + rr), Y(cy + rr)],
                          fill=fill,
                          outline=_rgba(light if hov else acc, int((185 if hov else 55) * ca * min(1.0, scale))),
                          width=max(1, int((2.2 if hov else 1.2) * S)))
                ic = p["icons"][i][0]
                texts.append((ic, cx - ic.width / 2, cy - ic.height / 2 - (2 * S if hov else 0),
                              ca * _clamp(scale, 0.0, 1.0), False))
                self._hit.append((cx - dd / 2, cy - dd / 2, cx + dd / 2, cy + dd / 2, ("action", aid)))
            if 0 <= self._hover_idx < len(p["labels"]):
                lb = p["labels"][self._hover_idx][0]
                texts.append((lb, (L + R) / 2 - lb.width / 2, Tp + 65 * S - lb.height / 2,
                              ca, False))
            return
        if kind == "split":
            ccx, ccy = (L + R) / 2, Tp + mh / 2
            r = p["char_r"]
            self._draw_orbitals(d, X(ccx), Y(ccy), r * 2, now, back=True, alpha=ca)
            self._draw_char(c2, d, X(ccx), Y(ccy), r * 2, mood, now, 255)
            self._draw_orbitals(d, X(ccx), Y(ccy), r * 2, now, back=False, alpha=ca)
            if aux is not None and p.get("title"):
                aL, aT, aR, aB, _ = aux
                img = p["title"][0]
                ta = ca * _smooth((self._aa.v - 0.50) / 0.42)
                texts.append((img, aR - 18 * S - img.width, (aT + aB) / 2 - img.height / 2,
                              ta, True))
            return
        if kind == "card":
            pad, r = p["pad"], p["char_r"]
            ccx, ccy = R - pad - r, Tp + pad + r
            self._draw_char(c2, d, X(ccx), Y(ccy), r * 2, mood, now, 255)
            img = p["title"][0]
            ty = Tp + pad + (p["head"] - img.height) / 2
            texts.append((img, ccx - r - p["gap"] - img.width, ty, ca, False))
            cxr = R - pad
            cy0 = B - pad - p["chip_h"]
            for i, (label, cid, cimg, cw) in enumerate(p["chips"]):
                cl = cxr - cw
                hov = p.get("clickable") and self._hover_chip == i
                sc = self._chip_springs[i].v if i < len(self._chip_springs) else 1.0
                dy = -1.8 * S * (sc - 1.0) * 6.0
                fill = _rgba(acc, 95) if hov else (255, 255, 255, 28 if p.get("clickable") else 14)
                d.rounded_rectangle([X(cl), Y(cy0 + dy), X(cxr), Y(cy0 + p["chip_h"] + dy)],
                                    radius=p["chip_h"],
                                    fill=(fill[0], fill[1], fill[2], int(fill[3] * ca)),
                                    outline=_rgba(light if hov else acc, (175 if hov else 95 if p.get("clickable") else 45) * ca),
                                    width=max(1, int((2.0 if hov else 1.4) * S)))
                texts.append((cimg[0], cl + (cw - cimg[0].width) / 2,
                              cy0 + dy + (p["chip_h"] - cimg[0].height) / 2, ca, False))
                if p.get("clickable"):
                    self._hit.append((cl, cy0, cxr, cy0 + p["chip_h"], ("chip", (label, cid))))
                cxr = cl - 8 * S
            return

        r = p["char_r"]
        cpad = p.get("cpad", 11 * S)
        h0 = p.get("h0", mh)
        prog_h = p.get("prog_h", 0)
        ccx = R - cpad - r
        ccy = Tp + min(h0, mh - prog_h) / 2 if mh - prog_h > h0 + 2 * S else Tp + (mh - prog_h) / 2
        if p.get("spin"):
            self._draw_spinner(d, X(ccx), Y(ccy), r * 2, now, ca)
        if vs == "account":
            self._draw_ring(d, X(ccx), Y(ccy), r * 2, now, ca)
        self._draw_char(c2, d, X(ccx), Y(ccy), r * 2, mood, now, 255)
        text_right = ccx - r - p["gap"] - (4 * S if p.get("spin") or vs == "account" else 0)
        title = p.get("title")
        sub_h = 14 * S if p.get("sub_kind") == "dots" else 18 * S if p.get("sub_kind") == "timer" else 0
        if title:
            img = title[0]
            block_h = img.height + sub_h
            ty = Tp + (mh - prog_h - block_h) / 2
            texts.append((img, text_right - img.width, ty, ca, False))
            sy = ty + img.height
        else:
            sy = Tp + mh / 2
        if p.get("sub_kind") == "dots":
            n = 8
            filled = int((now * 6) % (n + 4))
            rr = 3.2 * S
            for i in range(n):
                cx = text_right - rr - i * (rr * 2 + 4 * S)
                on = i < filled
                d.ellipse([X(cx - rr), Y(sy + 6 * S - rr), X(cx + rr), Y(sy + 6 * S + rr)],
                          fill=_rgba(light if on else (90, 90, 110), (235 if on else 120) * ca))
        elif p.get("sub_kind") == "timer":
            el = int(now - self._rec_start)
            timg = self._text_engine.block(f"⏺ {el // 60:02d}:{el % 60:02d}", 12.5 * S,
                                           "semibold", 120 * S, 1, (253, 164, 175))
            texts.append((timg[0], text_right - timg[0].width, sy + 1 * S, ca, False))
        if p.get("wave_w"):
            wx0 = L + p["lpad"]
            wx1 = wx0 + p["wave_w"]
            wcy = Tp + mh / 2
            self._draw_wave(d, X(wx0), X(wx1), Y(wcy), (mh * 0.64) * 2, now, ca)
            self._wave_geom = (wx0, wx1, wcy, mh * 0.64)
        else:
            self._wave_geom = None
        if p.get("voice"):
            vx1 = text_right - (title[0].width + 10 * S if title else 0)
            vx0 = vx1 - 36 * S
            if not title:
                vx0, vx1 = L + p["lpad"], L + p["lpad"] + 42 * S
            self._draw_voice(d, X(vx0), X(vx1), Y(ccy), mh * 0.54 * 2, now, ca)
        if p.get("progress"):
            px0, px1 = L + 20 * S, R - 20 * S
            py = B - 11 * S
            th = 4.5 * S
            d.rounded_rectangle([X(px0), Y(py), X(px1), Y(py + th)], radius=th,
                                fill=(255, 255, 255, int(34 * ca)))
            if self._progress_mode == "det":
                fx1 = px0 + (px1 - px0) * _clamp(self._progress.v, 0, 1)
                if fx1 > px0 + th:
                    d.rounded_rectangle([X(px0), Y(py), X(fx1), Y(py + th)], radius=th,
                                        fill=_rgba(acc, 255 * ca))
            else:
                span = (px1 - px0) * 0.34
                t = (math.sin(now * 2.8) + 1) / 2
                sx = px0 + (px1 - px0 - span) * t
                d.rounded_rectangle([X(sx), Y(py), X(sx + span), Y(py + th)], radius=th,
                                    fill=_rgba(_mix(acc, light, 0.35), 255 * ca))

    def _draw_wave(self, d, x0, x1, cy, hmax, now, ca):
        """Fluid Aurora dual-ribbon + glowing harmonic capsules."""
        n = len(self._bars)
        w = x1 - x0
        if w <= 4:
            return
        acc, deep, light = self._col_acc, self._col_deep, self._col_light
        lvl = max(0.08, self._mic.level())

        # 1. Background fluid Aurora sine ribbons (Siri/Gemini style)
        pts_top, pts_bot = [], []
        steps = 28
        for k in range(steps + 1):
            u = k / steps
            px = x0 + u * w
            env = math.sin(u * math.pi)
            wave1 = math.sin(u * 6.5 - now * 6.2) * 0.55 + math.cos(u * 10.0 + now * 4.4) * 0.45
            amp = hmax * 0.42 * env * (0.22 + 0.78 * lvl) * wave1
            pts_top.append((px, cy - abs(amp)))
            pts_bot.append((px, cy + abs(amp)))
        ribbon = pts_top + list(reversed(pts_bot))
        if len(ribbon) >= 6:
            d.polygon(ribbon, fill=_rgba(acc, int(58 * ca)))

        # 2. Foreground crisp bioluminescent capsules with glowing tips
        step = w / n
        bw = max(2.2, step * 0.54)
        for i, v in enumerate(self._bars):
            t = i / max(1, n - 1)
            col = _mix(deep, acc, t * 1.6) if t < 0.6 else _mix(acc, light, (t - 0.6) / 0.4)
            bh = max(bw, hmax * _clamp(v, 0, 1))
            x = x0 + i * step + (step - bw) / 2
            d.rounded_rectangle([x, cy - bh / 2, x + bw, cy + bh / 2], radius=bw / 2,
                                fill=_rgba(col, 245 * ca))
            if bh > bw * 2.0:
                tip_r = bw * 0.45
                cx_b = x + bw / 2
                d.ellipse([cx_b - tip_r, cy - bh / 2 + tip_r * 0.4,
                           cx_b + tip_r, cy - bh / 2 + tip_r * 2.4],
                          fill=_rgba(light, 210 * ca))

    def _draw_voice(self, d, x0, x1, cy, hmax, now, ca):
        """Symmetrical harmonic voice bars + connecting wave line."""
        n = len(self._vbars)
        step = (x1 - x0) / n
        bw = max(2.2, step * 0.52)
        d.line([x0, cy, x1, cy], fill=_rgba(self._col_acc, 85 * ca), width=2)
        for i, v in enumerate(self._vbars):
            bh = max(bw, hmax * _clamp(v, 0, 1))
            x = x0 + i * step + (step - bw) / 2
            col = _mix(self._col_acc, self._col_light, abs(i - n / 2) / max(1, n / 2))
            d.rounded_rectangle([x, cy - bh / 2, x + bw, cy + bh / 2], radius=bw / 2,
                                fill=_rgba(col, 255 * ca))

    def _draw_orbitals(self, d, cx, cy, r, now, back, alpha=1.0):
        acc, light = self._col_acc, self._col_light
        orbits = ((1.55, 0.35, 2.4, 0.0), (1.45, -0.5, -1.9, 2.1), (1.62, 1.2, 3.1, 4.2))
        for k, (R, tilt, spd, ph) in enumerate(orbits):
            th = now * spd + ph
            ox, oy = math.cos(th) * R * r, math.sin(th) * R * r * 0.36
            depth = math.sin(th)
            if (depth < 0) != back:
                continue
            rx = ox * math.cos(tilt) - oy * math.sin(tilt)
            ry = ox * math.sin(tilt) + oy * math.cos(tilt)
            sz = r * 0.13 * (1 + 0.35 * depth)
            col = _mix(acc, light, 0.3 + 0.3 * k / 2)
            a = 255 * (0.55 + 0.45 * (depth + 1) / 2) * alpha
            d.ellipse([cx + rx - sz, cy + ry - sz, cx + rx + sz, cy + ry + sz], fill=_rgba(col, a))

    def _draw_spinner(self, d, cx, cy, r, now, ca):
        R = r * 1.32
        w = max(2, int(r * 0.13))
        st = (now * 320) % 360
        d.arc([cx - R, cy - R, cx + R, cy + R], st, st + 115, fill=_rgba(self._col_acc, 255 * ca), width=w)
        st2 = (-now * 210) % 360
        d.arc([cx - R, cy - R, cx + R, cy + R], st2, st2 + 55, fill=_rgba(self._col_light, 165 * ca), width=w)

    def _draw_ring(self, d, cx, cy, r, now, ca):
        R = r * 1.32
        w = max(2, int(r * 0.09))
        a = 120 + 100 * (0.5 + 0.5 * math.sin(now * 3))
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=_rgba(self._col_acc, a * ca), width=w)

    def _char_body(self, rx, ry):
        """3D cartoon sphere with rim glow and subsurface highlight."""
        acc, deep, light = self._col_acc, self._col_deep, self._col_light
        w, h = int(2 * rx + 4), int(2 * ry + 4)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        nx = (xx - (w - 1) / 2) / rx
        ny = (yy - (h - 1) / 2) / ry
        dist = np.sqrt(nx * nx + ny * ny)
        alpha = np.clip((1 - dist) * min(rx, ry) + 0.5, 0, 1)
        hl = np.sqrt((nx + 0.36) ** 2 + (ny + 0.44) ** 2) / 1.52
        t = np.clip(1 - hl, 0, 1)
        rim = np.clip((dist - 0.72) / 0.28, 0, 1) ** 2 * 0.38
        deep_a, acc_a, light_a = (np.array(c, np.float32) for c in (deep, acc, light))
        t1 = np.clip(t * 1.72, 0, 1)[..., None]
        t2 = np.clip((t - 0.60) / 0.40, 0, 1)[..., None]
        col = deep_a + (acc_a - deep_a) * t1 + (light_a - acc_a) * t2 + light_a * rim[..., None]
        rgba = np.dstack([np.clip(col, 0, 255), alpha[..., None] * 255]).astype(np.uint8)
        return Image.fromarray(rgba, "RGBA")

    def _draw_char(self, img, d, cx, cy, r, mood, now, alpha=255):
        """Evolved Cartoon Yobi v8: 3D glossy body, bouncy antenna, cute side-ears/headset,
        layered anime eyes with iris & dual catchlights, expressive brows & mouth."""
        if r < 4:
            return
        acc, deep, light = self._col_acc, self._col_deep, self._col_light
        sq = _clamp(self._squash.v, -0.6, 0.6) * 0.18
        breath = math.sin(now * 2.2) * 0.028
        if mood == "listen":
            breath += self._mic.level() * 0.055

        # Gentle floating bobbing
        bob = math.sin(now * 3.1) * r * 0.045 if mood in ("idle", "curious", "talk") else 0.0
        if mood == "happy":
            bob = -abs(math.sin(now * 5.4)) * r * 0.075
        cy = cy + bob

        rx = r * (1 + sq + breath)
        ry = r * (1 - sq - breath)
        lx, ly = _clamp(self._lookx.v, -1, 1), _clamp(self._looky.v, -1, 1)
        ox, oy = lx * r * 0.15, ly * r * 0.12
        tilt = _clamp(self._tilt.v, -0.35, 0.35)

        # 1. Cartoon Side Ears / Headphones Pods (drawn behind body)
        ear_w, ear_h = r * 0.24, r * 0.42
        ear_pulse = 1.0 + (self._mic.level() * 0.22 if mood == "listen" else self._mouth * 0.15 if mood == "talk" else 0.0)
        ear_h *= ear_pulse
        for sgn in (-1, 1):
            ex_c = cx + sgn * (rx * 0.96)
            ey_c = cy + sgn * tilt * r * 0.22
            d.rounded_rectangle(
                [ex_c - ear_w, ey_c - ear_h, ex_c + ear_w, ey_c + ear_h],
                radius=ear_w, fill=_rgba(deep, 245), outline=_rgba(acc, 220),
                width=max(1, int(r * 0.08))
            )
            # Glowing inner ear pad
            d.rounded_rectangle(
                [ex_c - ear_w * 0.55, ey_c - ear_h * 0.55, ex_c + ear_w * 0.55, ey_c + ear_h * 0.55],
                radius=ear_w * 0.5, fill=_rgba(light, 190)
            )
        # Headband arc connecting the side pods when listening / executing / talking
        if mood in ("listen", "focus", "talk"):
            hb_r = rx * 1.03
            d.arc([cx - hb_r, cy - ry * 1.12, cx + hb_r, cy + ry * 0.7],
                  195, 345, fill=_rgba(acc, 210), width=max(2, int(r * 0.09)))

        # 2. Bouncy Cartoon Antenna / Energy Sprout on top of head
        if r > 12:
            sway = math.sin(now * 3.8) * r * 0.14 + self._antenna_sway.v * r * 0.08 + ox * 0.35
            ax_base, ay_base = cx + ox * 0.2, cy - ry * 0.92
            ax_tip, ay_tip = ax_base + sway, ay_base - r * 0.34
            d.line([ax_base, ay_base, ax_tip, ay_tip],
                   fill=_rgba(acc, 235), width=max(2, int(r * 0.09)))
            orb_r = r * (0.14 + 0.03 * math.sin(now * 6.0))
            d.ellipse([ax_tip - orb_r * 1.5, ay_tip - orb_r * 1.5,
                       ax_tip + orb_r * 1.5, ay_tip + orb_r * 1.5],
                      fill=_rgba(acc, 95))
            d.ellipse([ax_tip - orb_r, ay_tip - orb_r, ax_tip + orb_r, ay_tip + orb_r],
                      fill=_rgba(light, 250))

        # 3. Main 3D Glossy Cartoon Body
        body = self._char_body(rx, ry)
        _blit(img, body, cx - body.width / 2, cy - body.height / 2)

        # Top-left Cartoon Glass Specular Highlight Pill
        hl_cx = cx - rx * 0.32 + ox * 0.18
        hl_cy = cy - ry * 0.42 + oy * 0.18
        hl_rx, hl_ry = rx * 0.26, ry * 0.13
        d.ellipse([hl_cx - hl_rx, hl_cy - hl_ry, hl_cx + hl_rx, hl_cy + hl_ry],
                  fill=(255, 255, 255, 92))

        # 4. Expressive Cartoon Eyes
        ex = r * 0.35
        ey_base = cy - r * 0.06 + oy
        ew, eh = r * 0.24, r * 0.45
        blink = 1.0
        if self._blink_t >= 0:
            bt = (now - self._blink_t) / 0.16
            blink = abs(1 - 2 * _clamp(bt, 0, 1)) * 0.92 + 0.08
        lw = max(2, int(r * 0.11))
        eyes = [
            (cx - ex + ox, ey_base - tilt * r * 0.14),
            (cx + ex + ox, ey_base + tilt * r * 0.14),
        ]

        if mood in ("happy",):
            for idx_e, (x, y) in enumerate(eyes):
                d.arc([x - ew * 1.18, y - eh * 0.28, x + ew * 1.18, y + eh * 0.72], 200, 340,
                      fill=EYE, width=lw)
        elif mood in ("private", "sleep"):
            for x, y in eyes:
                d.arc([x - ew * 1.15, y - eh * 0.55, x + ew * 1.15, y + eh * 0.35], 20, 160,
                      fill=EYE, width=lw)
        elif mood == "sad":
            for idx_e, (x, y) in enumerate(eyes):
                s = ew * 0.92
                if idx_e == 0:
                    d.line([x - s, y - s * 0.85, x + s * 0.8, y], fill=EYE, width=lw)
                    d.line([x + s * 0.8, y, x - s, y + s * 0.85], fill=EYE, width=lw)
                else:
                    d.line([x + s, y - s * 0.85, x - s * 0.8, y], fill=EYE, width=lw)
                    d.line([x - s * 0.8, y, x + s, y + s * 0.85], fill=EYE, width=lw)
                # Cute cartoon tear drop on outer corner
                if r > 14:
                    tx_d = x + (-1 if idx_e == 0 else 1) * ew * 1.15
                    ty_d = y + eh * 0.35 + math.sin(now * 6 + idx_e) * r * 0.04
                    tr_d = r * 0.08
                    d.ellipse([tx_d - tr_d, ty_d - tr_d, tx_d + tr_d, ty_d + tr_d],
                              fill=(56, 189, 248, 210))
        else:
            k = {"listen": 1.14, "focus": 0.62, "think": 0.92, "curious": 1.08, "talk": 0.98}.get(mood, 1.0)
            for i, (x, y) in enumerate(eyes):
                eye_blink = blink if (self._wink_eye < 0 or self._wink_eye == i) else 1.0
                if self._wink_eye == i and eye_blink < 0.35:
                    d.arc([x - ew * 1.1, y - eh * 0.25, x + ew * 1.1, y + eh * 0.65], 200, 340,
                          fill=EYE, width=lw)
                    continue
                hh = eh * k * eye_blink
                if mood == "think" and i == 1:
                    hh *= 0.78
                hh = max(ew * 0.55, hh)
                d.rounded_rectangle([x - ew / 2, y - hh / 2, x + ew / 2, y + hh / 2],
                                    radius=ew / 2, fill=EYE)
                if eye_blink > 0.65 and hh > ew * 0.85:
                    # Colored lower iris glow crescent
                    ir_w, ir_h = ew * 0.62, hh * 0.36
                    d.ellipse([x - ir_w / 2 + ox * 0.08, y + hh * 0.06,
                               x + ir_w / 2 + ox * 0.08, y + hh * 0.06 + ir_h],
                              fill=_rgba(acc, 185))
                    # Primary anime catchlight (top-left)
                    cr = ew * 0.23
                    d.ellipse([x - ew * 0.14 - cr, y - hh * 0.23 - cr,
                               x - ew * 0.14 + cr, y - hh * 0.23 + cr],
                              fill=(255, 255, 255, 245))
                    # Secondary catchlight (bottom-right)
                    cr2 = ew * 0.11
                    d.ellipse([x + ew * 0.17 - cr2, y + hh * 0.18 - cr2,
                               x + ew * 0.17 + cr2, y + hh * 0.18 + cr2],
                              fill=(255, 255, 255, 185))

        # 5. Cool Cyber Visor / Glasses in "focus" (executing) mode
        if mood == "focus" and r > 12:
            vx0, vx1 = cx - ex * 1.72 + ox * 0.7, cx + ex * 1.72 + ox * 0.7
            vy0, vy1 = ey_base - eh * 0.48, ey_base + eh * 0.42
            d.rounded_rectangle([vx0, vy0, vx1, vy1], radius=(vy1 - vy0) * 0.4,
                                fill=(15, 23, 42, 110), outline=_rgba(light, 225),
                                width=max(1, int(r * 0.07)))
            # Glint across visor
            glint_x = vx0 + ((now * 0.9) % 1.0) * (vx1 - vx0 - r * 0.3)
            d.line([glint_x, vy0 + 2, glint_x + r * 0.22, vy1 - 2],
                   fill=(255, 255, 255, 165), width=max(1, int(r * 0.07)))

        # 6. Expressive Cartoon Eyebrows
        if mood in ("think", "focus", "sad", "curious", "listen") and r > 10:
            bw_ = ew * 1.18
            by_ = ey_base - eh * 0.74
            blw = max(2, int(r * 0.088))
            for idx_e, (x, y_e) in enumerate(eyes):
                sgn = -1 if idx_e == 0 else 1
                if mood == "focus":
                    dy_in, dy_out = r * 0.09, -r * 0.05
                elif mood == "sad":
                    dy_in, dy_out = -r * 0.10, r * 0.07
                elif mood == "think":
                    dy_in = -r * 0.09 if idx_e == 0 else r * 0.06
                    dy_out = -r * 0.02 if idx_e == 0 else 0.0
                else:
                    dy_in = dy_out = -r * 0.07
                x_in = x - sgn * bw_ * 0.5
                x_out = x + sgn * bw_ * 0.5
                by_cur = y_e - eh * 0.68
                d.line([x_in, by_cur + dy_in, x_out, by_cur + dy_out], fill=EYE, width=blw)

        # 7. Expressive Cartoon Mouth & Tongue
        my = cy + r * 0.37 + oy * 0.5
        mx = cx + ox * 0.6
        if mood == "talk":
            m = self._mouth
            mw_, mh_ = r * 0.36 * (0.82 + 0.22 * m), r * (0.08 + 0.26 * m)
            d.rounded_rectangle([mx - mw_ / 2, my - mh_ / 2, mx + mw_ / 2, my + mh_ / 2],
                                radius=min(mw_, mh_) / 2, fill=EYE)
            # Cute inner pink tongue when mouth opens
            if m > 0.25 and mh_ > 4:
                tw_, th_ = mw_ * 0.62, mh_ * 0.48
                d.ellipse([mx - tw_ / 2, my + mh_ / 2 - th_, mx + tw_ / 2, my + mh_ / 2],
                          fill=(244, 114, 182, 225))
            if self._tw_active and r > 10:
                tail_x = mx - r * 1.2
                tail_y = my
                d.polygon([
                    (mx - mw_ / 2 - 1, my - mh_ * 0.3),
                    (mx - mw_ / 2 - 1, my + mh_ * 0.3),
                    (tail_x, tail_y),
                ], fill=EYE + (int(160 * (0.5 + 0.5 * m)),))
        elif mood in ("happy", "curious", "idle", "private"):
            s = r * (0.22 if mood in ("happy", "curious") else 0.14)
            if mood == "happy" and r > 13:
                # Open cheerful cartoon D-smile
                d.chord([mx - s, my - s * 0.85, mx + s, my + s * 0.75], 15, 165,
                        fill=EYE, outline=EYE, width=max(2, int(r * 0.06)))
                d.ellipse([mx - s * 0.5, my, mx + s * 0.5, my + s * 0.55],
                          fill=(244, 114, 182, 210))
            else:
                d.arc([mx - s, my - s * 1.1, mx + s, my + s * 0.6], 25, 155, fill=EYE,
                      width=max(2, int(r * 0.085)))
        elif mood == "sad":
            s = r * 0.17
            d.arc([mx - s, my - s * 0.2, mx + s, my + s * 1.4], 205, 335, fill=EYE,
                  width=max(2, int(r * 0.085)))
        elif mood in ("focus", "think"):
            s = r * 0.11
            if mood == "think":
                # Quirky wavy/squiggly thinking mouth
                d.arc([mx - s, my - s * 0.4, mx, my + s * 0.4], 180, 360, fill=EYE, width=max(2, int(r * 0.075)))
                d.arc([mx, my - s * 0.4, mx + s, my + s * 0.4], 0, 180, fill=EYE, width=max(2, int(r * 0.075)))
            else:
                d.line([mx - s, my, mx + s, my], fill=EYE, width=max(2, int(r * 0.08)))

        # 8. Rosy Cartoon Blush Cheeks
        if mood in ("happy", "curious", "talk", "idle"):
            blush_a = 105 if mood in ("happy", "talk") else 65
            for sx in (-1, 1):
                chx = cx + sx * r * 0.58 + ox * 0.4
                chy = cy + r * 0.19 + sx * tilt * r * 0.1
                cr = r * 0.135
                d.ellipse([chx - cr * 1.35, chy - cr * 0.9, chx + cr * 1.35, chy + cr * 0.9],
                          fill=(255, 115, 165, blush_a))

        # 9. Contextual Badges (Lock, Recording Dot, Idea Bulb, Sleep Zzz)
        vs = self._plan.get("vs")
        if vs == "account":
            bx, by, b = cx + r * 0.72, cy + r * 0.62, r * 0.5
            d.arc([bx - b * 0.32, by - b * 0.78, bx + b * 0.32, by - b * 0.02], 180, 360,
                  fill=(238, 242, 255), width=max(2, int(r * 0.09)))
            d.rounded_rectangle([bx - b / 2, by - b * 0.32, bx + b / 2, by + b * 0.45],
                                radius=b * 0.16, fill=(238, 242, 255))
            kr = b * 0.1
            d.ellipse([bx - kr, by - kr, bx + kr, by + kr], fill=_rgba(self._col_deep))
        elif vs == "recording":
            pr = r * 0.2 * (1 + 0.18 * math.sin(now * 6))
            bx, by = cx + r * 0.78, cy - r * 0.72
            d.ellipse([bx - pr - 2, by - pr - 2, bx + pr + 2, by + pr + 2], fill=(255, 255, 255, 230))
            d.ellipse([bx - pr, by - pr, bx + pr, by + pr], fill=(244, 63, 94))
        elif vs == "suggesting":
            bx, by = cx - r * 0.86, cy - r * 0.82
            gr = r * (0.44 + 0.07 * math.sin(now * 4.5))
            d.ellipse([bx - gr, by - gr, bx + gr, by + gr], fill=(253, 224, 71, 80))
            br = r * 0.23
            d.ellipse([bx - br, by - br, bx + br, by + br], fill=(254, 240, 138))
            d.rounded_rectangle([bx - br * 0.55, by + br * 0.7, bx + br * 0.55, by + br * 1.35],
                                radius=br * 0.2, fill=(203, 213, 225))
        if mood == "sleep":
            for i in range(3):
                ph = (now * 0.5 + i / 3) % 1
                zx = cx + r * (0.85 + ph * 0.5)
                zy = cy - r * (0.6 + ph * 0.9)
                zs = r * (0.12 + 0.1 * ph)
                a = int(220 * (1 - ph))
                col = (226, 232, 240, a)
                d.line([zx - zs, zy - zs, zx + zs, zy - zs], fill=col, width=max(1, int(r * 0.06)))
                d.line([zx + zs, zy - zs, zx - zs, zy + zs], fill=col, width=max(1, int(r * 0.06)))
                d.line([zx - zs, zy + zs, zx + zs, zy + zs], fill=col, width=max(1, int(r * 0.06)))

    def _tick(self):
        t_start = time.perf_counter()
        now = t_start
        dt = _clamp(now - self._last_frame, 0.001, 0.05)
        self._last_frame = now
        if self._tw_active:
            elapsed = now - self._tw_last_t
            new_chars = int(elapsed * self._tw_rate)
            if new_chars > 0:
                self._tw_last_t = now
                self._tw_chars = min(self._tw_chars + new_chars, len(self._tw_full))
                revealed = self._tw_full[:self._tw_chars]
                cursor = "▍" if self._tw_chars < len(self._tw_full) else ""
                self._text = revealed + cursor
                self._layout()
                if self._tw_chars >= len(self._tw_full):
                    self._tw_active = False
                    self._tw_done_t = now
                    self._speaking_override = None
                    hide_ms = max(4500, len(self._tw_full) * 85)
                    self._cancel_hide()
                    self._schedule_hide(hide_ms)
        vs = self._visual_state()
        if vs != self._plan.get("vs"):
            self._vs_t = now
            if vs == "actions":
                for sp in self._action_springs:
                    sp.snap(0.0)
            self._layout()
        elif vs == "peek" and int(now) % 20 == 0 and now - getattr(self, "_peek_t", 0) > 1.5:
            self._peek_t = now
            self._layout()

        # Update staggered targets for quick actions & chips
        if vs == "actions":
            age = now - self._vs_t
            for i, sp in enumerate(self._action_springs):
                if age >= i * 0.028:
                    sp.t = 1.18 if i == self._hover_idx else 1.0
                else:
                    sp.t = 0.0
        else:
            for sp in self._action_springs:
                sp.t = 0.0

        for i, csp in enumerate(self._chip_springs):
            csp.t = 1.10 if (vs == "suggesting" and self._hover_chip == i) else 1.0

        for _ in range(2):
            for s in self._springs:
                s.step(dt / 2)
        k = 1 - math.exp(-dt * 9)
        tg = self._style_target
        self._col_acc = _mix(self._col_acc, tg[0], k)
        self._col_deep = _mix(self._col_deep, tg[1], k)
        self._col_light = _mix(self._col_light, tg[2], k)
        self._glow += (tg[3] - self._glow) * k
        self._update_life(now, dt, vs)
        try:
            self._present(self._render_frame(now, vs))
        except Exception as e:
            if not getattr(self, "_render_err", False):
                self._render_err = True
                import traceback
                traceback.print_exc()
                print(f"⚠️ island render error: {e}")
        active = (vs != "idle" or self._particles or self._ripples or self._speaking
                  or self._tw_active
                  or not all(s.settled() for s in self._springs[:11]))
        fps = self.FPS if active else self.IDLE_FPS
        spent = (time.perf_counter() - t_start) * 1000
        self.after(max(4, int(1000 / fps - spent)), self._tick)

    def _present(self, frame):
        if self._layered is not None:
            try:
                self._layered.update(frame, self._win_x, self._win_y)
                return
            except Exception as e:
                print(f"⚠️ layered render failed, switching to colour-key: {e}")
                self._layered = None
                self._fx_outside = False
                try:
                    self.attributes("-transparentcolor", KEY_COLOR)
                except Exception:
                    pass
        bg = Image.new("RGB", frame.size, KEY_RGB)
        bg.paste(frame, (0, 0), frame)
        if self._photo is None or self._photo.width() != bg.width:
            self._photo = ImageTk.PhotoImage(bg)
            self._canvas.itemconfigure(self._img_item, image=self._photo)
        else:
            self._photo.paste(bg)

    def _update_life(self, now, dt, vs):
        S = self._S
        if self._blink_t < 0 and now >= self._blink_next:
            self._blink_t = now
            self._wink_eye = random.choice([0, 1]) if (vs == "peek" and random.random() < 0.25) else -1
        if self._blink_t >= 0 and now - self._blink_t > 0.16:
            self._blink_t = -1.0
            self._wink_eye = -1
            self._blink_next = now + (0.22 if random.random() < 0.15 else random.uniform(2.2, 5.2))
        if now >= self._look_next:
            mood = self._mood(vs, now)
            if mood == "think":
                tx, ty = random.uniform(-0.9, -0.25), random.uniform(-1.0, -0.55)
                self._tilt.t = random.uniform(-0.18, 0.18)
            elif mood == "listen":
                tx, ty = random.uniform(-0.8, -0.25), random.uniform(-0.2, 0.25)
                self._tilt.t = 0.08
            elif mood in ("sleep", "private"):
                tx, ty = 0.0, 0.2
                self._tilt.t = 0.0
            elif vs in ("idle", "peek"):
                tx, ty = random.uniform(-0.85, 0.85), random.uniform(-0.5, 0.5)
                self._tilt.t = tx * 0.15
            else:
                tx, ty = random.uniform(-0.7, -0.1), random.uniform(-0.3, 0.3)
            self._lookx.t, self._looky.t = tx, ty
            self._look_next = now + random.uniform(1.0, 2.8)
        self._lookx.step(dt)
        self._looky.step(dt)
        self._antenna_sway.t = (self._lookx.v - self._lookx.t) * 1.4
        talk_t = 0.0
        if self._speaking:
            talk_t = (0.25 + 0.75 * abs(math.sin(now * 11 + math.sin(now * 3.7) * 2))
                      * (0.5 + 0.5 * abs(math.sin(now * 2.3))))
        self._mouth += (talk_t - self._mouth) * min(1.0, dt * 18)
        for i in range(len(self._vbars)):
            tgt = 0.2 + (0.8 * abs(math.sin(now * (8 + i * 1.3) + i)) * self._mouth if self._speaking else 0)
            self._vbars[i] += (tgt - self._vbars[i]) * min(1.0, dt * 16)
        if vs == "listening":
            lvl = self._mic.level()
            n = len(self._bars)
            for i in range(n):
                env = math.exp(-(((i - (n - 1) / 2) / (n * 0.34)) ** 2))
                tgt = 0.12 + lvl * env * (0.3 + 0.7 * abs(math.sin(now * (5 + i * 0.37) + i * 1.7)))
                self._bars[i] += (tgt - self._bars[i]) * min(1.0, dt * 16)
            g = getattr(self, "_wave_geom", None)
            if g and not getattr(self, "_reduced_motion", False) and random.random() < lvl * 65 * dt:
                wx0, wx1, wcy, hm = g
                i = random.randrange(n)
                bx = wx0 + (i + 0.5) * (wx1 - wx0) / n
                up = random.random() < 0.5
                by = wcy + (-1 if up else 1) * hm * self._bars[i] / 2
                self._particles.append({
                    "x": bx, "y": by,
                    "vx": random.uniform(-18, 18) * S,
                    "vy": (-1 if up else 1) * random.uniform(30, 85) * S,
                    "age": 0.0, "life": random.uniform(0.5, 1.0),
                    "size": random.uniform(1.1, 2.3) * S,
                    "col": _mix(self._col_acc, self._col_light, random.random()),
                })
        else:
            for i in range(len(self._bars)):
                self._bars[i] += (0.1 - self._bars[i]) * min(1.0, dt * 10)
        alive = []
        for pt in self._particles:
            pt["age"] += dt
            if pt["age"] < pt["life"]:
                pt["x"] += pt["vx"] * dt
                pt["y"] += pt["vy"] * dt
                pt["vy"] *= (1 - dt * 1.5)
                alive.append(pt)
        self._particles = alive[-160:]
        self._ripples = [rp for rp in self._ripples if now - rp[0] < 0.85]

    def _poll(self):
        now = time.perf_counter()
        try:
            px, py = self.winfo_pointerxy()
            rx, ry = px - self._win_x, py - self._win_y
            x0, y0, x1, y1 = self._island_rect
            inside = (x0 - 6) <= rx <= (x1 + 6) and (y0 - 6) <= ry <= (y1 + 6)
            if inside and not self._hover:
                self._hover = True
                self._hover_since = now
                self._last_activity = now
                self._squash.vel += 2.2
            elif not inside and self._hover:
                self._hover = False
            if self._layered is not None:
                self._layered.set_click_through(not inside and not self._dragging)
            self._hover_idx = -1
            self._hover_chip = -1
            if inside:
                for (hx0, hy0, hx1, hy1, (kind, val)) in self._hit:
                    if hx0 <= rx <= hx1 and hy0 <= ry <= hy1:
                        if kind == "action":
                            ids = [a for _, _, a in self._quick_actions]
                            self._hover_idx = ids.index(val) if val in ids else -1
                        elif kind == "chip":
                            labels = [c[0] for c in self._plan.get("chips", [])]
                            self._hover_chip = labels.index(val[0]) if val[0] in labels else -1
        except Exception:
            pass
        sp = self._speaking_override
        if sp is None:
            if self._tw_active:
                sp = True
            else:
                mod = sys.modules.get("tts_engine")
                fn = getattr(mod, "is_speaking", None) if mod else None
                try:
                    sp = bool(fn()) if fn else False
                except Exception:
                    sp = False
        if sp != self._speaking:
            self._speaking = sp
            if sp:
                self._last_activity = now
                if self._state == "idle" and self._ui_mode is None:
                    self._auto_speaking = True
            else:
                self._auto_speaking = False
        if (self._ui_mode == "actions" and not self._hover
                and now - getattr(self, "_actions_t", 0) > 6):
            self._ui_mode = None
        self._poll_job = self.after(120, self._poll)

    def _on_press(self, e):
        self._press = (e.x_root, e.y_root, self._win_x, self._win_y)
        self._dragging = False

    def _on_motion_drag(self, e):
        if not self._press:
            return
        sx, sy, wx, wy = self._press
        dx, dy = e.x_root - sx, e.y_root - sy
        if not self._dragging and math.hypot(dx, dy) > 5:
            self._dragging = True
        if self._dragging:
            self._win_x, self._win_y = wx + dx, wy + dy
            self.geometry(f"+{self._win_x}+{self._win_y}")

    def _on_release(self, e):
        if self._dragging:
            self._dragging = False
            self._press = None
            sw = self.winfo_screenwidth()
            cxs = (sw - self._W) // 2
            if abs(self._win_x - cxs) < 60 * self._S and self._win_y < 50 * self._S:
                self._win_x, self._win_y = cxs, 0
                self.geometry(f"+{self._win_x}+{self._win_y}")
            self._prefs["island_x"] = self._win_x
            self._prefs["island_y"] = self._win_y
            _save_prefs(self._prefs)
            return
        self._press = None
        rx, ry = e.x_root - self._win_x, e.y_root - self._win_y
        if self._click_job:
            try:
                self.after_cancel(self._click_job)
            except Exception:
                pass
        self._click_job = self.after(230, lambda: self._single_click(rx, ry))

    def _on_double(self, e):
        if self._click_job:
            try:
                self.after_cancel(self._click_job)
            except Exception:
                pass
            self._click_job = None
        self._toggle_chat_window()

    def _single_click(self, rx, ry):
        self._click_job = None
        for (x0, y0, x1, y1, (kind, val)) in self._hit:
            if x0 <= rx <= x1 and y0 <= ry <= y1:
                if kind == "action":
                    self._ui_mode = None
                    self._fire_quick_action(val)
                elif kind == "chip":
                    self._fire_suggestion(*val)
                return
        x0, y0, x1, y1 = self._island_rect
        if not (x0 <= rx <= x1 and y0 <= ry <= y1):
            return
        if self._state == "idle":
            if self._ui_mode == "actions":
                self._ui_mode = None
            else:
                self._ui_mode = "actions"
                self._actions_t = time.perf_counter()
        elif self._state in ("success", "error", "info", "suggesting"):
            self.set_state("hide")
        else:
            self._squash.vel += 4.5
            self._antenna_sway.vel += 10.0

    def _fire_suggestion(self, label, cid):
        cb = self._suggestion_cb
        self._suggestions = None
        self.set_state("hide")
        try:
            if cb:
                cb(cid if cid is not None else label)
            elif self._on_quick_action:
                self._on_quick_action(f"suggest:{cid if cid is not None else label}")
        except Exception as e:
            print(f"⚠️ suggestion callback failed: {e}")

    def _show_context_menu(self, event):
        menu = Menu(self, tearoff=0, bg="#0E121B", fg="#F8FAFC",
                    activebackground="#0284C7", activeforeground="#FFFFFF",
                    font=("Segoe UI", 10), bd=1, relief="flat")
        menu.add_command(label="⌨️ كتابة أمر سريع", command=self.show_inline_input)
        menu.add_command(label="⌘ لوحة الأوامر السريعة", command=self._open_palette)
        menu.add_command(label="💬 نافذة المحادثة", command=self._toggle_chat_window)
        menu.add_separator()
        modes_menu = Menu(menu, tearoff=0, bg="#0E121B", fg="#F8FAFC",
                          activebackground="#0284C7", activeforeground="#FFFFFF",
                          font=("Segoe UI", 10))
        modes_menu.add_command(label="💻 مود المذاكرة والكودينج", command=lambda: self._fire_quick_action("study"))
        modes_menu.add_command(label="🎮 مود الجيمينج", command=lambda: self._fire_quick_action("gaming"))
        modes_menu.add_command(label="🍿 مود السينما والروقان", command=lambda: self._fire_quick_action("cinema"))
        menu.add_cascade(label="🎯 الأوضاع الذكية", menu=modes_menu)
        menu.add_command(label="🚀 تنظيف وتفريغ الرامات", command=lambda: self._fire_quick_action("ram"))
        menu.add_command(label="💧 سجّل كوباية مياه (+1)", command=lambda: self._fire_quick_action("water"))
        menu.add_separator()
        theme_menu = Menu(menu, tearoff=0, bg="#0E121B", fg="#F8FAFC",
                          activebackground="#0284C7", activeforeground="#FFFFFF",
                          font=("Segoe UI", 10))
        theme_menu.add_command(label="داكن", command=lambda: self.set_theme("dark"))
        theme_menu.add_command(label="فاتح", command=lambda: self.set_theme("light"))
        theme_menu.add_command(label="تلقائي (النظام)", command=lambda: self.set_theme("auto"))
        menu.add_cascade(label="🎨 الثيم", menu=theme_menu)
        menu.add_command(label="📜 إظهار السجل", command=self.show_notification_history)
        menu.add_command(label="🗑️ مسح السجل", command=self.clear_notification_history)
        menu.add_separator()
        menu.add_command(label="⚡ الأوامر السريعة", command=self._toggle_quick_actions)
        menu.add_command(label="🎮 الـ Game Overlay", command=self._toggle_overlay)
        menu.add_command(label="✨ استعراض الحالات", command=self.run_demo)
        menu.add_command(label=("🔇 كتم الأصوات" if self._sounds else "🔊 تشغيل الأصوات"),
                         command=self._toggle_sounds)
        if self._companion_get and self._companion_toggle:
            try:
                on = bool(self._companion_get())
            except Exception:
                on = True
            menu.add_command(label=("🙊 إيقاف أسئلة يوبي" if on else "💬 تشغيل أسئلة يوبي"),
                             command=self._toggle_companion)
        menu.add_separator()
        menu.add_command(label="⚙️ الإعدادات", command=self._open_settings)
        menu.add_command(label="↺ إعادة تعيين الموضع", command=self._reset_position)
        menu.add_command(label="❌ خروج", command=lambda: self.event_generate("<<YobiQuit>>"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_companion(self):
        try:
            on = bool(self._companion_toggle())
        except Exception:
            return
        self.say("هرجع أسألك وأطمن عليك 💬" if on else "تمام، مش هسألك حاجة لحد ما تشغلها تاني 🙊",
                 state="info")

    def _toggle_sounds(self):
        self._sounds = not self._sounds
        self._prefs["sounds"] = self._sounds
        _save_prefs(self._prefs)

    def _reset_position(self):
        self._win_x = (self.winfo_screenwidth() - self._W) // 2
        self._win_y = 0
        self.geometry(f"+{self._win_x}+{self._win_y}")
        self._prefs["island_x"] = self._win_x
        self._prefs["island_y"] = self._win_y
        _save_prefs(self._prefs)

    def _open_settings(self):
        try:
            from ui_extras import SettingsWindow
            SettingsWindow(self, island=self, agent=getattr(self, "_agent", None))
        except Exception as e:
            print(f"⚠️ فتح الإعدادات فشل: {e}")

    def _open_palette(self):
        try:
            from ui_extras import CommandPalette
            CommandPalette(self, island=self, agent=getattr(self, "_agent", None))
        except Exception as e:
            print(f"⚠️ فتح لوحة الأوامر فشل: {e}")

    def _toggle_quick_actions(self):
        if self._ui_mode == "actions":
            self._ui_mode = None
        else:
            if self._state != "idle":
                self.set_state("hide")
            self._ui_mode = "actions"
            self._actions_t = time.perf_counter()

    def _show_quick_actions(self):
        if self._ui_mode != "actions":
            self._toggle_quick_actions()

    def _hide_quick_actions(self):
        self._ui_mode = None

    def _on_mousewheel(self, event):
        if not self._hover:
            return
        try:
            from system_control import volume_up, volume_down
            res = volume_up() if event.delta > 0 else volume_down()
            import re
            m = re.search(r"(\d+)%", res)
            if m:
                self.set_progress(int(m.group(1)) / 100.0)
            self.set_state("info", res, quiet=True)
            self._schedule_hide(1800)
        except Exception:
            pass

    def show_inline_input(self):
        """Animated glassmorphic inline command bar below the Dynamic Island."""
        if self._inline_bar is not None and self._inline_bar.winfo_exists():
            try:
                self._inline_bar.destroy()
            except Exception:
                pass
            self._inline_bar = None
            return

        bar = tk.Toplevel(self)
        bar.overrideredirect(True)
        bar.attributes("-topmost", True)
        bar.configure(bg="#0B0F17", highlightthickness=2, highlightbackground="#38BDF8")
        try:
            bar.attributes("-alpha", 0.0)
        except Exception:
            pass

        bw, bh = int(420 * self._S), int(50 * self._S)
        bx = max(0, self._win_x + (self._W - bw) // 2)
        target_y = max(0, self._win_y + int(self._island_rect[3]) + int(10 * self._S))
        start_y = max(0, target_y - int(14 * self._S))
        bar.geometry(f"{bw}x{bh}+{bx}+{start_y}")

        badge = tk.Label(
            bar, text="✨ يوبي", bg="#0F293A", fg="#38BDF8",
            font=("Segoe UI Semibold", int(10 * self._S)), padx=10, pady=4,
        )
        badge.pack(side="right", padx=(6, 10), pady=8)

        ent = tk.Entry(
            bar, bg="#0B0F17", fg="#F8FAFC", insertbackground="#38BDF8",
            relief="flat", font=("Segoe UI", int(12 * self._S)), justify="right",
        )
        ent.pack(side="right", fill="both", expand=True, padx=8, pady=8)
        ent.focus_set()

        # Smooth slide + fade-in animation
        def _anim_in(step=0):
            if not bar.winfo_exists():
                return
            t = _smooth((step + 1) / 6.0)
            cy = int(start_y + (target_y - start_y) * t)
            bar.geometry(f"{bw}x{bh}+{bx}+{cy}")
            try:
                bar.attributes("-alpha", 0.96 * t)
            except Exception:
                pass
            if step < 5:
                bar.after(16, lambda: _anim_in(step + 1))

        if not self._reduced_motion:
            _anim_in()
        else:
            bar.geometry(f"{bw}x{bh}+{bx}+{target_y}")
            try:
                bar.attributes("-alpha", 0.96)
            except Exception:
                pass

        def _submit(_e=None):
            q = ent.get().strip()
            bar.destroy()
            self._inline_bar = None
            if not q:
                return
            self.set_state("thinking", f"بنفذ: {q}...")

            def _run():
                try:
                    r = self._on_chat_send(q) if self._on_chat_send else f"تم: {q}"
                except Exception as ex:
                    r = f"حصل خطأ: {ex}"
                self.after(0, lambda: self.say(str(r or "تم التنفيذ ✅"), state="success"))
            threading.Thread(target=_run, daemon=True).start()

        ent.bind("<Return>", _submit)
        ent.bind("<Escape>", lambda e: bar.destroy())
        bar.bind("<FocusOut>", lambda e: self.after(150, lambda: bar.destroy() if bar.winfo_exists() else None))
        self._inline_bar = bar

    def _fire_quick_action(self, action_id):
        if self._on_quick_action:
            try:
                self._on_quick_action(action_id)
            except Exception as e:
                print(f"⚠️ quick action failed: {e}")
        if action_id == "chat":
            self._toggle_chat_window()
        elif action_id == "palette":
            self._open_palette()
        elif action_id == "settings":
            self._open_settings()
        elif action_id == "screenshot":
            try:
                from system_control import take_screenshot
                self.set_state("success", take_screenshot())
            except Exception:
                pass
        elif action_id == "ram":
            try:
                from device_control import handle_free_ram
                self.set_state("success", handle_free_ram())
            except Exception as e:
                self.set_state("error", f"فشل تنظيف الرام: {e}")
        elif action_id in ("study", "gaming", "cinema"):
            try:
                from device_control import activate_smart_mode
                self.set_state("success", activate_smart_mode(action_id))
            except Exception as e:
                self.set_state("error", f"فشل تفعيل الوضع: {e}")
        elif action_id == "water":
            try:
                res = self._on_chat_send("شربت مياه") if self._on_chat_send else "عاش 💧 بالهنا والشفا!"
                self.say(str(res), state="success")
            except Exception:
                self.say("عاش 💧 بالهنا والشفا!", state="success")
        elif action_id == "listen" and not self._on_quick_action:
            self.set_state("listening")

    def _add_to_history(self, state, text):
        self._notification_history.append({"state": state, "text": text, "timestamp": time.time()})
        if len(self._notification_history) > self._max_history:
            self._notification_history = self._notification_history[-self._max_history:]
        if self._history_panel is not None:
            self._history_panel.refresh(self._notification_history)

    def _toggle_history_panel(self):
        if self._history_panel is not None:
            try:
                self._history_panel.destroy()
            except Exception:
                pass
            self._history_panel = None
            self._history_visible = False
            return
        x = self._win_x + self._W // 2 - int(200 * self._S)
        y = self._win_y + int(self._island_rect[3]) + int(14 * self._S)
        self._history_panel = HistoryPanel(self, self._PAL, self._notification_history,
                                           x, y, on_close=self._history_closed,
                                           on_clear=self.clear_notification_history)
        self._history_visible = True

    def _show_history_panel(self):
        if self._history_panel is None:
            self._toggle_history_panel()

    def _hide_history_panel(self):
        if self._history_panel is not None:
            self._toggle_history_panel()

    def _history_closed(self):
        self._history_panel = None
        self._history_visible = False

    def _toggle_chat_window(self):
        try:
            from chat_window import ChatWindow
            if self._chat_window is None or not self._chat_window.winfo_exists():
                self._chat_window = ChatWindow(
                    master=self,
                    on_send_message=self._on_chat_send,
                    on_voice_toggle=lambda: self._fire_quick_action("listen"),
                )
            else:
                self._chat_window.toggle()
        except ImportError:
            print("⚠️ chat_window.py مش موجود")
        except Exception as e:
            print(f"⚠️ Chat window error: {e}")

    def _on_chat_send(self, text):
        return f"استلمت: {text}"

    def set_chat_handler(self, handler):
        self._on_chat_send = handler

    def add_chat_message(self, role, text):
        if self._chat_window and self._chat_window.winfo_exists():
            self._chat_window.add_message(role, text)

    def _toggle_overlay(self):
        try:
            from overlay_ui import GameOverlay
            if self._overlay is None:
                self._overlay = GameOverlay(master=self)
                self._overlay.show_mini()
            else:
                self._overlay.toggle()
        except ImportError:
            print("⚠️ overlay_ui.py مش موجود")
        except Exception as e:
            print(f"⚠️ Overlay error: {e}")

    def get_overlay(self):
        return self._overlay

    def run_demo(self):
        """Walk through every state once (also in the right-click menu)."""
        steps = [
            (0, lambda: self.set_state("listening", "سامعك.. اتكلم 🎤")),
            (3500, lambda: self.set_state("thinking", "بفكر في طلبك...")),
            (6500, lambda: (self.set_state("executing", "بفتح Valorant ⚙️"), self.set_progress(2.0))),
            (9500, lambda: self.set_state("thinking", "بجهزلك حساب Riot 🔐")),
            (12500, lambda: self.set_state("success", "دخلت بحساب Riot ✅")),
            (15500, lambda: self.set_state("info", "مساء الروقان! 🍿 إيه رأيك نشغل فيلم على نتفليكس أو نلعب شوية؟")),
            (20500, lambda: (self.set_speaking(True), self.set_state("speaking", "حاضر، بقولك أهو..."))),
            (24000, lambda: (self.set_speaking(None), self.set_state("info", "بسجل... دوس F9 لما تخلص"))),
            (28000, lambda: self.set_state("error", "معرفتش ألاقي البرنامج ده")),
            (32500, lambda: self.set_state("hide")),
        ]
        for ms, fn in steps:
            self.after(ms, fn)


class HistoryPanel(tk.Toplevel):
    """Animated Obsidian History Panel with filter pills, icons, and click-to-copy."""
    FILTERS = [("الكل", None), ("نجاح ✅", "success"), ("أخطاء ❌", "error"), ("معلومات 💡", "info")]
    EDGE = {"success": "#34d399", "error": "#f87171", "info": "#a78bfa",
            "suggesting": "#f472b6"}
    BADGE = {"success": "✅", "error": "❌", "info": "ℹ️", "suggesting": "💡"}

    def __init__(self, master, pal, items, x, y, on_close=None, on_clear=None):
        super().__init__(master)
        self._pal = pal
        self._items = items
        self._filter = None
        self._on_close = on_close
        self._on_clear = on_clear
        self.title("سجل إشعارات يوبي")
        self.attributes("-topmost", True)
        self._target_y = max(0, y)
        self._x = max(0, x)
        self.geometry(f"400x480+{self._x}+{max(0, self._target_y - 12)}")
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda e: self._close())
        self._build()
        self.refresh(items)
        self._animate_open()

    def _animate_open(self, step=0):
        if not self.winfo_exists():
            return
        t = _smooth((step + 1) / 6.0)
        cy = int(max(0, self._target_y - 12) + 12 * t)
        self.geometry(f"400x480+{self._x}+{cy}")
        try:
            self.attributes("-alpha", 0.98 * t)
        except Exception:
            pass
        if step < 5:
            self.after(16, lambda: self._animate_open(step + 1))

    def _build(self):
        p = self._pal
        self.configure(bg=p["history_bg"])
        head = tk.Frame(self, bg=p["history_bg"])
        head.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(head, text="📜 سجل يوبي", bg=p["history_bg"], fg=p["text"],
                 font=("Segoe UI Semibold", 14)).pack(side="right")
        tk.Button(head, text="🗑️ مسح الكل", command=self._clear, bg=p["card_bg"], fg=p["text_dim"],
                  bd=0, padx=12, pady=4, cursor="hand2",
                  activebackground=p["card_border"]).pack(side="left")

        self._chips = tk.Frame(self, bg=p["history_bg"])
        self._chips.pack(fill="x", padx=12, pady=(2, 8))
        self._chip_btns = []
        for label, key in self.FILTERS:
            b = tk.Label(self._chips, text=label, padx=12, pady=5, cursor="hand2",
                         font=("Segoe UI Semibold", 9))
            b.pack(side="right", padx=3)
            b.bind("<Button-1>", lambda e, k=key: self._set_filter(k))
            self._chip_btns.append((b, key))

        self._toast_lbl = tk.Label(self, text="", bg="#0284c7", fg="#ffffff",
                                   font=("Segoe UI Semibold", 9), padx=10, pady=3)

        wrap = tk.Frame(self, bg=p["history_bg"])
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self._cv = tk.Canvas(wrap, bg=p["history_bg"], highlightthickness=0, bd=0)
        sb = tk.Scrollbar(wrap, orient="vertical", command=self._cv.yview)
        self._cv.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        self._cv.pack(side="right", fill="both", expand=True)
        self._list = tk.Frame(self._cv, bg=p["history_bg"])
        self._win = self._cv.create_window(0, 0, window=self._list, anchor="nw")
        self._list.bind("<Configure>", lambda e: self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>", lambda e: self._cv.itemconfigure(self._win, width=e.width))
        self._cv.bind_all("<MouseWheel>", self._wheel)

    def _copy_item(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._toast_lbl.configure(text="📋 تم نسخ الإشعار")
            self._toast_lbl.place(relx=0.5, rely=0.92, anchor="center")
            self.after(1400, lambda: self._toast_lbl.place_forget() if self.winfo_exists() else None)
        except Exception:
            pass

    def _wheel(self, e):
        try:
            self._cv.yview_scroll(int(-e.delta / 120), "units")
        except Exception:
            pass

    def _set_filter(self, key):
        self._filter = key
        self.refresh(self._items)

    def apply_theme(self, pal):
        self._pal = pal
        for w in self.winfo_children():
            w.destroy()
        self._build()
        self.refresh(self._items)

    def refresh(self, items):
        self._items = items
        p = self._pal
        for b, key in self._chip_btns:
            on = key == self._filter
            b.configure(bg=p["info_acc"] if on else p["card_bg"],
                        fg="#ffffff" if on else p["text_dim"])
        for w in self._list.winfo_children():
            w.destroy()
        shown = [it for it in reversed(items)
                 if self._filter is None or it["state"] == self._filter
                 or (self._filter == "info" and it["state"] == "suggesting")]
        if not shown:
            tk.Label(self._list, text="✨ مفيش إشعارات هنا لسه", bg=p["history_bg"],
                     fg=p["text_dim"], font=("Segoe UI", 11)).pack(pady=45)
            return
        for it in shown:
            card = tk.Frame(self._list, bg=p["card_bg"], highlightthickness=1,
                            highlightbackground=p["card_border"], cursor="hand2")
            card.pack(fill="x", padx=6, pady=4)
            edge_col = self.EDGE.get(it["state"], "#94a3b8")
            tk.Frame(card, bg=edge_col, width=4).pack(side="right", fill="y")
            body = tk.Frame(card, bg=p["card_bg"])
            body.pack(side="right", fill="both", expand=True, padx=10, pady=8)
            badge = self.BADGE.get(it["state"], "ℹ️")
            lbl = tk.Label(body, text=f"{badge}  {it['text']}", bg=p["card_bg"], fg=p["text"],
                           wraplength=310, justify="right", anchor="e", font=("Segoe UI", 10))
            lbl.pack(fill="x")
            ts = time.strftime("%I:%M %p", time.localtime(it["timestamp"]))
            meta = tk.Label(body, text=f"{ts}  •  اضغط للنسخ 📋", bg=p["card_bg"],
                            fg=p["text_dim"], anchor="e", font=("Segoe UI", 8))
            meta.pack(fill="x", pady=(2, 0))
            for w_ in (card, body, lbl, meta):
                w_.bind("<Button-1>", lambda e, t=it["text"]: self._copy_item(t))

    def _clear(self):
        if self._on_clear:
            self._on_clear()

    def _close(self):
        try:
            self._cv.unbind_all("<MouseWheel>")
        except Exception:
            pass
        if self._on_close:
            self._on_close()
        self.destroy()


if __name__ == "__main__":
    island = DynamicIsland()
    island.bind("<<YobiQuit>>", lambda e: island.quit())

    def loop_demo():
        island.run_demo()
        island.after(36000, loop_demo)

    island.after(800, loop_demo)
    island.mainloop()