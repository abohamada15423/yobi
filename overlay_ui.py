# -*- coding: utf-8 -*-
"""
Yobi Game Overlay v5 — Anti-Aliased Bioluminescent HUD & Cartoon Gamer Yobi.
Renders 2x supersampled Pillow HUD cards with smooth spring slide-in/out transitions,
animated CPU/RAM/GPU telemetry bars, a blinking cartoon Yobi with gaming headset,
and real microphone audio waveforms with full Windows click-through.
"""

import math
import platform
import random
import time
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

KEY_COLOR = "#010203"
KEY_RGB = (1, 2, 3)

BG_CARD = (11, 15, 24)
BG_BAR = (28, 38, 56)
ACCENT = (56, 189, 248)
EMERALD = (52, 211, 153)
AMBER = (251, 191, 36)
DANGER = (248, 113, 113)
TEXT = (248, 250, 252)
MUTED = (148, 163, 184)
IS_WIN = platform.system().lower() == "windows"


def _metric_color(val):
    try:
        v = float(val)
    except Exception:
        return EMERALD
    if v >= 85:
        return DANGER
    if v >= 65:
        return AMBER
    return EMERALD


class _Spring:
    __slots__ = ("v", "t", "vel", "k", "c")

    def __init__(self, v=0.0, k=210.0, c=20.0):
        self.v = float(v)
        self.t = float(v)
        self.vel = 0.0
        self.k = k
        self.c = c

    def step(self, dt):
        a = self.k * (self.t - self.v) - self.c * self.vel
        self.vel += a * dt
        self.v += self.vel * dt

    def settled(self, eps=0.015):
        return abs(self.t - self.v) < eps and abs(self.vel) < eps * 3


