# -*- coding: utf-8 -*-
"""
Island daily — يومك على الجزيرة: مواقيت الصلاة، جلسات التركيز، المياه (من companion)،
أذكار وأدعية وآيات، ومواعيد الاجتماعات من رابط iCal.

Settings: config.json -> "daily" (all optional):
    "city": "القاهرة", "lat": 30.0444, "lon": 31.2357,
    "method": "EGYPT",            # EGYPT | MWL | MAKKAH | KARACHI | ISNA
    "asr": "standard",            # standard | hanafi
    "tune": {"maghrib": 2},       # minutes added per prayer to match your local timetable
    "prayer_alerts": true, "prayer_soon_min": 10,
    "focus_min": 25, "break_min": 5, "long_break_min": 15,
    "reminders": true, "remind_every_min": 20, "remind_for_s": 20,
    "quiet_hours": "",            # e.g. "23:00-07:00"
    "calendar_ical": ""           # private iCal link; kept out of logs
"""

import datetime as dt
import json
import math
import os
import random
import re
import threading
import time
import urllib.request
import webbrowser

_HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "city": "القاهرة", "lat": 30.0444, "lon": 31.2357, "method": "EGYPT", "asr": "standard",
    "prayer_alerts": True, "prayer_soon_min": 10,
    "focus_min": 25, "break_min": 5, "long_break_min": 15,
    "reminders": True, "remind_every_min": 20, "remind_for_s": 20, "quiet_hours": "",
    "calendar_ical": "",
}

# fajr / isha: sun angle below the horizon, or minutes after maghrib for isha
METHODS = {
    "EGYPT": {"fajr": 19.5, "isha": 17.5},
    "MWL": {"fajr": 18.0, "isha": 17.0},
    "MAKKAH": {"fajr": 18.5, "isha_min": 90},
    "KARACHI": {"fajr": 18.0, "isha": 18.0},
    "ISNA": {"fajr": 15.0, "isha": 15.0},
}
PRAYERS = ("fajr", "dhuhr", "asr", "maghrib", "isha")

REMINDERS = [
    ("dhikr", "سبحان الله وبحمده، سبحان الله العظيم", ""),
    ("dhikr", "أستغفر الله وأتوب إليه", ""),
    ("dhikr", "لا حول ولا قوة إلا بالله", ""),
    ("dhikr", "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير", ""),
    ("dhikr", "اللهم صلِّ وسلم على نبينا محمد", ""),
    ("dhikr", "سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر", ""),
    ("dua", "اللهم إني أسألك علمًا نافعًا، ورزقًا طيبًا، وعملًا متقبلًا", ""),
    ("dua", "اللهم أعنّي على ذكرك وشكرك وحسن عبادتك", ""),
    ("dua", "يا مقلب القلوب ثبّت قلبي على دينك", ""),
    ("dua", "اللهم إنك عفوٌّ تحب العفو فاعفُ عني", ""),
    ("ayah", "ألا بذكر الله تطمئن القلوب", "الرعد ٢٨"),
    ("ayah", "فاذكروني أذكركم واشكروا لي ولا تكفرون", "البقرة ١٥٢"),
    ("ayah", "فإن مع العسر يسرا", "الشرح ٥"),
    ("ayah", "وقل رب زدني علما", "طه ١١٤"),
    ("ayah", "ومن يتوكل على الله فهو حسبه", "الطلاق ٣"),
    ("ayah", "لا يكلف الله نفسا إلا وسعها", "البقرة ٢٨٦"),
    ("ayah", "رب اشرح لي صدري ويسر لي أمري", "طه ٢٥–٢٦"),
    ("ayah", "ربنا آتنا في الدنيا حسنة وفي الآخرة حسنة وقنا عذاب النار", "البقرة ٢٠١"),
]

JOIN_RE = re.compile(
    r"https://(?:meet\.google\.com/[a-z0-9-]+|teams\.(?:microsoft|live)\.com/[^\s\"'<>]+|"
    r"(?:[\w-]+\.)?zoom\.us/(?:j|my|w)/[^\s\"'<>]+|[\w-]+\.webex\.com/[^\s\"'<>]+)", re.I)


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(_HERE, "config.json"), encoding="utf-8") as f:
            cfg.update(json.load(f).get("daily") or {})
    except Exception:
        pass
    return cfg


# ── prayer times: standard solar position formulas ───────────────────
def _sin(d): return math.sin(math.radians(d))
def _cos(d): return math.cos(math.radians(d))
def _tan(d): return math.tan(math.radians(d))
def _acos(x): return math.degrees(math.acos(max(-1.0, min(1.0, x))))
def _fix(a, b): return a - b * math.floor(a / b)


