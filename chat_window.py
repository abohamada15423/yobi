# -*- coding: utf-8 -*-
"""
Yobi Chat Window v6 — Obsidian Bioluminescence & Live Cartoon Avatar UI.
Built with CustomTkinter + Pillow live cartoon avatar renderer, streaming message
typewriter reveal, animated bouncing-dot typing indicator, TTS replay button,
window fade-in animation, and prefers-reduced-motion support.
"""

import ctypes
import math
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
import numpy as np
from PIL import Image, ImageDraw, ImageTk

import customtkinter as ctk


def _to_user():
    """" يا <name>" from config.json → "user_name", or "" (a friend's PC: the greeting has no name)."""
    import json
    import os
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"), encoding="utf-8") as f:
            name = str(json.load(f).get("user_name") or "").strip()
    except Exception:
        name = ""
    return f" يا {name}" if name else ""

TOKENS = {
    "bg": "#07090E",
    "surface": "#0D111A",
    "surface_elev": "#121826",
    "card": "#151C2C",
    "card_hover": "#1E273B",
    "border": "#232D42",
    "user_bubble": "#0C3446",
    "user_border": "#0284C7",
    "bot_bubble": "#131926",
    "bot_border": "#28354E",
    "text": "#F8FAFC",
    "text_muted": "#94A3B8",
    "accent": "#38BDF8",
    "accent_hover": "#0284C7",
    "emerald": "#34D399",
    "amber": "#FBBF24",
    "violet": "#A78BFA",
    "danger": "#F87171",
    "font_main": "Segoe UI",
}