class GameOverlay(tk.Toplevel):
    """Click-through gaming HUD with spring animations and anti-aliased Pillow cards."""

    def __init__(self, master=None):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=KEY_COLOR)
        try:
            self.attributes("-transparentcolor", KEY_COLOR)
        except tk.TclError:
            pass

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

        self._visible = False
        self._mini = False
        self._subtitle = ""
        self._perf = {}
        self._listening = False
        self._phase = 0.0
        self._last_t = time.perf_counter()
        self._tick_job = None
        self._sub_job = None

        # Slide-in presence springs (0.0 = hidden offscreen, 1.0 = shown)
        self._mini_spr = _Spring(0.0, 220, 20)
        self._perf_spr = _Spring(0.0, 200, 19)
        self._sub_spr = _Spring(0.0, 230, 21)
        self._bar_springs = {
            "CPU": _Spring(0.0, 140, 18),
            "RAM": _Spring(0.0, 140, 18),
            "GPU": _Spring(0.0, 140, 18),
        }

        # Cartoon gamer Yobi state
        self._blink_next = time.perf_counter() + 2.5
        self._blink_t = -1.0
        self._lookx = 0.0
        self._photos = {}

        self._cv = tk.Canvas(self, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self._cv.pack(fill="both", expand=True)

        self._apply_click_through()
        self.withdraw()

    def _apply_click_through(self):
        if not IS_WIN:
            return
        try:
            import ctypes
            self.update_idletasks()
            u32 = ctypes.windll.user32
            hwnd = u32.GetAncestor(self.winfo_id(), 2) or self.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            )
        except Exception:
            pass

    def _font(self, size, bold=True):
        try:
            import os
            win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
            p = os.path.join(win, "seguisb.ttf" if bold else "segoeui.ttf")
            if os.path.exists(p):
                return ImageFont.truetype(p, int(size))
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size))
        except Exception:
            return ImageFont.load_default()

    def _mic_level(self, now):
        try:
            import audio_io
            eng = audio_io.get_audio_engine()
            if eng is not None:
                return min(1.0, float(eng.level) * 1.9)
        except Exception:
            pass
        return 0.25 + 0.55 * abs(math.sin(now * 3.1)) * (0.5 + 0.5 * math.cos(now * 7.3))

    def _ensure_loop(self):
        if self._visible and self._tick_job is None:
            self._last_t = time.perf_counter()
            self._tick()

    def show_mini(self):
        self.after(0, self._show_mini_ui)

    def _show_mini_ui(self):
        self._mini = True
        self._mini_spr.t = 1.0
        self._visible = True
        self.deiconify()
        self._apply_click_through()
        self._ensure_loop()

    def hide_mini(self):
        self.after(0, self._hide_mini_ui)

    def _hide_mini_ui(self):
        self._mini = False
        self._mini_spr.t = 0.0
        self._maybe_hide()

    def show_subtitle(self, text, duration=3.0):
        def _do():
            self._subtitle = str(text or "")
            self._sub_spr.t = 1.0 if self._subtitle else 0.0
            self._visible = True
            self.deiconify()
            self._apply_click_through()
            self._ensure_loop()
            if self._sub_job:
                try:
                    self.after_cancel(self._sub_job)
                except Exception:
                    pass
            self._sub_job = self.after(int(duration * 1000), self._clear_subtitle)
        self.after(0, _do)

    def _clear_subtitle(self):
        self._sub_job = None
        self._subtitle = ""
        self._sub_spr.t = 0.0
        self._maybe_hide()

    def show_perf_hud(self, fps=None, cpu=None, ram=None, gpu=None):
        def _do():
            self._perf = {"fps": fps, "cpu": cpu, "ram": ram, "gpu": gpu}
            self._perf_spr.t = 1.0
            self._visible = True
            self.deiconify()
            self._apply_click_through()
            self._ensure_loop()
        self.after(0, _do)

    def hide_perf_hud(self):
        def _do():
            self._perf = {}
            self._perf_spr.t = 0.0
            self._maybe_hide()
        self.after(0, _do)

    def update_perf(self):
        if not _HAS_PSUTIL:
            return
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            self.show_perf_hud(
                fps=self._perf.get("fps"),
                cpu=cpu,
                ram=ram,
                gpu=self._perf.get("gpu"),
            )
        except Exception:
            pass

    def set_listening(self, listening):
        def _do():
            self._listening = bool(listening)
            if self._listening:
                self._mini_spr.t = 1.0
                self._visible = True
                self.deiconify()
                self._apply_click_through()
                self._ensure_loop()
            else:
                if not self._mini:
                    self._mini_spr.t = 0.0
                self._maybe_hide()
        self.after(0, _do)

    def show(self):
        self.show_mini()

    def hide(self):
        def _do():
            self._visible = False
            self._mini = False
            self._mini_spr.t = 0.0
            self._perf_spr.t = 0.0
            self._sub_spr.t = 0.0
            self._cv.delete("all")
            self._photos.clear()
            if self._tick_job is not None:
                try:
                    self.after_cancel(self._tick_job)
                except Exception:
                    pass
                self._tick_job = None
            self.withdraw()
        self.after(0, _do)

    def toggle(self):
        self.hide() if self._visible else self.show_mini()

    def _maybe_hide(self):
        if (not self._mini and not self._subtitle and not self._perf and not self._listening
                and self._mini_spr.v < 0.03 and self._perf_spr.v < 0.03 and self._sub_spr.v < 0.03):
            self.hide()

    def _render_mini_pill(self, now):
        """Render anti-aliased 2x top mini pill with cartoon gamer Yobi & live waveform."""
        W, H = 320 * 2, 46 * 2
        im = Image.new("RGB", (W, H), KEY_RGB)
        d = ImageDraw.Draw(im)
        border = ACCENT if self._listening else EMERALD
        d.rounded_rectangle([4, 4, W - 4, H - 4], radius=42, fill=BG_CARD, outline=border, width=4)

        # Mini Cartoon Gamer Yobi on the left
        cx, cy, r = 46, H // 2, 26
        # Headset band + ear pods
        d.arc([cx - r * 1.08, cy - r * 1.15, cx + r * 1.08, cy + r * 0.7], 195, 345, fill=border, width=4)
        for sgn in (-1, 1):
            ex_p = cx + sgn * (r + 3)
            d.rounded_rectangle([ex_p - 5, cy - 10, ex_p + 5, cy + 10], radius=4, fill=border)
        # Body
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(14, 42, 62), outline=border, width=3)
        d.ellipse([cx - r * 0.45, cy - r * 0.65, cx - r * 0.05, cy - r * 0.35], fill=(200, 240, 255))
        # Blink & eyes
        blink = 1.0
        if self._blink_t >= 0:
            bt = (now - self._blink_t) / 0.15
            blink = abs(1 - 2 * max(0.0, min(1.0, bt)))
        eh = max(2, int(11 * blink))
        ox = math.sin(now * 1.7) * 3.0
        for sgn in (-1, 1):
            ex = cx + sgn * 9 + ox
            d.rounded_rectangle([ex - 3.5, cy - eh / 2 - 1, ex + 3.5, cy + eh / 2 - 1],
                                radius=3, fill=TEXT)
        # Smile or talking mouth
        if self._listening:
            d.ellipse([cx - 5 + ox * 0.5, cy + 7, cx + 5 + ox * 0.5, cy + 15], fill=border)
        else:
            d.arc([cx - 6 + ox * 0.5, cy + 4, cx + 6 + ox * 0.5, cy + 13], 20, 160, fill=border, width=3)

        # Status text
        f = self._font(22, bold=True)
        label = "سامعك.. اتكلم 🎤" if self._listening else "يوبي معاك 🎮"
        d.text((92, H // 2 - 13), label, fill=TEXT, font=f)

        # Live Audio Waveform when listening
        if self._listening:
            lvl = self._mic_level(now)
            n = 14
            wx0 = W - 210
            for i in range(n):
                env = math.sin((i + 0.5) / n * math.pi)
                bh = max(8, (10 + 48 * lvl * env * (0.4 + 0.6 * abs(math.sin(now * 8.0 + i * 0.65)))))
                bx = wx0 + i * 13
                col = ACCENT if i % 2 == 0 else EMERALD
                d.rounded_rectangle([bx, H // 2 - bh / 2, bx + 7, H // 2 + bh / 2], radius=3, fill=col)

        return im.resize((320, 46), Image.LANCZOS)

    def _render_perf_card(self, rows):
        """Render anti-aliased 2x telemetry HUD card with smooth progress bars."""
        W = 236 * 2
        H = (44 + len(rows) * 28) * 2
        im = Image.new("RGB", (W, H), KEY_RGB)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([4, 4, W - 4, H - 4], radius=32, fill=BG_CARD, outline=(36, 48, 72), width=4)

        f_head = self._font(18, bold=True)
        f_row = self._font(18, bold=True)
        d.text((28, 22), "⚡ YOBI TELEMETRY", fill=ACCENT, font=f_head)

        for idx, (label, val) in enumerate(rows):
            ry = (46 + idx * 27) * 2
            col = _metric_color(val)
            is_pct = isinstance(val, (int, float)) and label in ("CPU", "RAM", "GPU")
            shown_v = self._bar_springs[label].v if label in self._bar_springs and is_pct else val
            val_str = f"{shown_v:.0f}%" if is_pct else str(val)
            d.text((28, ry - 12), label, fill=MUTED, font=f_row)
            d.text((W - 88, ry - 12), val_str, fill=TEXT, font=f_row)
            if is_pct:
                bx0, bx1 = 122, W - 110
                d.rounded_rectangle([bx0, ry - 7, bx1, ry + 7], radius=7, fill=BG_BAR)
                fill_w = max(8, int((bx1 - bx0) * max(0.0, min(100.0, float(shown_v))) / 100.0))
                d.rounded_rectangle([bx0, ry - 7, bx0 + fill_w, ry + 7], radius=7, fill=col)

        return im.resize((W // 2, H // 2), Image.LANCZOS)

    def _render_subtitle_pill(self, text):
        tw = max(280, min(820, len(text) * 11 + 64))
        W, H = tw * 2, 54 * 2
        im = Image.new("RGB", (W, H), KEY_RGB)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([4, 4, W - 4, H - 4], radius=36, fill=BG_CARD, outline=ACCENT, width=3)
        f = self._font(26, bold=True)
        d.text((W // 2, H // 2), text, fill=TEXT, font=f, anchor="mm")
        return im.resize((tw, 54), Image.LANCZOS)

    def _tick(self):
        self._tick_job = None
        if not self._visible:
            return
        now = time.perf_counter()
        dt = max(0.005, min(0.05, now - self._last_t))
        self._last_t = now
        self._phase += dt * 4.0

        if self._blink_t < 0 and now >= self._blink_next:
            self._blink_t = now
        elif self._blink_t >= 0 and now - self._blink_t > 0.15:
            self._blink_t = -1.0
            self._blink_next = now + random.uniform(2.5, 5.2)

        self._mini_spr.t = 1.0 if (self._mini or self._listening) else 0.0
        self._perf_spr.t = 1.0 if bool(self._perf) else 0.0
        self._sub_spr.t = 1.0 if bool(self._subtitle) else 0.0

        for k, v in (self._perf or {}).items():
            ku = k.upper()
            if ku in self._bar_springs and isinstance(v, (int, float)):
                self._bar_springs[ku].t = float(v)

        for spr in (self._mini_spr, self._perf_spr, self._sub_spr, *self._bar_springs.values()):
            spr.step(dt)

        self._cv.delete("all")
        w = self.winfo_screenwidth()
        h_scr = self.winfo_screenheight()

        # 1. Top Mini Pill with slide-down spring
        if self._mini_spr.v > 0.02:
            img = self._render_mini_pill(now)
            self._photos["mini"] = ImageTk.PhotoImage(img)
            y_pos = int(-55 + 67 * self._mini_spr.v)
            self._cv.create_image(w // 2, y_pos, image=self._photos["mini"], anchor="n")

        # 2. Subtitle Pill with slide-up spring
        if self._sub_spr.v > 0.02 and self._subtitle:
            img = self._render_subtitle_pill(self._subtitle)
            self._photos["sub"] = ImageTk.PhotoImage(img)
            sy = int(h_scr + 40 - 150 * self._sub_spr.v)
            self._cv.create_image(w // 2, sy, image=self._photos["sub"], anchor="center")

        # 3. Performance HUD Card with slide-left spring & animated bars
        rows = [(k.upper(), v) for k, v in self._perf.items() if v is not None]
        if self._perf_spr.v > 0.02 and rows:
            img = self._render_perf_card(rows)
            self._photos["perf"] = ImageTk.PhotoImage(img)
            x_pos = int(w + 250 - 498 * self._perf_spr.v)
            self._cv.create_image(x_pos, 68, image=self._photos["perf"], anchor="nw")

        self._maybe_hide()
        if not self._visible:
            return

        animating = not (self._mini_spr.settled() and self._perf_spr.settled() and self._sub_spr.settled())
        fps_delay = 25 if (self._listening or animating) else 120
        self._tick_job = self.after(fps_delay, self._tick)