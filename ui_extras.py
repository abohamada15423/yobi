# -*- coding: utf-8 -*-
"""
Yobi UI Extras v3 — Obsidian Sidebar Settings Window (with Live Cartoon Yobi & Disk Persistence)
& Animated Spotlight Command Palette v3.
"""

import difflib
import json
import math
import os
import random
import time
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw, ImageTk

import customtkinter as ctk

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_HERE, "config.json")

TOKENS = {
    "bg": "#07090E",
    "sidebar": "#0C1018",
    "surface": "#111622",
    "card": "#161D2B",
    "card_hover": "#1F293D",
    "border": "#232E44",
    "accent": "#38BDF8",
    "accent_hover": "#0284C7",
    "emerald": "#34D399",
    "amber": "#FBBF24",
    "violet": "#A78BFA",
    "danger": "#F87171",
    "text": "#F8FAFC",
    "text_muted": "#94A3B8",
    "font_main": "Segoe UI",
}

_TTS_BACKENDS = {
    "auto": "تلقائي — Edge، ولو النت وقع Piper",
    "edge": "Edge (أونلاين، صوت مصري)",
    "piper": "Piper (أوفلاين دايمًا)",
}

_STT_ENGINES = {
    "auto": "تلقائي (Groq Turbo ← GPU المحلي ← Groq v3)",
    "groq-turbo": "Groq Whisper Large-v3 Turbo (سريع)",
    "groq-v3": "Groq Whisper Large-v3 (أعلى دقة)",
    "local": "محلي على كارت الشاشة (Offline GPU)",
}

_VOICES = [
    "ar-EG-SalmaNeural   (مصري أنثى)",
    "ar-EG-ShakirNeural  (مصري ذكر)",
    "ar-SA-HamedNeural   (سعودي ذكر)",
    "ar-SA-ZariyahNeural (سعودي أنثى)",
]


def _load_json_config() -> dict:
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_json_config(patch_fn):
    try:
        data = _load_json_config()
        patch_fn(data)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ حفظ الإعدادات فشل: {e}")


