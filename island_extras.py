# -*- coding: utf-8 -*-
"""
Island extras — التطبيقات المثبتة، الطقس، النت، الحافظة الذكية، لحظات اليوم
(صباح الخير / أهلا رجعت / خد بريك)، إذاعة القرآن، وتوفير البطارية.

Weather uses the prayer location from Settings (no IP lookup). Radio stations come from
mp3quran.net and only play from the hosts in RADIO_HOSTS.
"""

import ctypes
import datetime as dt
import json
import os
import random
import re
import threading
import time
import urllib.request
import webbrowser
from ctypes import wintypes
from island_tools import tr

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

_HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(_HERE, "island_state.json")

PIN_MAX = 12
DEFAULT_PINS = ["discord", "google chrome", "spotify", "visual studio code", "steam", "telegram",
                "whatsapp", "notepad", "calculator", "file explorer", "microsoft edge", "obs studio"]
RADIO_API = "https://mp3quran.net/api/v3/radios?language=ar"
RADIO_HOSTS = ("backup.qurango.net", "stream.radiojar.com")
NCSI = "http://www.msftconnecttest.com/connecttest.txt"
AWAY_S = 5 * 60
LONG_AWAY_S = 30 * 60
WORK_S = 50 * 60
CARE = [   # (title, text) in Arabic, then in English
    ("قوم اتحرك شوية", "بقالك ٥٠ دقيقة قدام الشاشة. دقيقتين حركة بيصحّوا الجسم والدماغ.",
     "Get up and move", "You've been at the screen for 50 minutes. Two minutes of moving wakes up body and mind."),
    ("ريّح عينك", "بص على حاجة بعيدة ٢٠ ثانية، قاعدة ٢٠-٢٠-٢٠.",
     "Rest your eyes", "Look at something far away for 20 seconds: the 20-20-20 rule."),
    ("خد نفس عميق", "شهيق ٤ ثواني، اكتم ٤، زفير ٤. كرّرها ٣ مرات.",
     "Take a deep breath", "Breathe in for 4 seconds, hold 4, out 4. Repeat 3 times."),
    ("فرد ضهرك", "ارفع كتافك وارجعهم لورا، وفرد رقبتك يمين وشمال.",
     "Stretch your back", "Lift your shoulders and roll them back, then stretch your neck left and right."),
]


# ── smart clipboard ──────────────────────────────────────────────────
URL_RE = re.compile(r"^https?://[^\s<>\"']{3,2000}$", re.I)
HEX_RE = re.compile(r"^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$", re.I)
RGB_RE = re.compile(r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*[\d.]+\s*)?\)$", re.I)
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def calc(src):
    """Arithmetic only: numbers, + - * / ^ % and parentheses. Never eval."""
    s = src.translate(_AR_DIGITS).replace("×", "*").replace("÷", "/").replace(",", "").replace(" ", "")
    if not s or len(s) > 120 or not re.fullmatch(r"[\d.+\-*/^%()]+", s):
        raise ValueError("not arithmetic")
    pos = 0

    def peek():
        return s[pos] if pos < len(s) else ""

    def eat(ch):
        nonlocal pos
        if peek() == ch:
            pos += 1
            return True
        return False

    def number():
        nonlocal pos
        m = re.match(r"\d+(?:\.\d+)?", s[pos:])
        if not m:
            raise ValueError("number expected")
        pos += m.end()
        return float(m.group())

    def factor():
        if eat("-"):
            return -factor()
        if eat("+"):
            return factor()
        if eat("("):
            v = expr()
            if not eat(")"):
                raise ValueError(") expected")
        else:
            v = number()
        if eat("%"):
            v /= 100
        if eat("^"):
            p = factor()
            if abs(p) > 64:
                raise ValueError("power too large")
            v = v ** p
        return v

    def term():
        v = factor()
        while peek() in ("*", "/"):
            if eat("*"):
                v *= factor()
            elif eat("/"):
                d = factor()
                if d == 0:
                    raise ValueError("division by zero")
                v /= d
        return v

    def expr():
        v = term()
        while peek() in ("+", "-"):
            if eat("+"):
                v += term()
            elif eat("-"):
                v -= term()
        return v

    v = expr()
    if pos != len(s):
        raise ValueError("trailing input")
    return v