def _julian(y, m, d):
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + 2 - a + a // 4 - 1524.5


def _sun(jd):
    """(declination, equation of time in hours) for a Julian day."""
    n = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * n, 360)
    q = _fix(280.459 + 0.98564736 * n, 360)
    lam = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * n
    ra = _fix(math.degrees(math.atan2(_cos(e) * _sin(lam), _cos(lam))) / 15, 24)
    decl = math.degrees(math.asin(_sin(e) * _sin(lam)))
    return decl, q / 15 - ra


def prayer_hours(y, m, d, lat, lon, tz_hours, method="EGYPT", asr_factor=1):
    """Local clock hours (e.g. 14.7) for fajr, sunrise, dhuhr, asr, maghrib, isha."""
    meth = METHODS.get(method, METHODS["EGYPT"])
    jd = _julian(y, m, d) - lon / (15 * 24)

    def noon(t):
        return _fix(12 - _sun(jd + t / 24)[1], 24)

    def at_angle(angle, t, before_noon=False):
        decl = _sun(jd + t / 24)[0]
        h = _acos((-_sin(angle) - _sin(decl) * _sin(lat)) / (_cos(decl) * _cos(lat))) / 15
        return noon(t) - h if before_noon else noon(t) + h

    def asr(t):
        decl = _sun(jd + t / 24)[0]
        angle = -math.degrees(math.atan(1 / (asr_factor + _tan(abs(lat - decl)))))
        return at_angle(angle, t)

    # two passes: the first guesses refine the sun's position for each time
    t = {"fajr": 5, "sunrise": 6, "dhuhr": 12, "asr": 13, "maghrib": 18, "isha": 18}
    for _ in range(2):
        f = {k: v / 24 for k, v in t.items()}
        t = {
            "fajr": at_angle(meth["fajr"], f["fajr"] * 24, True),
            "sunrise": at_angle(0.833, f["sunrise"] * 24, True),
            "dhuhr": noon(f["dhuhr"] * 24),
            "asr": asr(f["asr"] * 24),
            "maghrib": at_angle(0.833, f["maghrib"] * 24),
            "isha": at_angle(meth.get("isha", 17), f["isha"] * 24),
        }
    shift = tz_hours - lon / 15
    out = {k: v + shift for k, v in t.items()}
    if "isha_min" in meth:
        out["isha"] = out["maghrib"] + meth["isha_min"] / 60
    # shortcut: no high-latitude correction; fine below ~48°, add one before using it further north
    return out


def prayer_epochs(day, cfg):
    """{name: epoch ms} for a date, in this PC's time zone."""
    noon = dt.datetime(day.year, day.month, day.day, 12).astimezone()
    tz = noon.utcoffset().total_seconds() / 3600
    hours = prayer_hours(day.year, day.month, day.day, float(cfg["lat"]), float(cfg["lon"]), tz,
                         cfg.get("method", "EGYPT"), 2 if cfg.get("asr") == "hanafi" else 1)
    tune = cfg.get("tune") or {}            # minutes per prayer, to match a local timetable
    midnight = dt.datetime(day.year, day.month, day.day)
    # round to the minute, as printed timetables do
    return {k: int(round((midnight + dt.timedelta(hours=h + float(tune.get(k, 0)) / 60)).timestamp() / 60)
                   * 60 * 1000)
            for k, h in hours.items()}


def in_quiet(window, minute_of_day):
    if not window or "-" not in window:
        return False
    try:
        a, b = [int(p.split(":")[0]) * 60 + int(p.split(":")[1]) for p in window.split("-")]
    except Exception:
        return False
    return a <= minute_of_day < b if a <= b else minute_of_day >= a or minute_of_day < b