class SettingsWindow(ctk.CTkToplevel):
    """Modern Obsidian Settings Window with Sidebar Navigation, Cartoon Yobi Mascot & Full Persistence."""

    NAV_ITEMS = [
        ("voice", "🎙️  الصوت والسمع"),
        ("companion", "💧  الرفيق والأوضاع"),
        ("behavior", "⚡  السلوك والثيم"),
        ("tasks", "🎯  المهام المتعلمة"),
        ("about", "✨  حول يوبي"),
    ]

    def __init__(self, master, island=None, agent=None):
        super().__init__(master)
        self._island = island or master
        self._agent = (
            agent
            or getattr(self._island, "_agent", None)
            or getattr(master, "_agent", None)
        )
        self._cfg_data = _load_json_config()

        self.title("إعدادات يوبي الشاملة")
        self.geometry("740x610")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=TOKENS["bg"])

        self._active_page = "voice"
        self._nav_btns = {}
        self._pages = {}
        self._mascot_photo = None
        self._blink_next = time.perf_counter() + 2.2
        self._blink_t = -1.0

        self._build_shell()
        self._select_page("voice")
        self._animate_mascot()
        self._fade_in()

    def _fade_in(self, step=0):
        if not self.winfo_exists():
            return
        try:
            if step == 0:
                self.attributes("-alpha", 0.0)
            t = (step + 1) / 6.0
            self.attributes("-alpha", min(1.0, t * t * (3 - 2 * t)))
            if step < 5:
                self.after(16, lambda: self._fade_in(step + 1))
        except Exception:
            pass

    def _show_toast(self, text: str):
        self._toast.configure(text=f"  {text}  ")
        self._toast.place(relx=0.38, rely=0.93, anchor="center")
        self.after(1600, lambda: self._toast.place_forget() if self.winfo_exists() else None)

    def _build_shell(self):
        # Right Sidebar (RTL layout)
        self._sidebar = ctk.CTkFrame(
            self, width=215, fg_color=TOKENS["sidebar"], corner_radius=0,
            border_width=1, border_color=TOKENS["border"],
        )
        self._sidebar.pack(side="right", fill="y")
        self._sidebar.pack_propagate(False)

        # Animated Cartoon Yobi Mascot in Sidebar
        self._mascot_cv = tk.Canvas(
            self._sidebar, width=76, height=76, bg=TOKENS["sidebar"],
            highlightthickness=0, bd=0,
        )
        self._mascot_cv.pack(pady=(20, 4))
        self._mascot_item = self._mascot_cv.create_image(0, 0, anchor="nw")

        ctk.CTkLabel(
            self._sidebar, text="إعدادات يوبي",
            font=(TOKENS["font_main"], 16, "bold"), text_color=TOKENS["text"],
        ).pack(pady=(0, 2))
        ctk.CTkLabel(
            self._sidebar, text="Yobi Control Center v8",
            font=(TOKENS["font_main"], 10), text_color=TOKENS["text_muted"],
        ).pack(pady=(0, 16))

        for key, label in self.NAV_ITEMS:
            btn = ctk.CTkButton(
                self._sidebar, text=label, height=42, corner_radius=12,
                anchor="e", font=(TOKENS["font_main"], 13, "bold"),
                fg_color="transparent", hover_color=TOKENS["card_hover"],
                text_color=TOKENS["text_muted"],
                command=lambda k=key: self._select_page(k),
            )
            btn.pack(fill="x", padx=14, pady=3)
            self._nav_btns[key] = btn

        # Main Content Container
        self._content = ctk.CTkFrame(self, fg_color=TOKENS["bg"], corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        self._toast = ctk.CTkLabel(
            self, text="", fg_color=TOKENS["accent_hover"], text_color="#FFFFFF",
            corner_radius=10, height=30, font=(TOKENS["font_main"], 11, "bold"),
        )

        self._pages["voice"] = self._build_voice_page()
        self._pages["companion"] = self._build_companion_page()
        self._pages["behavior"] = self._build_behavior_page()
        self._pages["tasks"] = self._build_tasks_page()
        self._pages["about"] = self._build_about_page()

    def _select_page(self, key: str):
        self._active_page = key
        for k, btn in self._nav_btns.items():
            active = (k == key)
            btn.configure(
                fg_color=TOKENS["card"] if active else "transparent",
                text_color=TOKENS["accent"] if active else TOKENS["text_muted"],
                border_width=1 if active else 0,
                border_color=TOKENS["accent"] if active else TOKENS["border"],
            )
        for k, frame in self._pages.items():
            if k == key:
                frame.pack(fill="both", expand=True, padx=20, pady=18)
            else:
                frame.pack_forget()

    def _render_mascot(self, now: float) -> Image.Image:
        W = 152
        im = Image.new("RGBA", (W, W), (12, 16, 24, 255))
        d = ImageDraw.Draw(im, "RGBA")
        cx, cy = W / 2, W / 2 + 6 + math.sin(now * 2.8) * 3.0
        r = 44.0
        acc = (56, 189, 248)
        deep = (12, 74, 110)
        light = (224, 242, 254)

        # Halo
        hr = r + 11 + math.sin(now * 3.2) * 2.5
        d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=acc + (32,), outline=acc + (105,), width=2)

        # Antenna
        sway = math.sin(now * 3.6) * 7.0
        d.line([cx, cy - r + 2, cx + sway, cy - r - 14], fill=acc + (240,), width=4)
        d.ellipse([cx + sway - 6, cy - r - 20, cx + sway + 6, cy - r - 8], fill=light + (255,))

        # Side pods
        for sgn in (-1, 1):
            ex_c = cx + sgn * (r * 0.96)
            d.rounded_rectangle([ex_c - 8, cy - 16, ex_c + 8, cy + 16],
                                radius=6, fill=deep + (255,), outline=acc + (225,), width=2)

        # Body
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=deep + (255,), outline=acc + (245,), width=3)
        d.ellipse([cx - r * 0.85, cy - r * 0.85, cx + r * 0.85, cy + r * 0.85], fill=acc + (215,))
        d.ellipse([cx - r * 0.5, cy - r * 0.62, cx - r * 0.06, cy - r * 0.32], fill=(255, 255, 255, 105))

        # Eyes
        blink = 1.0
        if self._blink_t >= 0:
            bt = (now - self._blink_t) / 0.16
            blink = abs(1 - 2 * max(0.0, min(1.0, bt))) * 0.9 + 0.1
        ox = math.sin(now * 1.4) * 5.0
        for sgn in (-1, 1):
            ex = cx + sgn * 15.0 + ox
            ey = cy - 2.0
            ew, eh = 10.0, max(3.0, 19.0 * blink)
            d.rounded_rectangle([ex - ew / 2, ey - eh / 2, ex + ew / 2, ey + eh / 2],
                                radius=ew / 2, fill=(8, 11, 18, 255))
            if blink > 0.6:
                d.ellipse([ex - 3.8, ey - eh * 0.24 - 2.6, ex + 1.4, ey - eh * 0.24 + 2.6],
                          fill=(255, 255, 255, 245))
            d.ellipse([cx + sgn * 24 + ox * 0.4 - 6, cy + 8 - 3.5,
                       cx + sgn * 24 + ox * 0.4 + 6, cy + 8 + 3.5],
                      fill=(255, 115, 165, 95))

        # Smile
        d.arc([cx - 9 + ox * 0.5, cy + 8, cx + 9 + ox * 0.5, cy + 20], 20, 160, fill=(8, 11, 18, 255), width=4)
        return im.resize((76, 76), Image.LANCZOS)

    def _animate_mascot(self):
        if not self.winfo_exists():
            return
        now = time.perf_counter()
        if self._blink_t < 0 and now >= self._blink_next:
            self._blink_t = now
        elif self._blink_t >= 0 and now - self._blink_t > 0.16:
            self._blink_t = -1.0
            self._blink_next = now + random.uniform(2.5, 5.0)
        try:
            img = self._render_mascot(now)
            self._mascot_photo = ImageTk.PhotoImage(img)
            self._mascot_cv.itemconfigure(self._mascot_item, image=self._mascot_photo)
        except Exception:
            pass
        self.after(50, self._animate_mascot)

    def _section_card(self, parent, title: str):
        card = ctk.CTkFrame(
            parent, fg_color=TOKENS["surface"], corner_radius=16,
            border_width=1, border_color=TOKENS["border"],
        )
        card.pack(fill="x", pady=6)
        ctk.CTkLabel(
            card, text=title, font=(TOKENS["font_main"], 13, "bold"),
            text_color=TOKENS["accent"], anchor="e",
        ).pack(fill="x", padx=16, pady=(12, 4))
        return card

    # --------------------------------------------------------------- voice
    def _build_voice_page(self):
        page = ctk.CTkFrame(self._content, fg_color="transparent")

        # Read live STT engine state
        cur_stt_key = self._cfg_data.get("hearing", {}).get("stt_engine") or self._cfg_data.get("stt", {}).get("engine", "auto")
        try:
            import agent
            if getattr(agent, "_STT", None) is not None and hasattr(agent._STT, "engine_mode"):
                cur_stt_key = agent._STT.engine_mode
        except Exception:
            pass
        cur_stt_label = _STT_ENGINES.get(cur_stt_key, _STT_ENGINES["auto"])

        c1 = self._section_card(page, "🎙️ محرك السمع وحساسية النداء (STT & Wake Word)")
        self._stt_var = tk.StringVar(value=cur_stt_label)
        ctk.CTkOptionMenu(
            c1, values=list(_STT_ENGINES.values()), variable=self._stt_var,
            command=self._on_stt_change, width=440, height=34,
            fg_color=TOKENS["card"], button_color=TOKENS["accent_hover"],
        ).pack(padx=16, pady=(4, 10))

        cur_thr = float(self._cfg_data.get("hearing", {}).get("wake_threshold", 0.45))
        if self._agent and getattr(self._agent, "recognizer", None) and self._agent.recognizer.wake:
            cur_thr = float(self._agent.recognizer.wake.threshold)

        thr_row = ctk.CTkFrame(c1, fg_color="transparent")
        thr_row.pack(fill="x", padx=16)
        ctk.CTkLabel(thr_row, text="حساسية كلمة النداء (أعلى = أدق وقت اللعب):", anchor="e").pack(side="right")
        self._wake_lbl = ctk.CTkLabel(thr_row, text=f"{cur_thr:.2f}", text_color=TOKENS["accent"],
                                      font=(TOKENS["font_main"], 12, "bold"))
        self._wake_lbl.pack(side="left")

        self._wake_slider = ctk.CTkSlider(
            c1, from_=0.25, to=0.80, number_of_steps=22,
            command=self._on_wake_thr_change, button_color=TOKENS["accent"],
            progress_color=TOKENS["accent_hover"],
        )
        self._wake_slider.set(cur_thr)
        self._wake_slider.pack(fill="x", padx=16, pady=(4, 14))

        # Read live TTS state
        cur_voice = "ar-EG-SalmaNeural"
        cur_rate_int = 10
        try:
            from tts_engine import get_tts_engine
            eng = get_tts_engine()
            cur_voice = getattr(eng, "voice", cur_voice) or cur_voice
            rate_str = str(getattr(eng, "rate", "+10%") or "+10%").replace("%", "").replace("+", "")
            cur_rate_int = int(rate_str)
        except Exception:
            pass
        matched_voice = next((v for v in _VOICES if v.startswith(cur_voice)), _VOICES[0])

        c2 = self._section_card(page, "🔊 صوت التحدث وسرعة النطق (TTS Engine)")
        self._voice_var = tk.StringVar(value=matched_voice)
        ctk.CTkOptionMenu(
            c2, values=_VOICES, variable=self._voice_var,
            command=self._on_voice_change, width=440, height=34,
            fg_color=TOKENS["card"], button_color=TOKENS["accent_hover"],
        ).pack(padx=16, pady=(4, 10))

        rate_row = ctk.CTkFrame(c2, fg_color="transparent")
        rate_row.pack(fill="x", padx=16)
        ctk.CTkLabel(rate_row, text="سرعة الكلام:", anchor="e").pack(side="right")
        sign = "+" if cur_rate_int >= 0 else ""
        self._rate_label = ctk.CTkLabel(rate_row, text=f"{sign}{cur_rate_int}%", text_color=TOKENS["emerald"],
                                        font=(TOKENS["font_main"], 12, "bold"))
        self._rate_label.pack(side="left")

        self._rate_slider = ctk.CTkSlider(
            c2, from_=-30, to=50, number_of_steps=16,
            command=self._on_rate_change, button_color=TOKENS["emerald"],
            progress_color=TOKENS["emerald"],
        )
        self._rate_slider.set(cur_rate_int)
        self._rate_slider.pack(fill="x", padx=16, pady=(4, 10))

        row = ctk.CTkFrame(c2, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(2, 14))
        ctk.CTkButton(
            row, text="🔊 تجربة الصوت", command=self._test_voice, width=150, height=36,
            corner_radius=10, fg_color=TOKENS["accent"], hover_color=TOKENS["accent_hover"],
            text_color="#061018", font=(TOKENS["font_main"], 12, "bold"),
        ).pack(side="left", padx=(0, 10))

        self._backend_var = tk.StringVar(value=self._backend_label())
        ctk.CTkOptionMenu(
            row, values=list(_TTS_BACKENDS.values()), variable=self._backend_var,
            command=self._on_backend_change, width=280, height=36,
            fg_color=TOKENS["card"], button_color=TOKENS["accent_hover"],
        ).pack(side="left")

        return page

    def _on_stt_change(self, label):
        key = next((k for k, v in _STT_ENGINES.items() if v == label), "auto")
        try:
            import agent
            if getattr(agent, "_STT", None) is not None:
                agent._STT.set_engine(key)
        except Exception:
            pass
        _save_json_config(lambda d: d.setdefault("hearing", {}).__setitem__("stt_engine", key))
        self._show_toast("🎙️ تم حفظ محرك السمع")

    def _on_wake_thr_change(self, val):
        v = round(float(val), 2)
        self._wake_lbl.configure(text=f"{v:.2f}")
        try:
            if self._agent and getattr(self._agent, "recognizer", None) and self._agent.recognizer.wake:
                self._agent.recognizer.wake.set_threshold(v)
        except Exception:
            pass
        _save_json_config(lambda d: d.setdefault("hearing", {}).__setitem__("wake_threshold", v))

    def _backend_label(self):
        try:
            from tts_engine import get_tts_engine
            return _TTS_BACKENDS.get(get_tts_engine().backend, _TTS_BACKENDS["auto"])
        except Exception:
            return _TTS_BACKENDS["auto"]

    def _on_backend_change(self, label):
        key = next((k for k, v in _TTS_BACKENDS.items() if v == label), "auto")
        try:
            from tts_engine import get_tts_engine
            get_tts_engine().set_backend(key)
            self._show_toast("🔊 تم تحديث محرك النطق")
        except Exception as e:
            print(f"⚠️ تغيير محرك الصوت فشل: {e}")

    def _on_voice_change(self, choice):
        voice_id = choice.split()[0]
        try:
            from tts_engine import get_tts_engine
            get_tts_engine().set_voice(voice_id)
        except Exception:
            pass
        _save_json_config(lambda d: d.setdefault("tts", {}).__setitem__("voice", voice_id))
        self._show_toast("🗣️ تم تغيير صوت يوبي")

    def _on_rate_change(self, val):
        pct = int(round(val))
        sign = "+" if pct >= 0 else ""
        rate_str = f"{sign}{pct}%"
        self._rate_label.configure(text=rate_str)
        try:
            from tts_engine import get_tts_engine
            get_tts_engine().set_rate(rate_str)
        except Exception:
            pass
        _save_json_config(lambda d: d.setdefault("tts", {}).__setitem__("rate", rate_str))

    def _test_voice(self):
        try:
            from tts_engine import speak
            name = str(self._cfg_data.get("user_name") or "").strip()
            speak(f"أهلاً بيك{(' يا ' + name) if name else ''}! أنا يوبي، مساعدك الذكي بالشكل الجديد.")
        except Exception:
            pass

    # --------------------------------------------------- companion & modes
    def _build_companion_page(self):
        page = ctk.CTkFrame(self._content, fg_color="transparent")

        c1 = self._section_card(page, "💧 متابعة شرب المياه واللياقة اليومية")
        self._water_lbl = ctk.CTkLabel(
            c1, text=self._get_water_status(), anchor="e",
            text_color=TOKENS["accent"], font=(TOKENS["font_main"], 13, "bold"),
        )
        self._water_lbl.pack(fill="x", padx=16, pady=(2, 8))

        self._water_bar = ctk.CTkProgressBar(
            c1, height=12, corner_radius=6,
            fg_color=TOKENS["card"], progress_color=TOKENS["accent"],
        )
        self._water_bar.pack(fill="x", padx=16, pady=(0, 12))
        self._water_bar.set(min(1.0, self._get_water_cups() / 8.0))

        w_row = ctk.CTkFrame(c1, fg_color="transparent")
        w_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(
            w_row, text="💧 سجّل كوباية مياه (+1)", width=210, height=38, corner_radius=11,
            fg_color=TOKENS["accent"], hover_color=TOKENS["accent_hover"],
            text_color="#061018", font=(TOKENS["font_main"], 12, "bold"),
            command=self._log_water_cup,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            w_row, text="💪 النهارده راحة من الجيم", width=190, height=38, corner_radius=11,
            fg_color=TOKENS["card"], hover_color=TOKENS["card_hover"],
            command=self._set_gym_rest,
        ).pack(side="right")

        c2 = self._section_card(page, "🎯 تفعيل الأوضاع الذكية (Smart Macros)")
        m_row = ctk.CTkFrame(c2, fg_color="transparent")
        m_row.pack(fill="x", padx=16, pady=(6, 14))
        for label, mode in [
            ("💻 مود المذاكرة", "study"),
            ("🎮 مود الجيمينج", "gaming"),
            ("🍿 مود السينما", "cinema"),
        ]:
            ctk.CTkButton(
                m_row, text=label, width=142, height=40, corner_radius=12,
                fg_color=TOKENS["card"], hover_color=TOKENS["accent_hover"],
                border_width=1, border_color=TOKENS["border"],
                font=(TOKENS["font_main"], 12, "bold"),
                command=lambda m=mode: self._trigger_mode(m),
            ).pack(side="right", padx=4)

        c3 = self._section_card(page, "🚀 تسريع الجهاز وتفريغ الرامات")
        ctk.CTkButton(
            c3, text="🚀 تنظيف وتفريغ الرامات الآن", width=250, height=40, corner_radius=12,
            fg_color="#10B981", hover_color="#059669", text_color="#04130D",
            font=(TOKENS["font_main"], 13, "bold"),
            command=self._free_ram_now,
        ).pack(anchor="e", padx=16, pady=(4, 14))

        return page

    def _get_water_cups(self) -> int:
        try:
            p = os.path.join(_HERE, "companion_data.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return int(d.get("water_cups", 0))
        except Exception:
            pass
        return 0

    def _get_water_status(self):
        cups = self._get_water_cups()
        return f"شربت النهارده: {cups} من 8 كوبايات مياه 💧"

    def _log_water_cup(self):
        if self._island is not None and hasattr(self._island, "_fire_quick_action"):
            self._island._fire_quick_action("water")
            self.after(220, lambda: (
                self._water_lbl.configure(text=self._get_water_status()),
                self._water_bar.set(min(1.0, self._get_water_cups() / 8.0)),
                self._show_toast("💧 بالهنا والشفا! اتسجلت كوباية مياه"),
            ))

    def _set_gym_rest(self):
        if self._island is not None and hasattr(self._island, "_on_chat_send"):
            res = self._island._on_chat_send("النهاردة راحة من الجيم")
            if res:
                self._island.say(str(res), state="info")
                self._show_toast("💪 تم تسجيل راحة من الجيم النهارده")

    def _trigger_mode(self, mode):
        try:
            from device_control import activate_smart_mode
            msg = activate_smart_mode(mode)
            if self._island is not None:
                self._island.set_state("success", msg)
            self._show_toast(f"🎯 {msg}")
        except Exception as e:
            messagebox.showerror("يوبي", str(e))

    def _free_ram_now(self):
        try:
            from device_control import handle_free_ram
            msg = handle_free_ram()
            if self._island is not None:
                self._island.set_state("success", msg)
            self._show_toast("🚀 تم تفريغ الرامات بنجاح")
        except Exception as e:
            messagebox.showerror("يوبي", str(e))

    # ------------------------------------------------------------- behavior
    def _build_behavior_page(self):
        page = ctk.CTkFrame(self._content, fg_color="transparent")
        c1 = self._section_card(page, "⚡ التحكم في استجابة وسلوك يوبي")

        listen_init = True
        if self._agent is not None and hasattr(self._agent, "listening_enabled"):
            listen_init = bool(self._agent.listening_enabled.is_set())
        self._wake_enabled = tk.BooleanVar(value=listen_init)
        ctk.CTkCheckBox(
            c1, text="تفعيل الاستماع المستمر وكلمة النداء (Wake Word)",
            variable=self._wake_enabled, command=self._on_toggle_wake,
            fg_color=TOKENS["accent"],
        ).pack(anchor="w", padx=16, pady=(10, 8))

        voice_init = bool(self._cfg_data.get("replies", {}).get("voice", False))
        if self._agent is not None and hasattr(self._agent, "get_voice_reply"):
            voice_init = bool(self._agent.get_voice_reply())
        self._tts_enabled = tk.BooleanVar(value=voice_init)
        ctk.CTkCheckBox(
            c1, text="تشغيل الرد الصوتي (TTS) بجانب الكتابة على الجزيرة",
            variable=self._tts_enabled, command=self._on_toggle_tts,
            fg_color=TOKENS["accent"],
        ).pack(anchor="w", padx=16, pady=8)

        comp_init = True
        if self._island is not None and getattr(self._island, "_companion_get", None):
            try:
                comp_init = bool(self._island._companion_get())
            except Exception:
                comp_init = True
        self._suggestions_enabled = tk.BooleanVar(value=comp_init)
        ctk.CTkCheckBox(
            c1, text="أسئلة يوبي الذكية (المياه، الجيم، المزاج، السهر)",
            variable=self._suggestions_enabled, command=self._on_toggle_companion,
            fg_color=TOKENS["accent"],
        ).pack(anchor="w", padx=16, pady=(8, 14))

        c2 = self._section_card(page, "🎨 المظهر والثيم (Appearance)")
        theme_init = getattr(self._island, "_theme_pref", "auto") if self._island else "auto"
        self._theme_var = tk.StringVar(value=theme_init)
        ctk.CTkOptionMenu(
            c2, values=["dark", "light", "auto"],
            variable=self._theme_var, command=self._on_theme_change,
            width=220, height=36, fg_color=TOKENS["card"], button_color=TOKENS["accent_hover"],
        ).pack(anchor="e", padx=16, pady=(6, 14))

        return page

    def _on_toggle_wake(self):
        if self._agent is not None and hasattr(self._agent, "toggle_listen"):
            state = self._agent.toggle_listen()
            self._wake_enabled.set(bool(state))
            self._show_toast("🎤 تم تحديث حالة الاستماع")

    def _on_toggle_tts(self):
        if self._agent is not None and hasattr(self._agent, "toggle_voice_reply"):
            state = self._agent.toggle_voice_reply()
            self._tts_enabled.set(bool(state))
        _save_json_config(lambda d: d.setdefault("replies", {}).__setitem__("voice", bool(self._tts_enabled.get())))
        self._show_toast("🔊 تم تحديث الرد الصوتي")

    def _on_toggle_companion(self):
        if self._island is not None and hasattr(self._island, "_toggle_companion"):
            self._island._toggle_companion()
            self._show_toast("💬 تم تحديث أسئلة الرفيق")

    def _on_theme_change(self, choice):
        if self._island is not None:
            self._island.set_theme(choice)
            self._show_toast(f"🎨 تم تطبيق الثيم: {choice}")

    # ---------------------------------------------------------------- tasks
    def _build_tasks_page(self):
        page = ctk.CTkFrame(self._content, fg_color="transparent")
        c1 = self._section_card(page, "🎯 المهام البصرية المتعلمة (Vision Tasks)")

        self._tasks_scroll = ctk.CTkScrollableFrame(
            c1, height=340, fg_color=TOKENS["bg"], corner_radius=12,
        )
        self._tasks_scroll.pack(fill="both", expand=True, padx=14, pady=(4, 10))
        self._refresh_tasks_list()

        row = ctk.CTkFrame(c1, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(2, 12))
        ctk.CTkButton(
            row, text="🔄 إعادة فحص ألعاب وبرامج الجهاز",
            command=self._refresh_device, width=220, height=38, corner_radius=10,
            fg_color=TOKENS["accent"], hover_color=TOKENS["accent_hover"],
            text_color="#061018", font=(TOKENS["font_main"], 12, "bold"),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            row, text="🗑️ مسح الكل",
            command=self._clear_all_tasks, width=120, height=38, corner_radius=10,
            fg_color=TOKENS["card"], hover_color="#451A24",
            border_width=1, border_color=TOKENS["border"],
        ).pack(side="right")

        return page

    def _refresh_tasks_list(self):
        for w in self._tasks_scroll.winfo_children():
            w.destroy()
        try:
            from vision_agent import load_tasks
            tasks = load_tasks()
        except Exception:
            tasks = {}
        if not tasks:
            ctk.CTkLabel(
                self._tasks_scroll, text="✨ مفيش مهام بصرية متعلمة لسه",
                text_color=TOKENS["text_muted"], font=(TOKENS["font_main"], 12),
            ).pack(pady=35)
            return
        for name, data in tasks.items():
            card = ctk.CTkFrame(
                self._tasks_scroll, fg_color=TOKENS["card"], corner_radius=12,
                border_width=1, border_color=TOKENS["border"],
            )
            card.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(
                card, text=f"🎯 {name}",
                font=(TOKENS["font_main"], 12, "bold"), text_color=TOKENS["accent"], anchor="w",
            ).pack(fill="x", padx=12, pady=(8, 2))
            ctk.CTkLabel(
                card, text=(data.get("description") or "")[:140],
                font=(TOKENS["font_main"], 11), anchor="w",
                text_color=TOKENS["text_muted"], wraplength=420, justify="left",
            ).pack(fill="x", padx=12, pady=(0, 8))

    def _refresh_device(self):
        if self._agent is None:
            messagebox.showinfo("يوبي", "لازم يوبي يكون شغال عشان تفحص الجهاز.")
            return
        try:
            if hasattr(self._agent, "refresh_apps"):
                self._agent.refresh_apps()
            messagebox.showinfo(
                "يوبي",
                f"تم الفحص! لقيت {len(self._agent.games)} لعبة و "
                f"{len(self._agent.installed_apps)} برنامج.",
            )
        except Exception as e:
            messagebox.showerror("يوبي", f"فشل الفحص: {e}")

    def _clear_all_tasks(self):
        if not messagebox.askyesno("يوبي", "متأكد؟ هيتم مسح كل المهام المتعلمة."):
            return
        try:
            from vision_agent import save_tasks
            save_tasks({})
            self._refresh_tasks_list()
            self._show_toast("🗑️ تم مسح المهام المتعلمة")
        except Exception as e:
            messagebox.showerror("يوبي", str(e))

    # ---------------------------------------------------------------- about
    def _build_about_page(self):
        page = ctk.CTkFrame(self._content, fg_color="transparent")
        card = self._section_card(page, "✨ عن يوبي — Yobi AI Assistant")
        ctk.CTkLabel(
            card, text="يوبي v8.0 Pro — مساعدك الذكي بالعامية المصرية",
            font=(TOKENS["font_main"], 16, "bold"), text_color=TOKENS["text"],
        ).pack(pady=(16, 6))
        ctk.CTkLabel(
            card,
            text="Dynamic Island v8 (Evolved Cartoon Edition)  •  Groq Whisper + LLM\n"
                 "faster-whisper  •  openWakeWord  •  WebRTC AEC3  •  Pillow 2x HUD\n\n"
                 "• كليك شمال على الجزيرة: الأوامر السريعة بأنيميشن متدرج (8 أزرار)\n"
                 "• دبل كليك: نافذة المحادثة الذكية مع أفاتار يوبي الكرتوني الحي\n"
                 "• كليك بالبكرة (Middle-Click): شريط كتابة أمر سريع مباشر\n"
                 "• تحريك البكرة (Scroll): تعلية وتوطية الصوت لايف\n"
                 "• كليك يمين: القائمة الكاملة والأوضاع الذكية واستعراض الحالات",
            font=(TOKENS["font_main"], 12), text_color=TOKENS["text_muted"],
            justify="center",
        ).pack(padx=20, pady=(4, 24))
        return page


# ---------------------------------------------------------------------------
# Command Palette v3 (Spotlight Animated Launcher)
# ---------------------------------------------------------------------------
class CommandPalette(ctk.CTkToplevel):
    """Animated Spotlight-style quick-launch palette with category filter pills & phonetic search."""

    CATEGORIES = [
        ("all", "✨ الكل"),
        ("game", "🎮 ألعاب"),
        ("app", "⚡ برامج"),
        ("site", "🌐 مواقع"),
    ]

    def __init__(self, master, island=None, agent=None, known_targets=None):
        super().__init__(master)
        self._island = island or master
        self._agent = (
            agent
            or getattr(self._island, "_agent", None)
            or getattr(master, "_agent", None)
        )
        self._targets = known_targets or []
        self._kind_map = {}
        self._cat_filter = "all"
        self._cat_btns = {}

        self.title("لوحة الأوامر السريعة ⌘")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 580, 480
        self._x = max(0, (sw - w) // 2)
        self._target_y = max(40, int(sh * 0.16))
        self.geometry(f"{w}x{h}+{self._x}+{max(0, self._target_y - 18)}")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(fg_color=TOKENS["bg"])

        if self._agent is not None and hasattr(self._agent, "catalog"):
            for e in self._agent.catalog.entries:
                if not str(e.display).startswith("__"):
                    self._kind_map[e.display] = e.kind
            self._targets = self._agent.catalog.display_names(limit=260)
        elif self._agent is not None:
            for k in self._agent.games:
                self._kind_map[k] = "game"
            for k in self._agent.local_apps:
                self._kind_map[k] = "app"
            for k in self._agent.installed_apps:
                self._kind_map[k] = "installed"
            for k in self._agent.websites:
                self._kind_map[k] = "site"
            self._targets = (
                list(self._agent.websites.keys())
                + list(self._agent.local_apps.keys())
                + list(self._agent.installed_apps.keys())
                + list(self._agent.games.keys())
            )
        self._all_items = sorted({str(t) for t in self._targets if t and not str(t).startswith("__")})

        # Search input card
        top = ctk.CTkFrame(
            self, fg_color=TOKENS["surface"], corner_radius=16,
            border_width=1, border_color=TOKENS["accent"],
        )
        top.pack(fill="x", padx=16, pady=(16, 8))

        self._entry = ctk.CTkEntry(
            top, placeholder_text="🔍 اكتب اسم لعبة، برنامج، أو موقع (عربي أو إنجليزي)...",
            height=46, corner_radius=14, fg_color="transparent", border_width=0,
            text_color=TOKENS["text"], placeholder_text_color=TOKENS["text_muted"],
            font=(TOKENS["font_main"], 14), justify="right",
        )
        self._entry.pack(fill="x", padx=12, pady=2)
        self._entry.bind("<KeyRelease>", self._on_key)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Down>", self._on_down)
        self._entry.bind("<Up>", self._on_up)
        self._entry.bind("<Escape>", lambda e: self.destroy())
        self._entry.focus_set()

        # Category Filter Pills
        cats_row = ctk.CTkFrame(self, fg_color="transparent")
        cats_row.pack(fill="x", padx=16, pady=(0, 6))
        for cid, clabel in self.CATEGORIES:
            b = ctk.CTkButton(
                cats_row, text=clabel, width=90, height=30, corner_radius=15,
                font=(TOKENS["font_main"], 11, "bold"),
                command=lambda c=cid: self._set_category(c),
            )
            b.pack(side="right", padx=3)
            self._cat_btns[cid] = b

        self._list_frame = ctk.CTkScrollableFrame(
            self, height=310, fg_color=TOKENS["surface"], corner_radius=16,
            border_width=1, border_color=TOKENS["border"],
        )
        self._list_frame.pack(fill="both", expand=True, padx=16, pady=(2, 8))

        footer = ctk.CTkLabel(
            self, text="↵ للتشغيل الفوري   •   ↑↓ للتنقل   •   Esc للإغلاق",
            font=(TOKENS["font_main"], 10), text_color=TOKENS["text_muted"],
        )
        footer.pack(pady=(0, 8))

        self._index = 0
        self._results = []
        self._update_cat_buttons()
        self._filter_items()
        self._animate_open()

    def _animate_open(self, step=0):
        if not self.winfo_exists():
            return
        try:
            if step == 0:
                self.attributes("-alpha", 0.0)
            t = (step + 1) / 6.0
            s = t * t * (3 - 2 * t)
            cy = int(max(0, self._target_y - 18) + 18 * s)
            self.geometry(f"580x480+{self._x}+{cy}")
            self.attributes("-alpha", min(1.0, s))
            if step < 5:
                self.after(15, lambda: self._animate_open(step + 1))
        except Exception:
            pass

    def _set_category(self, cid: str):
        self._cat_filter = cid
        self._update_cat_buttons()
        self._filter_items()

    def _update_cat_buttons(self):
        for cid, btn in self._cat_btns.items():
            on = (cid == self._cat_filter)
            btn.configure(
                fg_color=TOKENS["accent"] if on else TOKENS["card"],
                text_color="#061018" if on else TOKENS["text_muted"],
                hover_color=TOKENS["accent_hover"] if on else TOKENS["card_hover"],
            )

    def _badge(self, item):
        k = self._kind_map.get(item, "")
        return {
            "game": ("🎮", "لعبة"),
            "app": ("⚡", "برنامج"),
            "installed": ("💻", "مثبت"),
            "site": ("🌐", "موقع"),
        }.get(k, ("🚀", "تشغيل"))

    def _matches_cat(self, item: str) -> bool:
        if self._cat_filter == "all":
            return True
        k = self._kind_map.get(item, "")
        if self._cat_filter == "app":
            return k in ("app", "installed")
        return k == self._cat_filter

    def _render(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        if not self._results:
            ctk.CTkLabel(
                self._list_frame, text="🔍 مفيش نتائج مطابقة للبحث",
                text_color=TOKENS["text_muted"], font=(TOKENS["font_main"], 13),
            ).pack(pady=40)
            return
        for i, item in enumerate(self._results):
            selected = (i == self._index)
            icon, kind_lbl = self._badge(item)
            btn = ctk.CTkButton(
                self._list_frame,
                text=f"{icon}   {item}   ({kind_lbl})",
                anchor="w", height=38, corner_radius=10,
                fg_color=(TOKENS["accent_hover"] if selected else "transparent"),
                hover_color=TOKENS["card_hover"],
                border_width=1 if selected else 0,
                border_color=TOKENS["accent"] if selected else TOKENS["border"],
                text_color=("#FFFFFF" if selected else TOKENS["text"]),
                font=(TOKENS["font_main"], 12, "bold" if selected else "normal"),
                command=lambda x=item: self._launch(x),
            )
            btn.pack(fill="x", pady=2, padx=4)

    def _filter_items(self):
        q = self._entry.get().lower().strip()
        pool = [t for t in self._all_items if self._matches_cat(t)]
        if not q:
            self._results = pool[:30]
        else:
            subs = [t for t in pool if q in t.lower()]
            if self._agent is not None and hasattr(self._agent, "catalog"):
                ranked = self._agent.catalog.rank(q, top=25)
                for e, sc in ranked:
                    if sc >= 0.58 and e.display not in subs and self._matches_cat(e.display):
                        subs.append(e.display)
            if not subs:
                subs = difflib.get_close_matches(q, pool, n=30, cutoff=0.48)
            self._results = subs[:30]
        self._index = 0
        self._render()

    def _on_key(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape"):
            return
        self._filter_items()

    def _on_down(self, event):
        if self._results:
            self._index = (self._index + 1) % len(self._results)
            self._render()

    def _on_up(self, event):
        if self._results:
            self._index = (self._index - 1) % len(self._results)
            self._render()

    def _on_enter(self, event):
        if self._results:
            self._launch(self._results[self._index])

    def _launch(self, item):
        if self._agent is not None:
            try:
                res = self._agent.open_target(item)
                if self._island is not None:
                    self._island.set_state("success", res)
            except Exception as e:
                print(f"⚠️ launch failed: {e}")
        self.destroy()