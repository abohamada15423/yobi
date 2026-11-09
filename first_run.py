# -*- coding: utf-8 -*-
"""First run on a new PC: ask for the API keys Yobi needs and save them to .env.

Gemini (required, free from aistudio.google.com) is Yobi's brain and can also hear;
Groq (optional, free from console.groq.com) makes hearing faster. Both keys are
checked online before saving, and they stay in .env on this PC only.

    from first_run import ask_keys
    ask_keys(env_path)                 # → (gemini, groq) or None if the window was closed
"""
import json
import os
import re
import threading
import urllib.error
import urllib.request
import webbrowser

GEMINI_URL = "https://aistudio.google.com/apikey"
GROQ_URL = "https://console.groq.com/keys"

BG, CARD, INK, INK2, ACCENT, BAD = "#0c0c0f", "#17171c", "#f2f2f5", "#a3a3ad", "#3CC2B4", "#ff6b6b"


def ar(text):
    """Tk doesn't join Arabic letters by itself."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def read_env(path):
    keys = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    keys[k.strip().upper()] = v.strip().strip('"').strip("'")
    return keys


NO_KEY = "YOBI_NO_KEY"      # "continue without a key": commands only, and don't ask again


def write_env(path, gemini, groq):
    """Keep any other lines; replace only the two keys. No Gemini key = the no-key choice."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip("\n") for l in f
                     if l.split("=", 1)[0].strip().upper() not in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", NO_KEY)
                     and not l.strip().startswith(("AIza", "gsk_"))]
    lines.append(f"GEMINI_API_KEY={gemini}" if gemini else f"{NO_KEY}=1")
    if groq:
        lines.append(f"GROQ_API_KEY={groq}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(l for l in lines if l.strip()) + "\n")


def looks_like(kind, key):
    """Only catches obvious slips (spaces, half a key, the other service's key): Google has more
    than one key format (AIza…, AQ.…), so the online check is the real test."""
    if not re.fullmatch(r"[0-9A-Za-z_.\-]{30,200}", key or ""):
        return False
    return not key.startswith("gsk_") if kind == "gemini" else not key.startswith("AIza")


def check_online(kind, key, timeout=8):
    """'ok', 'bad' (the service refused the key) or 'offline' (couldn't ask)."""
    if kind == "gemini":
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                                     headers={"x-goog-api-key": key})
    else:
        req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                                     headers={"Authorization": f"Bearer {key}", "User-Agent": "Yobi"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.loads(r.read() or b"{}")
            return "ok"
    except urllib.error.HTTPError as e:
        return "bad" if e.code in (400, 401, 403) else "offline"
    except Exception:
        return "offline"


def ask_keys(env_path, force=False):
    """Show the window when there is no Gemini key (or always with force). Returns the saved
    (gemini, groq), the existing ones when nothing was needed, or None if the user closed it."""
    have = read_env(env_path)
    gemini = have.get("GEMINI_API_KEY") or have.get("GOOGLE_API_KEY") or ""
    groq = have.get("GROQ_API_KEY", "")
    if gemini.startswith("gsk_") and not groq:
        gemini, groq = "", gemini
    if groq.startswith("AIza") and not gemini:
        gemini, groq = groq, ""
    if (gemini or have.get(NO_KEY)) and not force:
        return gemini, groq

    import tkinter as tk
    result = {}
    root = tk.Tk()
    root.title("Yobi")
    root.configure(bg=BG)
    root.resizable(False, False)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        root.iconbitmap(os.path.join(here, "yobi.ico"))
    except Exception:
        pass
    font = ("Segoe UI", 11)
    pad = dict(padx=24)

    def label(text, size=11, color=INK, bold=False, top=0):
        w = tk.Label(root, text=ar(text), bg=BG, fg=color, font=("Segoe UI", size, "bold" if bold else "normal"),
                     justify="right", anchor="e", wraplength=0)
        w.pack(fill="x", pady=(top, 0), **pad)
        return w

    def field(value):
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", pady=(6, 0), **pad)
        var = tk.StringVar(value=value)
        e = tk.Entry(row, textvariable=var, font=("Consolas", 11), bg=CARD, fg=INK, insertbackground=INK,
                     relief="flat", show="•", width=42)
        e.pack(side="right", ipady=7, fill="x", expand=True)

        def paste():
            try:
                var.set(root.clipboard_get().strip())
            except tk.TclError:
                pass
        tk.Button(row, text=ar("لصق"), command=paste, font=font, bg="#26262e", fg=INK, relief="flat",
                  activebackground="#33333d", activeforeground=INK, padx=12, cursor="hand2").pack(side="left", padx=(0, 8))
        # Ctrl+V with an Arabic keyboard layout doesn't reach Tk's paste: catch it by key code
        e.bind("<Control-KeyPress>", lambda ev: (paste(), "break")[1] if ev.keycode == 86 else None)
        return var, e

    def link(text, url):
        w = tk.Label(root, text=ar(text), bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"), cursor="hand2", anchor="e")
        w.pack(fill="x", pady=(4, 0), **pad)
        w.bind("<Button-1>", lambda _e: webbrowser.open(url))

    label("أهلاً بيك في يوبي", 17, bold=True, top=22)
    label("يوبي محتاج مفتاح Gemini مجاني عشان يفكر ويفهم كلامك.", 10, INK2, top=6)
    label("المفتاح بيتحفظ على جهازك بس.", 10, INK2)
    label("من غير مفتاح: يوبي بينفذ الأوامر بس (افتح، اقفل، الصوت…) من غير دردشة.", 10, INK2)

    label("مفتاح Gemini (للدردشة والسمع الأدق)", 11, bold=True, top=18)
    g_var, g_entry = field(gemini)
    link("هات مفتاح مجاني من هنا", GEMINI_URL)
    label("في الصفحة دوس Create API key وانسخ المفتاح", 9, INK2)

    label("مفتاح Groq (اختياري: بيخلي يوبي يسمع أسرع)", 11, bold=True, top=16)
    q_var, _ = field(groq)
    link("هات مفتاح Groq مجاني من هنا", GROQ_URL)

    status = label("", 10, INK2, top=14)
    buttons = tk.Frame(root, bg=BG)
    buttons.pack(fill="x", pady=(10, 22), **pad)

    def say(text, color=INK2):
        status.configure(text=ar(text), fg=color)

    def done():
        g, q = g_var.get().strip(), q_var.get().strip()
        if not looks_like("gemini", g):
            say("مفتاح Gemini شكله مش مظبوط. انسخه كله من غير مسافات.", BAD)
            g_entry.focus_set()
            return
        if q and not looks_like("groq", q):
            say("مفتاح Groq شكله مش مظبوط: بيبدأ بـ gsk_ (أو سيبه فاضي).", BAD)
            return
        go.configure(state="disabled")
        say("بتأكد من المفاتيح…")

        def work():
            gr = check_online("gemini", g)
            qr = check_online("groq", q) if q else "ok"
            root.after(0, lambda: finish(g, q, gr, qr))
        threading.Thread(target=work, daemon=True).start()

    def finish(g, q, gr, qr):
        go.configure(state="normal")
        if gr == "bad":
            say("Google رفض مفتاح Gemini ده. اتأكد إنك نسخته كله.", BAD)
            return
        if qr == "bad":
            say("Groq رفض المفتاح ده. صلّحه أو سيبه فاضي.", BAD)
            return
        write_env(env_path, g, q)
        result["keys"] = (g, q)
        if "offline" in (gr, qr):
            say("حفظت المفاتيح، بس ماقدرتش أتأكد منها دلوقتي (النت؟).", INK2)
            root.after(1600, root.destroy)
        else:
            root.destroy()

    go = tk.Button(buttons, text=ar("يلا نبدأ"), command=done, font=("Segoe UI", 11, "bold"), bg=ACCENT, fg="#0b1e1c",
                   relief="flat", activebackground="#57d6c9", padx=22, pady=6, cursor="hand2")
    go.pack(side="right")
    def no_key():
        write_env(env_path, "", q_var.get().strip() if looks_like("groq", q_var.get().strip()) else "")
        result["keys"] = ("", "")
        root.destroy()

    tk.Button(buttons, text=ar("كمّل من غير مفتاح"), command=no_key, font=font, bg="#26262e", fg=INK2, relief="flat",
              activebackground="#33333d", activeforeground=INK, padx=12, pady=6, cursor="hand2").pack(side="left")
    tk.Button(buttons, text=ar("خروج"), command=root.destroy, font=font, bg="#26262e", fg=INK, relief="flat",
              activebackground="#33333d", activeforeground=INK, padx=16, pady=6, cursor="hand2").pack(side="right", padx=(0, 8))
    root.bind("<Return>", lambda _e: done())

    root.update_idletasks()
    w, h = max(540, root.winfo_reqwidth()), root.winfo_reqheight()
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
    root.attributes("-topmost", True)
    root.after(400, lambda: root.attributes("-topmost", False))
    g_entry.focus_set()
    root.mainloop()
    return result.get("keys")


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    print(ask_keys(p, force=True))