# ── the daily service ────────────────────────────────────────────────
class IslandDaily:
    TICK_S = 1.0

    def __init__(self, send, is_free=lambda: True, is_fullscreen=lambda: False, log=print, cfg=None):
        self._send = send
        self._is_free = is_free
        self._is_fullscreen = is_fullscreen
        self._log = log
        self.cfg = cfg or load_cfg()
        self.companion = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        # prayer
        self._day = None
        self._times = {}
        self._alerted = set()
        # focus
        self.phase = None           # None | focus | break | long
        self.ends_at = None         # epoch seconds while running
        self.paused_left = None     # seconds while paused
        self.total = 0
        self.round = 0
        # reminders
        self._bag = []
        self._last_reminder = None
        self._next_reminder = time.time() + float(self.cfg["remind_every_min"]) * 60
        # meetings
        self._events = []
        self._links = {}
        self._cal_next = 0.0
        self._cal_warned = False

    # ── lifecycle ─────────────────────────────────────────────
    def start(self):
        threading.Thread(target=self._loop, name="island-daily", daemon=True).start()

    def stop(self):
        self._stop.set()

    def set_companion(self, companion):
        self.companion = companion
        self._send_water()

    def handle(self, msg):
        t = msg.get("t")
        if t == "panel" and msg.get("open"):
            self._send_water()
            self._send_prayer()
            self._send_focus()
        elif t == "focus":
            cmd = msg.get("cmd")
            if cmd in ("start", "pause", "resume", "stop", "skip"):
                getattr(self, f"focus_{cmd}")()
        elif t == "water" and msg.get("cmd") == "add":
            threading.Thread(target=self._add_water, daemon=True).start()
        elif t == "meeting_join":
            link = self._links.get(str(msg.get("id")))
            if link and JOIN_RE.fullmatch(link):
                webbrowser.open(link)
        elif t == "notice_action" and msg.get("action") == "focus_start":
            self.focus_start()
        elif t == "notice_dropped" and msg.get("kind") == "reminder":
            if self._last_reminder:
                self._bag.append(self._last_reminder)    # show the same text next time
            self._next_reminder = time.time() + 60      # the island was busy: try again in a minute

    # ── loop ──────────────────────────────────────────────────
    def _loop(self):
        while not self._stop.wait(self.TICK_S):
            for step in (self._prayer_tick, self._focus_tick, self._reminder_tick, self._calendar_tick):
                try:
                    step()
                except Exception as e:
                    self._log(f"⚠️ island daily: {e}")

    # ── prayer ────────────────────────────────────────────────
    def _prayer_tick(self):
        today = dt.date.today()
        if today != self._day:
            self._day = today
            self._times = prayer_epochs(today, self.cfg)
            self._times["next_fajr"] = prayer_epochs(today + dt.timedelta(days=1), self.cfg)["fajr"]
            self._alerted = set()
            self._send_prayer()
        if not self.cfg.get("prayer_alerts", True):
            return
        now = time.time() * 1000
        soon = float(self.cfg["prayer_soon_min"]) * 60000
        for k in PRAYERS:
            at = self._times[k]
            if at - soon <= now < at - soon + 60000 and (k, "soon") not in self._alerted:
                self._alerted.add((k, "soon"))
                self._send({"t": "notice", "kind": "prayer_soon", "prayer": k, "at": at,
                            "minutes": int(self.cfg["prayer_soon_min"])})
            if at <= now < at + 60000 and (k, "adhan") not in self._alerted:
                self._alerted.add((k, "adhan"))
                self._send({"t": "notice", "kind": "adhan", "prayer": k, "at": at})

    def _send_prayer(self):
        if self._times:
            self._send({"t": "prayer", "city": self.cfg.get("city", ""),
                        "times": {k: v for k, v in self._times.items()}})

    # ── focus sessions ────────────────────────────────────────
    def _minutes_for(self, phase):
        return float(self.cfg["focus_min" if phase == "focus" else
                              "long_break_min" if phase == "long" else "break_min"])

    def _begin(self, phase):
        with self._lock:
            self.phase = phase
            self.total = self._minutes_for(phase) * 60
            self.ends_at = time.time() + self.total
            self.paused_left = None
        self._send_focus()

    def focus_start(self):
        with self._lock:
            self.round = 0
        self._begin("focus")

    def focus_pause(self):
        with self._lock:
            if self.phase and self.ends_at:
                self.paused_left = max(0.0, self.ends_at - time.time())
                self.ends_at = None
        self._send_focus()

    def focus_resume(self):
        with self._lock:
            if self.phase and self.paused_left is not None:
                self.ends_at = time.time() + self.paused_left
                self.paused_left = None
        self._send_focus()

    def focus_stop(self):
        with self._lock:
            self.phase, self.ends_at, self.paused_left, self.total = None, None, None, 0
        self._send_focus()

    def focus_skip(self):
        with self._lock:
            if self.phase:
                self.ends_at, self.paused_left = time.time(), None
        self._focus_tick()

    def _focus_tick(self):
        with self._lock:
            if not self.phase or self.ends_at is None or time.time() < self.ends_at:
                return
            done = self.phase
        if done == "focus":
            with self._lock:
                self.round += 1
                nxt = "long" if self.round % 4 == 0 else "break"
            self._send({"t": "notice", "kind": "focus_done", "round": self.round,
                        "next_min": int(self._minutes_for(nxt))})
            self._begin(nxt)                       # the break starts by itself
        else:
            self.focus_stop()
            self._send({"t": "notice", "kind": "break_done", "focus_min": int(self._minutes_for("focus"))})

    def _send_focus(self):
        with self._lock:
            self._send({"t": "focus", "phase": self.phase, "round": self.round, "total": self.total,
                        "ends_at": int(self.ends_at * 1000) if self.ends_at else None,
                        "paused_left": self.paused_left,
                        "focus_min": int(self._minutes_for("focus"))})

    @property
    def focusing(self):
        return self.phase == "focus"

    # ── dhikr, du'a, ayah ─────────────────────────────────────
    def _reminder_tick(self):
        if not self.cfg.get("reminders", True):
            return
        now = time.time()
        if now < self._next_reminder:
            return
        lt = time.localtime()
        blocked = (self.focusing or in_quiet(self.cfg.get("quiet_hours", ""), lt.tm_hour * 60 + lt.tm_min)
                   or not self._is_free() or self._is_fullscreen())
        if blocked:
            self._next_reminder = now + 60          # try again in a minute
            return
        if not self._bag:
            self._bag = random.sample(REMINDERS, len(REMINDERS))  # nothing repeats until all were shown
        kind, text, ref = self._last_reminder = self._bag.pop()
        self._send({"t": "notice", "kind": "reminder", "sub": kind, "text": text, "ref": ref,
                    "seconds": int(self.cfg["remind_for_s"])})
        self._next_reminder = now + float(self.cfg["remind_every_min"]) * 60

    # ── water (counted by yopi's companion) ───────────────────
    def _send_water(self):
        c = self.companion
        if c is None:
            return
        try:
            self._send({"t": "water", "count": int(c.data.get("water_cups", 0)),
                        "goal": int(c.cfg.get("water_goal", 8))})
        except Exception:
            pass

    def _add_water(self):
        c = self.companion
        if c is None:
            return
        try:
            msg = c._drank()
        except Exception as e:
            self._log(f"⚠️ water: {e}")
            return
        self._send_water()
        if msg:
            self._send({"t": "say", "text": msg, "state": "success", "chime": True})

    # ── meetings from a private iCal link ─────────────────────
    def _calendar_tick(self):
        url = str(self.cfg.get("calendar_ical") or "").strip().replace("webcal://", "https://", 1)
        now = time.time()
        if url and now >= self._cal_next:
            self._cal_next = now + 600
            threading.Thread(target=self._fetch_calendar, args=(url,), daemon=True).start()
        for ev in self._events:
            key = (ev["id"], "soon")
            if ev["start"] - 5 * 60000 <= now * 1000 < ev["start"] - 4 * 60000 and key not in self._alerted:
                self._alerted.add(key)
                self._send({"t": "notice", "kind": "meeting", "id": ev["id"], "title": ev["title"],
                            "at": ev["start"], "has_link": ev["has_link"]})

    def _fetch_calendar(self, url):
        if not url.startswith("https://"):
            return
        try:
            import icalendar
            import recurring_ical_events
        except Exception:
            if not self._cal_warned:
                self._cal_warned = True
                self._log("ℹ️ الاجتماعات محتاجة: pip install icalendar recurring-ical-events")
            return
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                cal = icalendar.Calendar.from_ical(r.read())
            start = dt.datetime.now().astimezone()
            items = recurring_ical_events.of(cal).between(start - dt.timedelta(hours=1), start + dt.timedelta(days=1))
        except Exception as e:
            self._log(f"⚠️ الاجتماعات: {type(e).__name__}")      # never log the link itself
            return
        events, links = [], {}
        for i, ev in enumerate(items):
            s, e = ev.get("DTSTART"), ev.get("DTEND")
            if s is None or not isinstance(s.dt, dt.datetime):
                continue                                          # all-day events aren't meetings
            s_ms = int(s.dt.astimezone().timestamp() * 1000)
            e_ms = int(e.dt.astimezone().timestamp() * 1000) if e is not None and isinstance(e.dt, dt.datetime) else s_ms
            if e_ms < start.timestamp() * 1000:
                continue
            link = ""
            for field in ("LOCATION", "URL", "DESCRIPTION", "X-GOOGLE-CONFERENCE"):
                m = JOIN_RE.search(str(ev.get(field) or ""))
                if m:
                    link = m.group(0).rstrip(").,;")
                    break
            eid = f"m{i}_{s_ms}"
            if link:
                links[eid] = link
            events.append({"id": eid, "title": str(ev.get("SUMMARY") or "اجتماع")[:80],
                           "start": s_ms, "end": e_ms, "has_link": bool(link)})
        events.sort(key=lambda x: x["start"])
        self._events, self._links = events[:8], links
        self._send({"t": "meetings", "events": self._events})
