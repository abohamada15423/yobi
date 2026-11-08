# -*- coding: utf-8 -*-
"""
Login Dialog v2 — Obsidian Bioluminescence modal for saving game credentials.
"""

import customtkinter as ctk

BG = "#080A0F"
CARD = "#121722"
BORDER = "#222B3D"
TEXT = "#F8FAFC"
MUTED = "#94A3B8"
ACCENT = "#38BDF8"
ACCENT_HOVER = "#0284C7"


class LoginDialog(ctk.CTkToplevel):
    """Modal dialog with masked username + password fields and show/hide toggle."""

    def __init__(self, launcher_name="riot", parent=None):
        super().__init__(parent)
        self.title("حفظ بيانات الدخول الآمنة 🔐")
        self.geometry("460x310")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=BG)

        self._result = None
        self._show_secret = False

        self.update_idletasks()
        w, h = 460, 310
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=18, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card, text=f"🔐 بيانات الدخول لـ {launcher_name}",
            font=("Segoe UI Semibold", 16), text_color=TEXT,
        ).pack(pady=(16, 2))

        ctk.CTkLabel(
            card, text="تُحفظ مشفرة داخل Windows Credential Manager فقط",
            font=("Segoe UI", 11), text_color=MUTED,
        ).pack(pady=(0, 12))

        ctk.CTkLabel(card, text="اسم المستخدم", anchor="e", font=("Segoe UI", 12), text_color=TEXT).pack(fill="x", padx=22)
        self._user_entry = ctk.CTkEntry(
            card, height=38, corner_radius=10, fg_color=BG, border_color=BORDER,
            text_color=TEXT, font=("Segoe UI", 12), show="•",
        )
        self._user_entry.pack(fill="x", padx=22, pady=(2, 8))

        ctk.CTkLabel(card, text="كلمة المرور", anchor="e", font=("Segoe UI", 12), text_color=TEXT).pack(fill="x", padx=22)
        self._pass_entry = ctk.CTkEntry(
            card, height=38, corner_radius=10, fg_color=BG, border_color=BORDER,
            text_color=TEXT, font=("Segoe UI", 12), show="•",
        )
        self._pass_entry.pack(fill="x", padx=22, pady=(2, 14))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=22, pady=(0, 12))

        ctk.CTkButton(
            btn_row, text="حفظ آمن ✅", height=38, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#061018",
            font=("Segoe UI", 12, "bold"), command=self._on_ok,
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="إلغاء", height=38, corner_radius=10,
            fg_color="transparent", border_width=1, border_color=BORDER,
            hover_color="#1E293B", text_color=MUTED, command=self._on_cancel,
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

        self._user_entry.focus_set()
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self._pass_entry.bind("<Return>", lambda e: self._on_ok())
        self.grab_set()

    def _on_ok(self):
        user = self._user_entry.get().strip()
        pwd = self._pass_entry.get()
        if not user or not pwd:
            return
        self._result = (user, pwd)
        self.destroy()

    def _on_cancel(self):
        self._result = None
        self.destroy()

    def get_result(self):
        return self._result


def show_login_dialog(launcher_name="riot", parent=None):
    dlg = LoginDialog(launcher_name=launcher_name, parent=parent)
    dlg.wait_window()
    return dlg.get_result()