def classify(text):
    """What a copied text is, and the one useful thing to offer. None for plain text."""
    t = (text or "").strip()
    if not t:
        return None
    if URL_RE.match(t):
        return {"kind": "link", "value": t}
    if HEX_RE.match(t):
        h = t[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return {"kind": "color", "value": "#" + h[:6].upper()}
    m = RGB_RE.match(t)
    if m and all(0 <= int(x) <= 255 for x in m.groups()):
        return {"kind": "color", "value": "#" + "".join(f"{int(x):02X}" for x in m.groups())}
    # dates (2026-11-07) and phone numbers (010-1234-5678) use '-' too: they aren't sums
    dashes_only = re.fullmatch(r"[\d٠-٩]+(?:-[\d٠-٩]+)+", t)
    if not dashes_only and re.search(r"\d", t.translate(_AR_DIGITS)) and re.search(r"[+\-*/^%×÷]", t.strip("-+")) and len(t) <= 120:
        try:
            v = calc(t)
            if abs(v) < 1e15:
                out = f"{v:.10g}"
                return {"kind": "math", "value": t, "result": out}
        except (ValueError, OverflowError, ZeroDivisionError):
            pass
    words = len(t.split())
    if words >= 40:
        return {"kind": "count", "words": words, "chars": len(t)}
    return None


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(data):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def idle_seconds():
    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LII()
    lii.cbSize = ctypes.sizeof(lii)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
    except Exception:
        return 0.0


class IslandExtras:
    TICK_S = 1.0

    def __init__(self, send, island=None, daily=None, tools=None, log=print):
        self._send = send
        self._island = island
        self._daily = daily
        self._tools = tools
        self._log = log
        self._stop = threading.Event()
        self.weather = None
        self._weather_next = 0.0
        self._weather_fails = 0
        self._online = None
        self._offline_since = None
        self._net_next = 0.0
        self._state = load_state()
        self._away_since = None
        self._active_since = time.time()
        self._care_i = random.randrange(len(CARE))
        self._radio = None
        self._radio_at = 0.0
        self._saver = None
        self.events = []                      # (time, text) things worth telling after an absence

    @property
    def cfg(self):
        return self._tools.cfg if self._tools is not None else {}

    # ── lifecycle ─────────────────────────────────────────────
    def start(self):
        threading.Thread(target=self._loop, name="island-extras", daemon=True).start()

    def stop(self):
        self._stop.set()

    def note(self, text):
        """Other services report what happened (a download finished, ...)."""
        self.events.append((time.time(), text))
        self.events = self.events[-20:]

    def handle(self, msg):
        t = msg.get("t")
        try:
            if t == "panel" and msg.get("open"):
                self._send_apps()
                if self.weather:
                    self._send({"t": "weather", **self.weather})
            elif t == "apps_get":
                self._send_apps(with_catalog=True)
            elif t == "app_open":
                threading.Thread(target=self._open_app, args=(str(msg.get("name", "")),), daemon=True).start()
            elif t in ("app_pin", "app_unpin"):
                self._pin(str(msg.get("name", "")), t == "app_pin")
            elif t == "radio_get":
                threading.Thread(target=self._send_radio, daemon=True).start()
            elif t == "smart_action":
                self._smart_action(msg)
        except (TypeError, ValueError):
            pass

    def _loop(self):
        n = 0
        while not self._stop.wait(self.TICK_S):
            n += 1
            for step, every in ((self._weather_tick, 5), (self._net_tick, 1), (self._moments_tick, 2),
                                (self._saver_tick, 20)):
                if n % every == 0:
                    try:
                        step()
                    except Exception as e:
                        self._log(f"⚠️ island extras: {type(e).__name__}: {e}")

    # ── apps ──────────────────────────────────────────────────
    def _catalog(self):
        agent = getattr(self._island, "_agent", None)
        try:
            return agent.catalog if agent is not None else None
        except Exception:
            return None

    def _entries(self):
        cat = self._catalog()
        if cat is None:
            return {}
        return {e.display.lower(): e for e in cat.entries if e.kind in ("app", "installed", "game")}

    def _pins(self):
        entries = self._entries()
        pins = [p for p in (self.cfg.get("pinned_apps") or []) if p.lower() in entries]
        if not pins and not self.cfg.get("pinned_apps"):
            pins = [entries[d].display for d in DEFAULT_PINS if d in entries][:8]
        return pins[:PIN_MAX]

    @staticmethod
    def _exe(entry):
        launch = entry.launch[0] if isinstance(entry.launch, list) and entry.launch else entry.launch
        if isinstance(launch, str) and launch.lower().endswith(".exe") and os.path.isfile(launch):
            return launch
        return None

    def _send_apps(self, with_catalog=False):
        entries = self._entries()
        if not entries:
            return
        running = set()
        if psutil is not None:
            for p in psutil.process_iter(["name"]):
                running.add((p.info.get("name") or "").lower())
        items = []
        for name in self._pins():
            e = entries[name.lower()]
            exe = self._exe(e)
            items.append({"name": e.display, "icon": exe or "",
                          "running": bool(exe and os.path.basename(exe).lower() in running)})
        msg = {"t": "apps", "pinned": items}
        if with_catalog:
            msg["catalog"] = sorted({e.display for e in entries.values()}, key=str.lower)
        self._send(msg)

    def _pin(self, name, on):
        from island_tools import save_section
        entries = self._entries()
        pins = self._pins()
        if on and name.lower() in entries and name not in pins and len(pins) < PIN_MAX:
            pins.append(entries[name.lower()].display)
        elif not on:
            pins = [p for p in pins if p.lower() != name.lower()]
        else:
            return
        self._tools.cfg["pinned_apps"] = pins
        save_section("island", {"pinned_apps": pins})
        self._send_apps()

    def _open_app(self, name):
        e = self._entries().get(name.lower())
        if e is None:
            return
        exe = self._exe(e)
        if exe and self._focus_running(os.path.basename(exe)):
            return
        agent = getattr(self._island, "_agent", None)
        try:
            agent.launch(e)
        except Exception as err:
            self._send({"t": "say", "text": tr(f"معرفتش أفتح {e.display}: {err}", f"Couldn't open {e.display}: {err}"), "state": "error", "chime": True})

    @staticmethod
    def _focus_running(exe_name):
        """Bring an already-open window of this app to the front."""
        if psutil is None:
            return False
        pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() == exe_name.lower()}
        if not pids:
            return False
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0 \
                    and not user32.GetWindow(hwnd, 4):           # skip owned popups
                found.append(hwnd)
            return True

        user32.EnumWindows(each, 0)
        if not found:
            return False
        hwnd = found[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)                            # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True

    # ── weather at the prayer location ────────────────────────
    def _weather_tick(self):
        if not self.cfg.get("weather", True) or time.time() < self._weather_next:
            return
        d = self._daily.cfg if self._daily is not None else {"lat": 30.0444, "lon": 31.2357, "city": ""}
        url = ("https://api.open-meteo.com/v1/forecast?latitude={:.4f}&longitude={:.4f}"
               "&current=temperature_2m,weather_code,is_day&daily=temperature_2m_max,temperature_2m_min"
               "&timezone=auto&forecast_days=1").format(float(d["lat"]), float(d["lon"]))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Yobi"}), timeout=15) as r:
                w = json.loads(r.read())
            self.weather = {"temp": round(w["current"]["temperature_2m"]), "code": int(w["current"]["weather_code"]),
                            "is_day": bool(w["current"]["is_day"]), "hi": round(w["daily"]["temperature_2m_max"][0]),
                            "lo": round(w["daily"]["temperature_2m_min"][0]), "city": d.get("city", "")}
            self._send({"t": "weather", **self.weather})
            self._weather_fails = 0
            self._weather_next = time.time() + 20 * 60
        except Exception:
            self._weather_next = time.time() + [2, 5, 15][min(self._weather_fails, 2)] * 60
            self._weather_fails += 1

    def refresh_weather(self):
        self._weather_next = 0.0

    # ── internet ──────────────────────────────────────────────
    def _net_tick(self):
        if time.time() < self._net_next:
            return
        self._net_next = time.time() + (5 if self._online is False else 15)   # notice a return fast
        threading.Thread(target=self._probe, daemon=True).start()

    def _probe(self):
        try:
            with urllib.request.urlopen(NCSI, timeout=6) as r:
                online = r.status == 200 and r.read(40).startswith(b"Microsoft Connect Test")
        except Exception:
            online = False
        was = self._online
        self._online = online
        if was is None or was == online:
            return
        if not online:
            self._offline_since = time.time()
            self.note(tr("النت فصل", "The internet dropped"))
        gone = int(time.time() - self._offline_since) if online and self._offline_since else 0
        if self.cfg.get("net_toasts", True):
            self._send({"t": "hud", "kind": "net", "online": online, "gone_s": gone})
        if online:
            self.note(tr("النت رجع", "The internet came back"))
            self.refresh_weather()

    # ── moments: morning brief, welcome back, take a break ────
    def _free(self):
        isl = self._island
        try:
            free = isl._state == "idle" and not isl.reply_visible()
        except Exception:
            free = True
        try:
            from island_widgets import foreground_fullscreen
            return free and not foreground_fullscreen()
        except Exception:
            return free

    def _moments_tick(self):
        idle = idle_seconds()
        now = time.time()
        if idle >= AWAY_S:
            if self._away_since is None:
                self._away_since = now - idle
            return
        if idle > 30:
            return
        today = dt.date.today().isoformat()
        # first time at the computer today (from 4 am): the morning brief
        if (self.cfg.get("morning_brief", True) and self._state.get("brief_day") != today
                and dt.datetime.now().hour >= 4 and self._free()):
            self._state["brief_day"] = today
            save_state(self._state)
            self._away_since = None
            self._active_since = now
            self._send(self._brief())
            return
        # back after an absence: tell what happened meanwhile, if anything did
        if self._away_since is not None:
            away = now - self._away_since
            since = self._away_since
            self._away_since = None
            self._active_since = now
            happened = [t for (ts, t) in self.events if ts >= since]
            happened += self._prayers_between(since, now)
            if self.cfg.get("welcome_back", True) and (happened or away >= LONG_AWAY_S) and self._free():
                self._send({"t": "notice", "kind": "welcome", "away_min": int(away // 60), "events": happened[-4:]})
            return
        # 50 minutes of continuous use: a gentle break card
        focusing = self._daily is not None and self._daily.phase == "focus"
        if self.cfg.get("wellbeing", True) and now - self._active_since >= WORK_S and not focusing and self._free():
            self._active_since = now
            ar_title, ar_text, en_title, en_text = CARE[self._care_i % len(CARE)]
            title, text = tr(ar_title, en_title), tr(ar_text, en_text)
            self._care_i += 1
            self._send({"t": "notice", "kind": "care", "title": title, "text": text})

    def _prayers_between(self, a, b):
        names = {"fajr": ("الفجر", "Fajr"), "dhuhr": ("الظهر", "Dhuhr"), "asr": ("العصر", "Asr"),
                 "maghrib": ("المغرب", "Maghrib"), "isha": ("العشاء", "Isha")}
        times = getattr(self._daily, "_times", {}) or {}
        return [tr(f"أذان {names[k][0]}", f"{names[k][1]} adhan") for k in names if k in times and a * 1000 <= times[k] <= b * 1000]

    def _brief(self):
        h = dt.datetime.now().hour
        greet = tr("صباح الفل ☀️", "Good morning ☀️") if h < 12 else tr("مساء الخير 🌙", "Good evening 🌙") if h >= 17 else tr("أهلا بيك 👋", "Hello 👋")
        nxt = None
        times = getattr(self._daily, "_times", {}) or {}
        now_ms = time.time() * 1000
        for k in ("fajr", "dhuhr", "asr", "maghrib", "isha"):
            if times.get(k, 0) > now_ms:
                nxt = {"prayer": k, "at": times[k]}
                break
        meetings = [e for e in getattr(self._daily, "_events", []) if e["start"] > now_ms]
        return {"t": "notice", "kind": "brief", "greet": greet, "weather": self.weather, "next": nxt,
                "meetings": len(meetings), "first_meeting": meetings[0] if meetings else None}

    # ── Qur'an radio stations ─────────────────────────────────
    def _send_radio(self):
        if self._radio is None or time.time() - self._radio_at > 6 * 3600:
            try:
                with urllib.request.urlopen(urllib.request.Request(RADIO_API, headers={"User-Agent": "Yobi"}),
                                            timeout=15) as r:
                    radios = json.loads(r.read()).get("radios", [])
                self._radio = [{"name": str(x["name"])[:80], "url": x["url"]} for x in radios
                               if radio_url_ok(x.get("url"))]
                self._radio_at = time.time()
            except Exception:
                self._send({"t": "radio_stations", "items": [], "error": True})
                return
        self._send({"t": "radio_stations", "items": self._radio})

    # ── smart clipboard actions ───────────────────────────────
    def _smart_action(self, msg):
        if msg.get("action") == "open_link":
            url = str(msg.get("value", ""))
            if URL_RE.match(url):
                webbrowser.open(url)
        elif msg.get("action") == "copy_result" and self._tools is not None:
            res = str(msg.get("value", ""))
            if re.fullmatch(r"-?[\d.e+]+", res):
                self._tools.copy_text(res)

    # ── battery saver ─────────────────────────────────────────
    def _saver_tick(self):
        on = False
        if self.cfg.get("battery_saver") and psutil is not None:
            bat = psutil.sensors_battery()
            if bat is not None and not bat.power_plugged:
                at = int(self.cfg.get("battery_saver_at", 20))
                on = bat.percent <= at or (self._saver and bat.percent < at + 10)
        if on != self._saver:
            self._saver = bool(on)
            self._send({"t": "battery_saver", "on": self._saver})


def radio_url_ok(url):
    if not isinstance(url, str):
        return False
    m = re.match(r"^https://([^/\s]+)/\S*$", url)
    return bool(m) and m.group(1).lower() in RADIO_HOSTS
