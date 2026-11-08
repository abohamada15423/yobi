# -*- coding: utf-8 -*-
"""
ElectronIsland — يوبي بواجهة جديدة (Electron) بدل ui.py.

Same public methods agent.py already calls on DynamicIsland (after, set_state,
say, ask, end_turn, is_free, mainloop, bind ...), so the agent barely changes.
The Electron window in island/ only draws; every decision stays in Python.

Transport: a 127.0.0.1 socket with a one-time token, JSON one message per line.
Callbacks given to after() run on the thread that calls mainloop(), like Tk.
"""

import heapq
import itertools
import json
import os
import secrets
import socket
import subprocess
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
ISLAND_DIR = os.path.join(_HERE, "island")

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
_KNOWN = {"idle", "listening", "recording", "thinking", "executing", "account",
          "speaking", "success", "error", "info", "suggesting"}
_ACTIVE = {"listening", "recording", "thinking", "executing", "account", "speaking"}
SAY_MAX = 230


# The Electron runtime and the Tauri build live in ~/.yobi: out of OneDrive (they're big) and out of
# AppData, which the Claude desktop app redirects to its own private folder for anything it writes.
YOBI_HOME = os.path.join(os.path.expanduser("~"), ".yobi")


def find_electron():
    """electron.exe: YOBI_ELECTRON, then island/node_modules, then the shared runtime."""
    cands = [
        os.environ.get("YOBI_ELECTRON"),
        os.path.join(ISLAND_DIR, "node_modules", "electron", "dist", "electron.exe"),
        os.path.join(YOBI_HOME, "electron-runtime", "node_modules", "electron", "dist", "electron.exe"),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


TAURI_DIR = os.path.join(_HERE, "island-tauri")


def find_tauri():
    """The Tauri island (island-tauri/): YOBI_TAURI, then its release and debug builds."""
    target = os.path.join(YOBI_HOME, "tauri-target")
    for c in (os.environ.get("YOBI_TAURI"),
              os.path.join(target, "release", "yobi-island.exe"),
              os.path.join(target, "debug", "yobi-island.exe")):
        if c and os.path.isfile(c):
            return c
    return None


def norm_state(state):
    s = str(state or "").strip().lower()
    s = STATE_ALIASES.get(s, s)
    return s if s in _KNOWN else "info"


def reading_ms(text, state):
    """How long a reply stays readable (mirrors island.js)."""
    n = len(str(text or ""))
    if state == "success":
        return 3800 + min(4000, n * 25)
    if state == "error":
        return 4500 + min(4000, n * 25)
    typing = n / max(30.0, n / 3.5) * 1000
    return typing + min(10000, max(4000, n * 45))


def shorten(text):
    full = " ".join(str(text or "").split())
    return full if len(full) <= SAY_MAX else full[:SAY_MAX - 1].rstrip() + "…"


class ElectronIsland:
    CONNECT_TIMEOUT_S = 25

    def __init__(self, electron_exe=None, log=print, engine="electron"):
        """engine: "electron" (island/) or "tauri" (island-tauri/). Same messages either way."""
        self._init_core(log)

        if engine == "tauri":
            exe = find_tauri()
            if not exe:
                raise RuntimeError("yobi-island.exe مش موجود (اعمل build لـ island-tauri)")
            args, cwd = [exe], TAURI_DIR
        else:
            exe = electron_exe or find_electron()
            if not exe:
                raise RuntimeError("electron.exe مش موجود (شغّل: npm install جوه island)")
            args, cwd = [exe, ISLAND_DIR], ISLAND_DIR
        token = secrets.token_hex(16)
        srv = socket.create_server(("127.0.0.1", 0))
        srv.settimeout(self.CONNECT_TIMEOUT_S)
        port = srv.getsockname()[1]
        env = dict(os.environ, YOBI_ISLAND_PORT=str(port), YOBI_ISLAND_TOKEN=token)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        self._proc = subprocess.Popen(
            args, env=env, cwd=cwd,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            self._sock, self._rfile = self._accept(srv, token)
        except Exception:
            self._proc.kill()
            raise
        finally:
            srv.close()
        threading.Thread(target=self._reader, name="island-reader", daemon=True).start()
        try:
            from island_widgets import IslandWidgets
            self._widgets = IslandWidgets(self._send, log=log)
            self._widgets.start()
        except Exception as e:
            log(f"⚠️ island widgets: {e}")
        try:
            from island_daily import IslandDaily
            from island_widgets import foreground_fullscreen
            self._daily = IslandDaily(
                self._send, log=log, is_fullscreen=foreground_fullscreen,
                is_free=lambda: self._state == "idle" and not self.reply_visible())
            self._daily.start()
        except Exception as e:
            log(f"⚠️ island daily: {e}")
        try:
            from island_tools import IslandTools
            self._tools = IslandTools(self._send, daily=self._daily, log=log)
            self._tools.start()
        except Exception as e:
            log(f"⚠️ island tools: {e}")
        try:
            from island_extras import IslandExtras
            self._extras = IslandExtras(self._send, island=self, daily=self._daily, tools=self._tools, log=log)
            if self._tools is not None:
                self._tools.extras = self._extras
            self._extras.start()
        except Exception as e:
            log(f"⚠️ island extras: {e}")

    def _init_core(self, log=print):
        """Everything except the window, so tests can run without Electron."""
        self._log = log
        self._lock = threading.Lock()           # socket writes
        self._cv = threading.Condition()        # scheduler
        self._heap = []
        self._seq = itertools.count()
        self._cancelled = set()
        self._closed = False
        self._binds = {}
        self._ask_cb = {}                        # id -> callback (only the latest is live)
        self._ask_live = None
        self._state = "idle"
        self._reply_until = 0.0
        self._last_activity = time.monotonic()
        self._chat_handler = None
        self._quick_cb = None
        self._companion_get = None
        self._companion_toggle = None
        self._agent = None                       # agent.py sets island._agent
        self._level_thread = None
        self._widgets = None                     # island_widgets.IslandWidgets
        self._daily = None                       # island_daily.IslandDaily
        self._tools = None                       # island_tools.IslandTools
        self._extras = None                      # island_extras.IslandExtras

    # ── connection ────────────────────────────────────────────
    def _accept(self, srv, token):
        deadline = time.monotonic() + self.CONNECT_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"Electron قفل (exit {self._proc.returncode})")
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                break
            conn.settimeout(5)
            rfile = conn.makefile("r", encoding="utf-8")
            try:
                hello = json.loads(rfile.readline(4096) or "{}")
            except Exception:
                hello = {}
            # Only the window we started knows the token; anything else is dropped.
            if (isinstance(hello, dict) and hello.get("t") == "hello"
                    and secrets.compare_digest(str(hello.get("token", "")), token)):
                conn.settimeout(None)
                return conn, rfile
            conn.close()
        raise RuntimeError("الواجهة مردتش في الوقت")

    def _send(self, msg):
        if self._closed:
            return
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            try:
                self._sock.sendall(data)
            except OSError:
                self._on_disconnect()

    def _reader(self):
        try:
            for line in self._rfile:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    self.after(0, self._handle, msg)
        except OSError:
            pass
        self._on_disconnect()

    def _on_disconnect(self):
        if self._closed:
            return
        self._closed = True
        if self._widgets is not None:
            self._widgets.stop()
        for svc in (self._daily, self._tools, self._extras):
            if svc is not None:
                svc.stop()
        quit_fn = self._binds.get("<<YobiQuit>>")
        with self._cv:
            self._cv.notify_all()
        if quit_fn:
            threading.Thread(target=lambda: quit_fn(None), daemon=True).start()

    # ── Tk-like scheduling ────────────────────────────────────
    def after(self, ms, fn=None, *args):
        if fn is None:
            time.sleep(max(0, ms) / 1000)
            return None
        job = next(self._seq)
        with self._cv:
            heapq.heappush(self._heap, (time.monotonic() + max(0, ms) / 1000, job, fn, args))
            self._cv.notify()
        return job

    def after_cancel(self, job):
        with self._cv:
            self._cancelled.add(job)

    def mainloop(self):
        # Tk dialogs that agent.py still opens (save-login) need a root on this thread;
        # keep it hidden so no empty "tk" window appears.
        try:
            import tkinter
            if tkinter._default_root is None:
                tkinter.Tk().withdraw()
        except Exception:
            pass
        while True:
            with self._cv:
                while not self._closed:
                    if self._heap and self._heap[0][0] <= time.monotonic():
                        break
                    timeout = (self._heap[0][0] - time.monotonic()) if self._heap else None
                    self._cv.wait(timeout)
                if self._closed:
                    return
                _, job, fn, args = heapq.heappop(self._heap)
                if job in self._cancelled:
                    self._cancelled.discard(job)
                    continue
            try:
                fn(*args)
            except Exception as e:
                self._log(f"⚠️ island callback: {e}")

    def bind(self, sequence, fn, add=None):
        self._binds[sequence] = fn

    def quit(self):
        self._send({"t": "quit"})
        self._closed = True
        with self._cv:
            self._cv.notify_all()

    destroy = quit

    # ── public API used by agent.py ───────────────────────────
    def set_state(self, state, text="", quiet=False):
        st = norm_state(state)
        text = "" if text is None else str(text)
        self._state = st
        self._last_activity = time.monotonic()
        self._reply_until = (time.monotonic() + reading_ms(text, st) / 1000
                             if st in ("success", "error", "info") and text else 0.0)
        self._send({"t": "state", "state": st, "text": shorten(text)})
        if st in ("listening", "recording"):
            self._start_level_feed()

    def say(self, text, state=None, chime=True):
        shown = shorten(text)
        if not shown:
            return
        st = norm_state(state) if state else (self._state if self._state in ("success", "error", "info") else "info")
        if st not in ("success", "error", "info"):
            st = "info"
        self._state = st
        self._last_activity = time.monotonic()
        self._reply_until = time.monotonic() + reading_ms(shown, st) / 1000
        self._send({"t": "say", "text": shown, "state": st, "chime": bool(chime)})

    typewriter_text = say

    def ask(self, question, options=None, callback=None, timeout_ms=30000, chime=True):
        opts = [[str(o[0]), o[1]] for o in (options or [("أيوه 👍", "yes"), ("لا", "no")])]
        ask_id = secrets.token_hex(6)
        self._ask_live = ask_id
        self._ask_cb = {ask_id: callback}
        self._state = "suggesting"
        self._last_activity = time.monotonic()
        self._reply_until = time.monotonic() + int(timeout_ms) / 1000
        self._send({"t": "ask", "id": ask_id, "text": shorten(question), "options": opts,
                    "timeout": int(timeout_ms), "chime": bool(chime)})

    def show_listening_soft(self, text=""):
        if self.reply_visible():
            return
        self._state = "listening"
        self._send({"t": "listening_soft", "text": str(text or "")})
        self._start_level_feed()

    def end_turn(self):
        if self.reply_visible():
            return
        if self._state in _ACTIVE:
            self._state = "idle"
        self._send({"t": "end_turn"})

    def reply_visible(self):
        return time.monotonic() < self._reply_until

    def is_free(self, min_idle_s=60):
        return (self._state == "idle" and not self.reply_visible()
                and time.monotonic() - self._last_activity >= min_idle_s)

    def set_progress(self, value):
        try:
            self._send({"t": "progress", "v": float(value)})
        except (TypeError, ValueError):
            pass

    def set_companion_toggle(self, get_enabled, toggle):
        self._companion_get = get_enabled
        self._companion_toggle = toggle

    def set_companion(self, companion):
        """The island's water slot shows and adds to the companion's own count."""
        if self._daily is not None:
            self._daily.set_companion(companion)

    def set_quick_action_callback(self, callback):
        self._quick_cb = callback

    def set_chat_handler(self, handler):
        self._chat_handler = handler

    # Accepted for compatibility; this island has no avatar, overlay or history panel yet.
    def set_speaking(self, speaking):
        pass

    def set_avatar_mood(self, mood):
        pass

    def set_suggestions(self, items, callback=None):
        pass

    def pulse(self):
        pass

    def get_overlay(self):
        return None

    def run_demo(self):
        steps = [
            (0, lambda: self.set_state("listening", "سامعك.. اتكلم 🎤")),
            (3200, lambda: self.set_state("thinking", "بفكر في طلبك…")),
            (6000, lambda: (self.set_state("executing", "بفتح Discord"), self.set_progress(2.0))),
            (8600, lambda: self.set_state("success", "تمام، فتحت ديسكورد ✅")),
            (13000, lambda: self.say("الساعة ١٠:٤٥ بالليل. لو هتلعب كمان، اشرب مياه الأول 💧", state="info")),
            (21000, lambda: self.ask("قصدك Euro Truck Simulator 2 ولا Rocket League؟",
                                     [("Euro Truck Simulator 2", "a"), ("Rocket League", "b"),
                                      ("لا، ولا حاجة", "none")], lambda v: None, timeout_ms=9000)),
            (31000, lambda: self.set_state("error", "مش لاقي البرنامج ده على الجهاز")),
        ]
        for ms, fn in steps:
            self.after(ms, fn)

    # ── events from the window ────────────────────────────────
    def _handle(self, msg):
        t = msg.get("t")
        if t == "answer":
            ask_id = msg.get("id")
            if ask_id != self._ask_live:
                return                    # an older question; the current one is still open
            cb = self._ask_cb.pop(ask_id, None)
            self._ask_live = None
            self._reply_until = 0.0
            if cb:
                cb(msg.get("value"))
        elif t == "view":
            st = norm_state(msg.get("state"))
            if st == "idle":
                self._state = "idle"
                self._reply_until = 0.0
        elif t == "quick" and self._quick_cb:
            self._quick_cb(str(msg.get("id", "")))
        elif t == "chat":
            text = str(msg.get("text", "")).strip()[:500]
            if text:
                self._last_activity = time.monotonic()
                threading.Thread(target=self._run_chat, args=(text,), daemon=True).start()
        elif t in ("panel", "media"):
            if self._widgets is not None:
                self._widgets.handle(msg)
            if t == "panel":
                for svc in (self._daily, self._tools, self._extras):
                    if svc is not None:
                        svc.handle(msg)
        elif t in ("focus", "water", "meeting_join", "notice_action", "notice_dropped"):
            for svc in (self._daily, self._tools):     # each ignores what isn't its own
                if svc is not None:
                    svc.handle(msg)
        elif t in ("apps_get", "app_open", "app_pin", "app_unpin", "radio_get", "smart_action"):
            if self._extras is not None:
                self._extras.handle(msg)
        elif t in ("clip_copy", "clip_clear", "shelf_add", "shelf_open", "shelf_folder",
                   "shelf_remove", "shelf_clear", "dl_open", "dl_folder", "settings_get", "settings_set",
                   "preview"):
            if self._tools is not None:
                self._tools.handle(msg)
        elif t == "menu_open":
            self._send_menu_state()
        elif t == "log":
            self._log(f"⚠️ island window: {str(msg.get('text', ''))[:300]}")
        elif t == "menu":
            self._menu(str(msg.get("id", "")))

    def _run_chat(self, text):
        handler = self._chat_handler
        try:
            reply = handler(text) if handler else f"استلمت: {text}"
        except Exception as e:
            reply = f"❌ حصل خطأ: {e}"
        if reply:
            self.after(0, self.say, str(reply), "info")
        else:
            self.after(0, self.end_turn)

    def _menu(self, item):
        agent = self._agent
        if item == "toggle_listen" and agent is not None and hasattr(agent, "toggle_listen"):
            agent.toggle_listen()
        elif item == "toggle_voice" and agent is not None and hasattr(agent, "toggle_voice_reply"):
            agent.toggle_voice_reply()
        elif item == "toggle_companion" and self._companion_toggle:
            self._companion_toggle()
        elif item == "demo":
            self.run_demo()
        elif item == "quit":
            fn = self._binds.get("<<YobiQuit>>")
            if fn:
                threading.Thread(target=lambda: fn(None), daemon=True).start()
            else:
                self.quit()
            return
        self._send_menu_state()

    def _send_menu_state(self):
        agent = self._agent
        listen = voice = companion = None
        try:
            ev = getattr(agent, "listening_enabled", None)
            listen = ev.is_set() if ev is not None else None
        except Exception:
            pass
        try:
            voice = bool(agent.get_voice_reply()) if hasattr(agent, "get_voice_reply") else None
        except Exception:
            pass
        try:
            companion = bool(self._companion_get()) if self._companion_get else None
        except Exception:
            pass
        self._send({"t": "menu_state", "listen": listen, "voice": voice, "companion": companion})

    # ── mic level for the listening line ──────────────────────
    def _start_level_feed(self):
        if self._level_thread is not None and self._level_thread.is_alive():
            return
        self._level_thread = threading.Thread(target=self._level_loop, name="island-level", daemon=True)
        self._level_thread.start()

    def _level_loop(self):
        try:
            from audio_io import get_audio_engine
        except Exception:
            return              # the window breathes on its own without levels
        while not self._closed and self._state in ("listening", "recording"):
            eng = get_audio_engine()
            if eng is None:
                return
            self._send({"t": "level", "v": round(min(1.0, float(getattr(eng, "level", 0.0)) * 1.8), 3)})
            time.sleep(0.05)