def prefers_reduced_motion() -> bool:
    if sys.platform != "win32":
        return False
    try:
        anim = ctypes.c_bool(True)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(anim), 0)
        return not bool(anim.value)
    except Exception:
        return False


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix_rgb(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class ChatWindow(ctk.CTkToplevel):
    """Modern dark-obsidian conversational surface with a living cartoon Yobi header."""

    CHIP_COMMANDS = [
        ("🎮 اقترح لعبة", "اقترح عليا لعبة ألعبها"),
        ("🚀 فضي الرامات", "فضي الرامات"),
        ("💻 مود الكودينج", "فعل مود الكودينج"),
        ("💧 شربت مياه", "شربت مياه"),
        ("👁️ وصف الشاشة", "إيه اللي على الشاشة؟"),
        ("📊 إحصائيات اللعب", "إحصائيات اللعب النهارده"),
    ]

    def __init__(self, master=None, on_send_message=None, on_voice_toggle=None):
        super().__init__(master)
        self._on_send = on_send_message
        if on_voice_toggle is None and master is not None and hasattr(master, "_fire_quick_action"):
            on_voice_toggle = lambda: master._fire_quick_action("listen")
        self._on_voice = on_voice_toggle
        self._messages = []
        self._typing = False
        self._typing_step = 0
        self._typing_job = None
        self._reduced_motion = prefers_reduced_motion()

        # Live cartoon avatar animation state
        self._av_mood = "idle"       # idle | listen | think | talk | happy
        self._av_blink_next = time.perf_counter() + 2.4
        self._av_blink_t = -1.0
        self._av_lookx = 0.0
        self._av_looky = 0.0
        self._av_tx = 0.0
        self._av_ty = 0.0
        self._av_look_next = time.perf_counter() + 1.8
        self._av_mouth = 0.0
        self._av_talking_until = 0.0
        self._av_photo = None
        self._av_job = None

        self.title("يوبي • المحادثة الذكية")
        self.geometry("580x780")
        self.minsize(440, 540)
        self.configure(fg_color=TOKENS["bg"])
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.hide)

        self._build()
        self.bind("<Escape>", lambda e: self.hide())
        self.bind("<Control-e>", lambda e: self._export_chat())
        self.bind("<Control-l>", lambda e: self.clear_chat())
        self.bind("<Control-k>", lambda e: self._entry.focus_set())

        self._animate_avatar()
        self._fade_in()

    def _fade_in(self, step=0):
        if self._reduced_motion or not self.winfo_exists():
            return
        try:
            if step == 0:
                self.attributes("-alpha", 0.0)
            t = (step + 1) / 7.0
            alpha = t * t * (3 - 2 * t)
            self.attributes("-alpha", min(1.0, alpha))
            if step < 6:
                self.after(16, lambda: self._fade_in(step + 1))
        except Exception:
            pass

    def _build(self):
        # ── Header ─────────────────────────────────────────────────
        head = ctk.CTkFrame(
            self, fg_color=TOKENS["surface"], corner_radius=0,
            height=84, border_width=1, border_color=TOKENS["border"],
        )
        head.pack(fill="x")
        head.pack_propagate(False)

        self._avatar_cv = tk.Canvas(
            head, width=58, height=58, bg=TOKENS["surface"], highlightthickness=0, bd=0,
            cursor="hand2",
        )
        self._avatar_cv.pack(side="right", padx=(10, 16), pady=13)
        self._avatar_item = self._avatar_cv.create_image(0, 0, anchor="nw")
        self._avatar_cv.bind("<Button-1>", lambda e: self._poke_avatar())

        title_col = ctk.CTkFrame(head, fg_color="transparent")
        title_col.pack(side="right", pady=14)
        ctk.CTkLabel(
            title_col, text="يوبي • Yobi AI",
            font=(TOKENS["font_main"], 17, "bold"), text_color=TOKENS["text"], anchor="e",
        ).pack(anchor="e")
        self._status_lbl = ctk.CTkLabel(
            title_col, text="● صاحي وجاهز يسمعك  •  اضغط على أي رسالة لنسخها",
            font=(TOKENS["font_main"], 11), text_color=TOKENS["emerald"], anchor="e",
        )
        self._status_lbl.pack(anchor="e")

        actions_row = ctk.CTkFrame(head, fg_color="transparent")
        actions_row.pack(side="left", padx=14)
        ctk.CTkButton(
            actions_row, text="✕", width=36, height=36, corner_radius=11,
            fg_color=TOKENS["card"], hover_color="#451A24", text_color=TOKENS["text_muted"],
            font=(TOKENS["font_main"], 14, "bold"), command=self.hide,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            actions_row, text="🗑️ مسح", width=66, height=36, corner_radius=11,
            fg_color=TOKENS["card"], hover_color=TOKENS["card_hover"], text_color=TOKENS["text_muted"],
            font=(TOKENS["font_main"], 11, "bold"), command=self.clear_chat,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            actions_row, text="💾 حفظ", width=66, height=36, corner_radius=11,
            fg_color=TOKENS["card"], hover_color=TOKENS["card_hover"], text_color=TOKENS["text_muted"],
            font=(TOKENS["font_main"], 11, "bold"), command=self._export_chat,
        ).pack(side="left", padx=3)

        # ── Quick Chips Bar ────────────────────────────────────────
        chips_card = ctk.CTkFrame(
            self, fg_color=TOKENS["surface"], corner_radius=16,
            border_width=1, border_color=TOKENS["border"],
        )
        chips_card.pack(fill="x", padx=16, pady=(12, 6))

        chips_inner = ctk.CTkFrame(chips_card, fg_color="transparent")
        chips_inner.pack(fill="x", padx=10, pady=8)
        for label, cmd in self.CHIP_COMMANDS:
            ctk.CTkButton(
                chips_inner, text=label, height=31, corner_radius=15,
                fg_color=TOKENS["card"], hover_color=TOKENS["accent_hover"],
                border_width=1, border_color=TOKENS["border"],
                text_color=TOKENS["text"], font=(TOKENS["font_main"], 11, "bold"),
                command=lambda c=cmd: self._run_chip(c),
            ).pack(side="right", padx=3, pady=2)

        # ── Messages Scrollable Area ───────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=TOKENS["bg"], corner_radius=0,
            scrollbar_button_color=TOKENS["card"],
            scrollbar_button_hover_color=TOKENS["accent"],
        )
        self._scroll.pack(fill="both", expand=True, padx=10, pady=4)

        self._empty_state = None
        self._render_empty_state()

        # ── Toast Notification Bar (hidden by default) ─────────────
        self._toast = ctk.CTkLabel(
            self, text="", fg_color=TOKENS["accent_hover"], text_color="#FFFFFF",
            corner_radius=12, height=32, font=(TOKENS["font_main"], 11, "bold"),
        )

        # ── Input Composer Bar ─────────────────────────────────────
        bottom = ctk.CTkFrame(
            self, fg_color=TOKENS["surface"], corner_radius=0,
            height=78, border_width=1, border_color=TOKENS["border"],
        )
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        self._entry = ctk.CTkEntry(
            bottom, placeholder_text="اكتب أمرك أو سؤالك هنا... (Enter للإرسال)",
            height=46, corner_radius=15,
            fg_color=TOKENS["card"], border_color=TOKENS["border"],
            text_color=TOKENS["text"], placeholder_text_color=TOKENS["text_muted"],
            font=(TOKENS["font_main"], 13), justify="right",
        )
        self._entry.pack(side="right", fill="x", expand=True, padx=(8, 16), pady=16)
        self._entry.bind("<Return>", lambda e: self._send())
        self._entry.bind("<FocusIn>", lambda e: self._entry.configure(border_color=TOKENS["accent"]))
        self._entry.bind("<FocusOut>", lambda e: self._entry.configure(border_color=TOKENS["border"]))

        ctk.CTkButton(
            bottom, text="إرسال ➤", width=88, height=46, corner_radius=15,
            fg_color=TOKENS["accent"], hover_color=TOKENS["accent_hover"],
            text_color="#061018", font=(TOKENS["font_main"], 13, "bold"),
            command=self._send,
        ).pack(side="left", padx=(16, 6), pady=16)

        self._voice_btn = ctk.CTkButton(
            bottom, text="🎙️", width=46, height=46, corner_radius=15,
            fg_color=TOKENS["card"], hover_color=TOKENS["card_hover"],
            border_width=1, border_color=TOKENS["border"],
            text_color=TOKENS["accent"], font=(TOKENS["font_main"], 17),
            command=self._voice,
        )
        self._voice_btn.pack(side="left", padx=4, pady=16)

    def _poke_avatar(self):
        """Playful cartoon reaction when user clicks Yobi's avatar in the header."""
        self._av_mood = "happy"
        self._av_talking_until = time.perf_counter() + 1.4
        self._show_toast("✨ يوبي معاك وجاهز لأي أمر!")

    def _render_cartoon_avatar(self, now: float) -> Image.Image:
        """Render a 2x supersampled (116x116 -> 58x58) cartoon Yobi avatar."""
        W = 116
        im = Image.new("RGBA", (W, W), (13, 17, 26, 255))
        d = ImageDraw.Draw(im, "RGBA")

        mood = self._av_mood
        if now < self._av_talking_until and mood not in ("think", "listen"):
            mood = "talk"

        palette = {
            "idle":   ((56, 189, 248), (12, 74, 110), (224, 242, 254)),
            "listen": ((56, 189, 248), (2, 132, 199), (224, 242, 254)),
            "think":  ((251, 191, 36), (180, 83, 9),  (254, 243, 199)),
            "talk":   ((45, 212, 191), (15, 118, 110), (204, 251, 241)),
            "happy":  ((52, 211, 153), (4, 120, 87),   (209, 250, 229)),
        }.get(mood, ((56, 189, 248), (12, 74, 110), (224, 242, 254)))
        acc, deep, light = palette

        cx = W / 2
        cy = W / 2 + 4 + math.sin(now * 3.0) * 2.5
        r = 34.0

        # Outer pulsing glow ring
        ring_r = r + 9 + math.sin(now * 3.6) * 2.2
        d.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
                  fill=acc + (38,), outline=acc + (115,), width=2)

        # Cartoon Side Headphones / Ears
        ew_ear, eh_ear = 7.5, 14.0
        for sgn in (-1, 1):
            ex_c = cx + sgn * (r * 0.96)
            d.rounded_rectangle([ex_c - ew_ear, cy - eh_ear, ex_c + ew_ear, cy + eh_ear],
                                radius=6, fill=deep + (255,), outline=acc + (220,), width=2)

        # Bouncy Top Antenna
        sway = math.sin(now * 4.0) * 5.5 + self._av_lookx * 4.0
        ax_tip, ay_tip = cx + sway, cy - r - 11
        d.line([cx, cy - r + 2, ax_tip, ay_tip], fill=acc + (240,), width=3)
        d.ellipse([ax_tip - 5, ay_tip - 5, ax_tip + 5, ay_tip + 5], fill=light + (255,))

        # Main Cartoon Sphere
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=deep + (255,), outline=acc + (245,), width=3)
        d.ellipse([cx - r * 0.85, cy - r * 0.85, cx + r * 0.85, cy + r * 0.85], fill=acc + (215,))
        # Top-left glossy highlight
        d.ellipse([cx - r * 0.52, cy - r * 0.62, cx - r * 0.06, cy - r * 0.32],
                  fill=(255, 255, 255, 105))

        # Eyes
        ox, oy = self._av_lookx * 5.0, self._av_looky * 4.0
        blink = 1.0
        if self._av_blink_t >= 0:
            bt = (now - self._av_blink_t) / 0.16
            blink = abs(1 - 2 * max(0.0, min(1.0, bt))) * 0.9 + 0.1
        for sgn in (-1, 1):
            ex = cx + sgn * 11.5 + ox
            ey = cy - 2.0 + oy
            ew, eh = 8.0, max(2.2, 15.0 * blink)
            if mood == "happy":
                d.arc([ex - 9, ey - 5, ex + 9, ey + 9], 200, 340, fill=(8, 11, 18, 255), width=4)
            else:
                d.rounded_rectangle([ex - ew / 2, ey - eh / 2, ex + ew / 2, ey + eh / 2],
                                    radius=ew / 2, fill=(8, 11, 18, 255))
                if blink > 0.6:
                    d.ellipse([ex - 3.2, ey - eh * 0.25 - 2.2, ex + 1.2, ey - eh * 0.25 + 2.2],
                              fill=(255, 255, 255, 245))
            # Rosy blush
            d.ellipse([cx + sgn * 19 + ox * 0.5 - 5, cy + 7 - 3,
                       cx + sgn * 19 + ox * 0.5 + 5, cy + 7 + 3],
                      fill=(255, 115, 165, 95))

        # Mouth
        mx, my = cx + ox * 0.6, cy + 12.5 + oy * 0.5
        if mood == "talk":
            mh = 3.0 + 8.0 * self._av_mouth
            d.rounded_rectangle([mx - 7, my - mh / 2, mx + 7, my + mh / 2],
                                radius=3.5, fill=(8, 11, 18, 255))
            if mh > 5.5:
                d.ellipse([mx - 4.5, my, mx + 4.5, my + mh / 2], fill=(244, 114, 182, 225))
        elif mood == "think":
            d.line([mx - 5, my, mx + 5, my - 2], fill=(8, 11, 18, 255), width=3)
        else:
            d.arc([mx - 7, my - 6, mx + 7, my + 4], 20, 160, fill=(8, 11, 18, 255), width=3)

        return im.resize((58, 58), Image.LANCZOS)

    def _animate_avatar(self):
        if not self.winfo_exists():
            return
        now = time.perf_counter()
        if self._av_blink_t < 0 and now >= self._av_blink_next:
            self._av_blink_t = now
        elif self._av_blink_t >= 0 and now - self._av_blink_t > 0.16:
            self._av_blink_t = -1.0
            self._av_blink_next = now + random.uniform(2.4, 5.2)

        if now >= self._av_look_next:
            if self._av_mood == "think":
                self._av_tx, self._av_ty = random.uniform(-0.8, 0.8), -0.7
            else:
                self._av_tx, self._av_ty = random.uniform(-0.7, 0.7), random.uniform(-0.4, 0.4)
            self._av_look_next = now + random.uniform(1.2, 2.8)

        self._av_lookx += (self._av_tx - self._av_lookx) * 0.18
        self._av_looky += (self._av_ty - self._av_looky) * 0.18

        if now < self._av_talking_until:
            self._av_mouth = 0.25 + 0.75 * abs(math.sin(now * 12.5))
        else:
            self._av_mouth *= 0.7

        try:
            if self.state() != "withdrawn":
                img = self._render_cartoon_avatar(now)
                self._av_photo = ImageTk.PhotoImage(img)
                self._avatar_cv.itemconfigure(self._avatar_item, image=self._av_photo)
        except Exception:
            pass

        delay = 40 if (self.state() != "withdrawn" and not self._reduced_motion) else 250
        self._av_job = self.after(delay, self._animate_avatar)

    def _render_empty_state(self):
        if self._empty_state is not None and self._empty_state.winfo_exists():
            self._empty_state.destroy()
        self._empty_state = ctk.CTkFrame(
            self._scroll, fg_color=TOKENS["surface"], corner_radius=20,
            border_width=1, border_color=TOKENS["border"],
        )
        self._empty_state.pack(fill="x", padx=18, pady=34)

        hr = time.localtime().tm_hour
        greeting = f"☀️ صباح النشاط{_to_user()}!" if 5 <= hr < 17 else f"🌙 مساء الروقان{_to_user()}!"
        ctk.CTkLabel(
            self._empty_state, text=greeting,
            font=(TOKENS["font_main"], 19, "bold"), text_color=TOKENS["text"],
        ).pack(pady=(24, 6))
        ctk.CTkLabel(
            self._empty_state,
            text="أنا صاحي وجاهز.. تقدر تقولي افتح أي لعبة، نظف الرامات،\nأو تسألني عن أي حاجة على الشاشة وهرد عليك فوراً.",
            font=(TOKENS["font_main"], 12), text_color=TOKENS["text_muted"], justify="center",
        ).pack(pady=(0, 24), padx=20)

    def _run_chip(self, cmd_text):
        self._entry.delete(0, "end")
        self._entry.insert(0, cmd_text)
        self._send()

    def _voice(self):
        if self._on_voice:
            self._av_mood = "listen"
            self.set_status("🎤 سامعك.. اتكلم دلوقتي", TOKENS["accent"])
            self._on_voice()

    def _show_toast(self, message: str):
        self._toast.configure(text=f"  {message}  ")
        self._toast.place(relx=0.5, rely=0.87, anchor="center")
        self.after(1800, lambda: self._toast.place_forget() if self.winfo_exists() else None)

    def _copy_text(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._show_toast("📋 تم نسخ النص إلى الحافظة")
        except Exception:
            pass

    def _speak_text(self, text: str):
        try:
            from tts_engine import speak
            self._av_talking_until = time.perf_counter() + min(4.0, max(1.2, len(text) * 0.05))
            threading.Thread(target=speak, args=(text,), daemon=True).start()
            self._show_toast("🔊 يوبي بيقرأ الرد...")
        except Exception:
            pass

    def _scroll_bottom(self):
        try:
            self._scroll._parent_canvas.update_idletasks()
            self._scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def clear_chat(self):
        self._messages.clear()
        for w in self._scroll.winfo_children():
            w.destroy()
        self._render_empty_state()
        self._scroll_bottom()

    def _add_bubble(self, role: str, text: str, ts: float, stream_anim: bool = False):
        if self._empty_state is not None and self._empty_state.winfo_exists():
            self._empty_state.destroy()
            self._empty_state = None

        is_user = (role == "user")
        row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        row.pack(fill="x", pady=6, padx=6)

        bg = TOKENS["user_bubble"] if is_user else TOKENS["bot_bubble"]
        border = TOKENS["user_border"] if is_user else TOKENS["bot_border"]

        card = ctk.CTkFrame(
            row, fg_color=bg, corner_radius=18,
            border_width=1, border_color=TOKENS["accent"] if (stream_anim and not is_user) else border,
        )
        card.pack(side="right" if is_user else "left", padx=(44, 2) if is_user else (2, 44))

        initial_text = "▍" if (stream_anim and not is_user and not self._reduced_motion) else text
        msg_lbl = ctk.CTkLabel(
            card, text=initial_text, font=(TOKENS["font_main"], 13),
            text_color=TOKENS["text"], wraplength=380,
            justify="right", anchor="e",
        )
        msg_lbl.pack(fill="x", padx=15, pady=(11, 4))

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=(0, 8))

        t_str = time.strftime("%I:%M %p", time.localtime(ts))
        who = "👤 أنت" if is_user else "✨ يوبي"
        meta_lbl = ctk.CTkLabel(
            footer, text=f"{who} • {t_str} • 📋 نسخ",
            font=(TOKENS["font_main"], 10), text_color=TOKENS["text_muted"],
            anchor="e" if is_user else "w", cursor="hand2",
        )
        meta_lbl.pack(side="right" if is_user else "left")

        if not is_user:
            spk_btn = ctk.CTkButton(
                footer, text="🔊", width=26, height=22, corner_radius=8,
                fg_color="transparent", hover_color=TOKENS["card_hover"],
                text_color=TOKENS["accent"], font=(TOKENS["font_main"], 11),
                command=lambda t=text: self._speak_text(t),
            )
            spk_btn.pack(side="right", padx=(4, 0))

        for widget in (card, msg_lbl, meta_lbl):
            widget.bind("<Button-1>", lambda e, t=text: self._copy_text(t))

        if stream_anim and not is_user and not self._reduced_motion and len(text) > 1:
            self._av_talking_until = time.perf_counter() + min(3.0, max(0.9, len(text) * 0.025))
            step_size = max(2, len(text) // 18)

            def _type_step(idx=step_size):
                if not msg_lbl.winfo_exists():
                    return
                if idx < len(text):
                    msg_lbl.configure(text=text[:idx] + " ▍")
                    self.after(22, lambda: _type_step(idx + step_size))
                else:
                    msg_lbl.configure(text=text)
                    card.configure(border_color=border)
                    self._scroll_bottom()

            self.after(18, _type_step)

        self.after(20, self._scroll_bottom)

    def _send(self):
        text = self._entry.get().strip()
        if not text:
            return
        self._entry.delete(0, "end")
        self.add_message("user", text)
        self._av_mood = "think"
        self.set_typing(True)
        self.set_status("🧠 يوبي بيفكر...", TOKENS["amber"])

        def _worker():
            try:
                reply = self._on_send(text) if self._on_send else f"استلمت: {text}"
            except Exception as exc:
                reply = f"⚠️ حصل خطأ: {exc}"
            self.after(30, lambda: (
                self.set_typing(False),
                setattr(self, "_av_mood", "idle"),
                self.set_status("● صاحي وجاهز يسمعك", TOKENS["emerald"]),
                self.add_message("assistant", reply, stream_anim=True),
            ))

        threading.Thread(target=_worker, daemon=True).start()

    def add_message(self, role: str, text: str, timestamp=None, stream_anim: bool = False):
        if not text:
            return
        ts = timestamp or time.time()
        self._messages.append({"role": role, "text": text, "timestamp": ts})
        self._add_bubble(role, text, ts, stream_anim=stream_anim)

    def set_typing(self, typing: bool):
        self._typing = bool(typing)
        if self._typing_job:
            try:
                self.after_cancel(self._typing_job)
            except Exception:
                pass
            self._typing_job = None
        if hasattr(self, "_typing_card") and self._typing_card.winfo_exists():
            self._typing_card.destroy()
        if self._typing:
            self._typing_card = ctk.CTkFrame(
                self._scroll, fg_color=TOKENS["card"], corner_radius=16,
                border_width=1, border_color=TOKENS["accent"],
            )
            self._typing_card.pack(anchor="w", padx=10, pady=6)
            self._typing_cv = tk.Canvas(
                self._typing_card, width=44, height=22, bg=TOKENS["card"],
                highlightthickness=0, bd=0,
            )
            self._typing_cv.pack(side="left", padx=(12, 4), pady=8)
            self._typing_lbl = ctk.CTkLabel(
                self._typing_card, text="يوبي بيكتب الرد...",
                font=(TOKENS["font_main"], 12, "bold"), text_color=TOKENS["accent"],
            )
            self._typing_lbl.pack(side="left", padx=(2, 14), pady=8)
            self._typing_step = 0
            if not self._reduced_motion:
                self._animate_typing()
            self.after(20, self._scroll_bottom)

    def _animate_typing(self):
        if not self._typing or not hasattr(self, "_typing_cv") or not self._typing_cv.winfo_exists():
            return
        self._typing_cv.delete("all")
        t = time.perf_counter() * 5.5
        cols = [TOKENS["accent"], "#60A5FA", TOKENS["violet"]]
        for i in range(3):
            dy = math.sin(t - i * 0.9) * 4.2
            cx = 10 + i * 12
            cy = 11 + dy
            r = 4.0
            self._typing_cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=cols[i], outline="")
        self._typing_step += 1
        self._typing_job = self.after(45, self._animate_typing)

    def set_status(self, text: str, color=None):
        if hasattr(self, "_status_lbl") and self._status_lbl.winfo_exists():
            self._status_lbl.configure(text=text, text_color=color or TOKENS["emerald"])

    def update_suggestions(self, suggestions):
        pass

    def show(self):
        self.deiconify()
        self.lift()
        self._fade_in()
        self._entry.focus_set()
        self.after(30, self._scroll_bottom)

    def hide(self):
        self.withdraw()

    def toggle(self):
        self.hide() if self.state() != "withdrawn" else self.show()

    def _export_chat(self):
        try:
            with open("yobi_chat_export.md", "w", encoding="utf-8") as f:
                for m in self._messages:
                    t_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(m.get("timestamp", time.time())))
                    f.write(f"### {m['role']} ({t_str})\n{m['text']}\n\n")
            self._show_toast("💾 اتحفظت المحادثة في yobi_chat_export.md")
        except Exception as e:
            messagebox.showerror("يوبي", f"فشل حفظ المحادثة: {e}")