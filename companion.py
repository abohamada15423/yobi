# -*- coding: utf-8 -*-
"""
Companion — يوبي بيهتم بيك ويسألك من نفسه
==========================================

بيسأل أسئلة خفيفة في أوقات مناسبة، وإنت ترد بزرار (أو بالكلام / الكتابة):

  • 💧 المياه    — "شربت مياه من شوية؟"  (لو قلت لسه، يفكرك كمان شوية)
  • ☕ الشاي     — "إيه رأيك تقوم تعمل شاي؟"  (العصر وبالليل)
  • 💪 الجيم     — "هتروح الجيم النهارده الساعة كام؟"  (ويفكرك قبلها بنص ساعة)
  • 🎵 المزيكا   — "مش عايز تسمع شوية أغاني؟"  (لو بقالك فترة ساكت)
  • 📺 المسلسل   — "بتتفرج على مسلسل إيه؟ وصلت الحلقة كام؟"  (وبيفتكر)
"""

import json
import os
import random
import re
import threading
import time
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(_HERE, "companion_data.json")

DEFAULTS = {
    "enabled": True,
    "quiet_hours": "01:00-10:00",
    "min_gap_min": 35,
    "max_per_day": 10,
    "min_idle_s": 90,
    "water_every_min": 30,
    "water_snooze_min": 10,
    "water_goal": 8,
    "water_gap_after_question_min": 5,
    "gap_after_water_min": 10,
    "water_backoff_after_ignores": 2,
    "away_min": 10,
    "after_game_min_session": 20,
    "mood_window": "13:00-22:00",
    "night_summary_window": "23:30-00:30",
    "sleep_nudge_window": "00:30-01:00",
    "tea_windows": ["16:30-18:30", "21:00-23:00"],
    "gym_ask_window": "11:00-17:30",
    "gym_options": [["٥ م", "17:00"], ["٧ م", "19:00"], ["٩ م", "21:00"]],
    "gym_remind_before_min": 30,
    "music_every_hours": 5,
    "music_window": "12:00-00:30",
    "series_every_hours": 20,
    "series_window": "18:00-00:30",
    "answer_timeout_s": 45,
    "tick_s": 30,
}

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_EP_RE = re.compile(r"(?:الحلقة|الحلقه|حلقة|حلقه|ep|episode|e)\s*[#:]?\s*(\d{1,4})", re.I)


def _minutes(hhmm):
    h, m = str(hhmm).strip().split(":")
    return int(h) * 60 + int(m)


def in_window(minute_of_day, window):
    try:
        a, b = window.split("-")
        a, b = _minutes(a), _minutes(b)
    except Exception:
        return False
    if a <= b:
        return a <= minute_of_day < b
    return minute_of_day >= a or minute_of_day < b


def _ar_num(n):
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def _fmt_time(hhmm):
    m = _minutes(hhmm)
    h, mm = divmod(m, 60)
    suffix = "م" if h >= 12 else "ص"
    h12 = h - 12 if h > 12 else (12 if h == 0 else h)
    return f"{_ar_num(h12)}{':' + _ar_num(f'{mm:02d}') if mm else ''} {suffix}"


def _norm(text):
    t = str(text or "").translate(_AR_DIGITS).strip()
    t = re.sub(r"[ًٌٍَُِّْـ]", "", t)
    return re.sub(r"\s+", " ", t)


class Companion:
    def __init__(self, ask, say, is_free=lambda: True, run_command=None,
                 config=None, data_path=DATA_PATH, clock=time.time, rng=None,
                 log=print, get_game=None, idle_s=None):
        self._ask = ask
        self._say = say
        self._is_free = is_free
        self._get_game = get_game or (lambda: None)
        self._idle_s = idle_s or (lambda: 0.0)
        self._game = None
        self._away_since = None
        self._run_command = run_command
        self.cfg = dict(DEFAULTS)
        self.cfg.update(config or {})
        self._path = data_path
        self._clock = clock
        self._rng = rng or random.Random()
        self._log = log
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self.data = self._load()
        self._roll_day()

    # ───────────────────────────────────────────────────────── storage
    def _blank(self):
        return {"day": "", "count_today": 0, "last_any": 0.0, "asked": {},
                "water_cups": 0, "water_snooze": 0.0, "tea_done": [],
                "gym": {"day": "", "time": None, "reminded": False},
                "series": {"name": None, "episode": None, "updated": 0.0},
                "pending_text": None, "enabled": None,
                "last_water_popup": 0.0, "water_ignored": 0, "awaiting": None,
                "after_game": None, "back_from_away": False,
                "mood": {"day": "", "value": None}, "night_done": []}

    def _load(self):
        data = self._blank()
        try:
            with open(self._path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if isinstance(data.get(k), dict) and isinstance(v, dict):
                        data[k].update(v)
                    else:
                        data[k] = v
        except Exception:
            pass
        return data

    def _save(self):
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except Exception as e:
            self._log(f"⚠️ companion: مقدرتش أحفظ ({e})")

    # ────────────────────────────────────────────────────────── helpers
    def _now(self):
        return datetime.fromtimestamp(self._clock())

    def _mod(self):
        n = self._now()
        return n.hour * 60 + n.minute

    def _roll_day(self):
        today = self._now().strftime("%Y-%m-%d")
        if self.data.get("day") != today:
            self.data.update(day=today, count_today=0, water_cups=0,
                             water_snooze=0.0, tea_done=[], water_ignored=0,
                             night_done=[], after_game=None)
            if self.data["gym"].get("day") != today:
                self.data["gym"] = {"day": "", "time": None, "reminded": False}
            self._save()

    @property
    def enabled(self):
        e = self.data.get("enabled")
        return bool(self.cfg.get("enabled", True) if e is None else e)

    def set_enabled(self, value):
        with self._lock:
            self.data["enabled"] = bool(value)
            self._save()
        return self.enabled

    def toggle(self):
        return self.set_enabled(not self.enabled)

    def _since(self, key):
        return self._clock() - float(self.data["asked"].get(key, 0.0))

    def _mark_asked(self, key):
        now = self._clock()
        self.data["asked"][key] = now
        if key == "water":
            self.data["last_water_popup"] = now
        else:
            self.data["last_any"] = now
            self.data["count_today"] = int(self.data.get("count_today", 0)) + 1
        self._save()

    def _pick(self, *options):
        return self._rng.choice(options)

    # ────────────────────────────────────────────────────── main loop
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="yobi-companion")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        if self._stop.wait(120):
            return
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                self._log(f"⚠️ companion: {e}")
            self._stop.wait(float(self.cfg["tick_s"]))

    def tick(self):
        with self._lock:
            self._roll_day()
            if not self.enabled:
                return None
            mod = self._mod()
            now = self._clock()
            self._track_game(now)
            self._expire_awaiting(now)
            if in_window(mod, self.cfg["quiet_hours"]):
                # Don't let an after_game flag from late night linger until 10 AM
                self.data["after_game"] = None
                return None

            if self._gym_reminder_due(mod):
                self.data["gym"]["reminded"] = True
                self._save()
                self._say(self._pick("فاضل نص ساعة على الجيم 💪 جهّز شنطتك",
                                     "يلا قرّب ميعاد الجيم 💪 متنساش المياه"))
                return "gym_reminder" 
            if self._track_away(now):
                return None

            if not self._safe_is_free():
                return None

            ag = self.data.get("after_game")
            if ag:
                self.data["after_game"] = None
                self._ask_water(after_game=ag)
                return "water"

            if self.data.get("back_from_away"):
                self.data["back_from_away"] = False
                self._save()
                if self._since("water") >= self._water_interval() / 2:
                    self._ask_water(back=True)
                    return "water"

            snooze = float(self.data.get("water_snooze") or 0.0)
            if snooze and now >= snooze:
                self.data["water_snooze"] = 0.0
                self._ask_water(again=True)
                return "water"

            night = self._night_message(mod)
            if night:
                return night

            since_q = now - float(self.data.get("last_any", 0.0))
            since_w = now - float(self.data.get("last_water_popup", 0.0))
            due = self._due(mod)
            budget_ok = int(self.data.get("count_today", 0)) < int(self.cfg["max_per_day"])
            gap = self.cfg["min_gap_min"] * (1.5 if self._tired() else 1)
            others_ok = (budget_ok and since_q >= gap * 60
                         and since_w >= self.cfg["gap_after_water_min"] * 60)

            if "gym" in due and others_ok:
                self._ask_gym()
                return "gym"

            if ("water" in due and not self.data.get("water_snooze")
                    and since_q >= self.cfg["water_gap_after_question_min"] * 60):
                self._ask_water()
                return "water"

            rest = [k for k in due if k not in ("water", "gym")]
            if rest and others_ok:
                kind = "mood" if "mood" in rest else self._rng.choice(rest)
                getattr(self, f"_ask_{kind}")()
                return kind
            return None

    # ───────────────────────────────────────── v7.3: context tracking
    def _track_game(self, now):
        try:
            g = self._get_game()
        except Exception:
            g = None
        if g and not self._game:
            self._game = (str(g), now)
        elif not g and self._game:
            name, start = self._game
            self._game = None
            minutes = int((now - start) / 60)
            if minutes >= int(self.cfg["after_game_min_session"]):
                self.data["after_game"] = {"name": name, "minutes": minutes}
                self._save()
        elif g and self._game and self._game[0] != str(g):
            self._game = (str(g), self._game[1])

    def _track_away(self, now):
        try:
            idle = float(self._idle_s() or 0.0)
        except Exception:
            idle = 0.0
        if idle >= self.cfg["away_min"] * 60:
            if self._away_since is None:
                self._away_since = now - idle
            return True
        if self._away_since is not None:
            self._away_since = None
            self.data["back_from_away"] = True
            self._save()
        return False

    def _expire_awaiting(self, now):
        aw = self.data.get("awaiting")
        if not aw or now - float(aw.get("ts", 0)) < self.cfg["answer_timeout_s"] + 5:
            return
        self.data["awaiting"] = None
        if aw.get("kind") == "water":
            self.data["water_ignored"] = int(self.data.get("water_ignored", 0)) + 1
        self._save()

    def _water_interval(self):
        base = float(self.cfg["water_every_min"]) * 60
        if int(self.data.get("water_ignored", 0)) >= int(self.cfg["water_backoff_after_ignores"]):
            return base * 2
        return base

    def _tired(self):
        m = self.data.get("mood") or {}
        return m.get("day") == self.data["day"] and m.get("value") in ("tired", "stressed")

    def _night_message(self, mod):
        done = self.data.setdefault("night_done", [])
        if "summary" not in done and in_window(mod, self.cfg["night_summary_window"]):
            done.append("summary")
            self._save()
            n, goal = int(self.data.get("water_cups", 0)), int(self.cfg["water_goal"])
            if n >= goal:
                msg = f"النهارده شربت {_ar_num(n)} كوبايات مياه 💧 عاش، كمّلت الهدف 🎉"
            elif n:
                msg = f"النهارده شربت {_ar_num(n)} من {_ar_num(goal)} كوبايات 💧 بكرة نكمّلهم"
            else:
                msg = "مقولتليش إنك شربت مياه خالص النهارده 💧 اشرب كوباية قبل ما تنام"
            self._say(msg)
            return "night_summary"
        if "sleep" not in done and in_window(mod, self.cfg["sleep_nudge_window"]):
            done.append("sleep")
            self._save()
            if self._game:
                return None
            self._say(self._pick("الوقت اتأخر 😴 متسهرش كتير، بكرة عايزك فايق",
                                 "عدّت ١٢ ونص 🌙 لو خلّصت اللي في إيدك نام بدري شوية"))
            return "sleep_nudge"
        return None

    def _safe_is_free(self):
        try:
            return bool(self._is_free())
        except Exception:
            return False

    def _due(self, mod):
        c, due = self.cfg, []
        if (in_window(mod, c["gym_ask_window"]) and self.data["gym"].get("day") != self.data["day"]
                and self._since("gym") > 6 * 3600):
            due.append("gym")
        if self._since("water") >= self._water_interval():
            due.append("water")
        m = self.data.get("mood") or {}
        if in_window(mod, c["mood_window"]) and m.get("day") != self.data["day"]:
            due.append("mood")
        for w in c["tea_windows"]:
            if in_window(mod, w) and w not in self.data["tea_done"]:
                due.append("tea")
                break
        if in_window(mod, c["music_window"]) and self._since("music") >= c["music_every_hours"] * 3600:
            due.append("music")
        if in_window(mod, c["series_window"]) and self._since("series") >= c["series_every_hours"] * 3600:
            due.append("series")
        if self._tired():
            due = [k for k in due if k in ("gym", "water")]
        return due

    def _gym_reminder_due(self, mod):
        g = self.data["gym"]
        if g.get("day") != self.data["day"] or not g.get("time") or g.get("reminded"):
            return False
        t = _minutes(g["time"])
        return t - self.cfg["gym_remind_before_min"] <= mod < t + 30

    def _ask_q(self, question, options, handler, kind=None):
        self.data["awaiting"] = {"kind": kind, "ts": self._clock()}

        def _wrapped(value):
            with self._lock:
                self.data["awaiting"] = None
                if kind == "water":
                    self.data["water_ignored"] = 0
            handler(value)
        self._ask(question, options, _wrapped, self.cfg["answer_timeout_s"])

    # ───────────────────────────────────────────────────── questions
    def _ask_water(self, again=False, after_game=None, back=False):
        self._mark_asked("water")
        n, goal = int(self.data.get("water_cups", 0)), int(self.cfg["water_goal"])
        if again:
            q = "فاكر الكوباية؟ شربت ولا لسه؟ 💧"
        elif after_game:
            q = (f"خلصت {after_game['name']}؟ لعبت {_ar_num(after_game['minutes'])} دقيقة 🎮 "
                 f"قوم اشرب كوباية مياه وفرّد ضهرك 💧")
        elif back:
            q = "أهلا رجعت 👋 اشرب كوباية مياه؟ 💧"
        elif n == 0 and self._mod() < 14 * 60:
            q = "صباح الفل ☀️ ابدأ يومك بكوباية مياه، شربت؟"
        elif n < self._expected_cups() - 2:
            q = f"لسه {_ar_num(n)} كوبايات بس النهارده من {_ar_num(goal)} 💧 يلا كوباية؟"
        else:
            q = self._pick("شربت مياه من شوية؟ 💧",
                           "فاكر تشرب مياه؟ 💧 شربت من شوية؟",
                           "كوباية مياه دلوقتي هتفرق معاك 💧 شربت؟")
        self._ask_q(q, [("شربت ✅", "yes"), ("لسه", "no")], self._on_water, kind="water")

    def _expected_cups(self):
        try:
            wake = _minutes(self.cfg["quiet_hours"].split("-")[1])
            sleep = _minutes(self.cfg["quiet_hours"].split("-")[0])
        except Exception:
            wake, sleep = 600, 60
        span = (sleep - wake) % 1440 or 1440
        elapsed = (self._mod() - wake) % 1440
        return int(self.cfg["water_goal"]) * min(1.0, elapsed / span)

    def _on_water(self, value):
        with self._lock:
            if value == "yes":
                self._say(self._drank())
            elif value == "no":
                snooze = min(float(self.cfg["water_snooze_min"]),
                             float(self.cfg["water_every_min"]) / 2)
                self.data["water_snooze"] = self._clock() + snooze * 60
                self._save()
                self._say(f"طب قوم اشرب كوباية دلوقتي 💧 هسألك تاني كمان {_ar_num(int(snooze))} دقايق")

    def _drank(self):
        with self._lock:
            self.data["water_cups"] = int(self.data.get("water_cups", 0)) + 1
            self.data["asked"]["water"] = self._clock()
            self.data["water_snooze"] = 0.0
            self.data["water_ignored"] = 0
            n, goal = self.data["water_cups"], int(self.cfg["water_goal"])
            self._save()
        if n == goal:
            return f"🎉 كمّلت الـ {_ar_num(goal)} كوبايات النهارده! عاش يا بطل 💧"
        if n < goal:
            unit = "كوباية" if n == 1 else "كوبايات"
            return f"عاش 💧 كده {_ar_num(n)} {unit} من {_ar_num(goal)} النهارده"
        return f"عاش 💧 {_ar_num(n)} كوبايات النهارده، فوق الهدف كمان"

    _MOOD_REPLIES = {
        "great": ("يا رب دايمًا 💙", "حلو أوي، كمّل كده 😄"),
        "ok": ("ماشي 💙 لو احتجت حاجة أنا هنا", "تمام، يوم هادي برضه حلو 👌"),
        "tired": ("خد بريك ١٠ دقايق بعيد عن الشاشة 😮‍💨 وهقلل الأسئلة النهارده، "
                  "بس هفضل أفكرك بالمياه 💧",),
        "stressed": ("خد نفس عميق كده 🫁 وقوم اتمشى دقيقتين. هسيبك تركز النهارده "
                     "ومش هسألك غير على المياه 💙",),
    }

    def _ask_mood(self):
        self._mark_asked("mood")
        self.data["mood"] = {"day": self.data["day"], "value": None}
        self._save()
        q = self._pick("عامل إيه النهارده؟ 💙", "طمّني عليك، يومك ماشي إزاي؟ 💙")
        self._ask_q(q, [("تمام 😄", "great"), ("عادي", "ok"),
                        ("تعبان 😮‍💨", "tired"), ("مضغوط 😣", "stressed")],
                    self._on_mood, kind="mood")

    def _on_mood(self, value):
        if value not in self._MOOD_REPLIES:
            return
        with self._lock:
            self.data["mood"] = {"day": self.data["day"], "value": value}
            self._save()
        self._say(self._pick(*self._MOOD_REPLIES[value]))

    def _ask_tea(self):
        mod = self._mod()
        for w in self.cfg["tea_windows"]:
            if in_window(mod, w):
                self.data["tea_done"].append(w)
                break
        self._mark_asked("tea")
        q = self._pick("إيه رأيك تقوم تعمل شاي؟ ☕",
                       "وقت شاي ولا إيه؟ ☕",
                       "بريك صغير وكوباية شاي؟ ☕")
        self._ask_q(q, [("يلا ☕", "yes"), ("مش دلوقتي", "no")], self._on_tea)

    def _on_tea(self, value):
        if value == "yes":
            self._say(self._pick("استمتع ☕ وفرّد ضهرك شوية", "عاش ☕ خد ٥ دقايق راحة"))
        elif value == "no":
            self._say("ماشي، براحتك 👌")

    def _ask_gym(self):
        self._mark_asked("gym")
        opts = [(str(lbl), str(val)) for lbl, val in self.cfg["gym_options"][:3]]
        opts.append(("مش رايح", "skip"))
        self._ask_q(self._pick("هتروح الجيم النهارده الساعة كام؟ 💪",
                               "الجيم النهارده الساعة كام؟ 💪"), opts, self._on_gym)

    def _on_gym(self, value):
        with self._lock:
            if value == "skip":
                self.data["gym"] = {"day": self.data["day"], "time": None, "reminded": True}
                self._save()
                self._say("ماشي، يوم راحة 😴 بس متنساش تتحرك شوية")
            elif value and re.match(r"^\d{1,2}:\d{2}$", str(value)):
                self.set_gym_time(value)

    def set_gym_time(self, hhmm):
        with self._lock:
            self.data["gym"] = {"day": self.data["day"], "time": hhmm, "reminded": False}
            self.data["asked"]["gym"] = self._clock()
            self._save()
        before = _minutes(hhmm) - self.cfg["gym_remind_before_min"]
        before = f"{before // 60:02d}:{before % 60:02d}"
        msg = f"تمام 💪 الجيم الساعة {_fmt_time(hhmm)}، وهفكرك الساعة {_fmt_time(before)}"
        self._say(msg)
        return msg

    def _ask_music(self):
        self._mark_asked("music")
        q = self._pick("مش عايز تسمع شوية أغاني؟ 🎵", "نشغّل شوية مزيكا؟ 🎵")
        self._ask_q(q, [("شغّل 🎵", "yes"), ("لا", "no")], self._on_music)

    def _on_music(self, value):
        if value == "yes":
            if self._run_command:
                try:
                    self._run_command("شغل اغاني")
                    return
                except Exception as e:
                    self._log(f"⚠️ companion music: {e}")
            self._say("قول «يا يوبي شغّل أغاني» 🎵")
        elif value == "no":
            self._say("تمام 👌")

    def _ask_series(self):
        self._mark_asked("series")
        s = self.data["series"]
        if s.get("name"):
            ep = s.get("episode")
            if ep:
                q = f"لسه بتتفرج على {s['name']}؟ وصلت الحلقة كام؟ 📺"
                opts = [(f"الحلقة {_ar_num(ep + 1)}", "next"), (f"لسه {_ar_num(ep)}", "same"),
                        ("خلّصته ✅", "done"), ("حاجة تانية", "other")]
            else:
                q = f"لسه بتتفرج على {s['name']}؟ 📺"
                opts = [("أيوه", "same"), ("خلّصته ✅", "done"), ("حاجة تانية", "other")]
        else:
            q = "بتتفرج على مسلسل إيه دلوقتي؟ 📺"
            opts = [("هقولك", "other"), ("مش بتفرج على حاجة", "none")]
        self._ask_q(q, opts, self._on_series)

    def _on_series(self, value):
        with self._lock:
            s = self.data["series"]
            if value == "next":
                s["episode"] = int(s.get("episode") or 0) + 1
                s["updated"] = self._clock()
                self._save()
                self._say(f"حلو! {s['name']} الحلقة {_ar_num(s['episode'])} 🍿")
            elif value == "same":
                self._say("ماشي، استمتع 🍿")
            elif value == "done":
                name = s.get("name") or "المسلسل"
                self.data["series"] = {"name": None, "episode": None, "updated": self._clock()}
                self._save()
                self._say(f"مبروك خلّصت {name} 🎉 ابقى قولّي هتبدأ إيه بعده")
            elif value == "other":
                self.data["pending_text"] = {"kind": "series", "expires": self._clock() + 240}
                self._save()
                self._say("اكتب اسمه في المحادثة، أو قول «يا يوبي» واسمه 👂 "
                          "ولو تحب قول رقم الحلقة كمان")
            elif value == "none":
                self._say("تمام 👌 لو بدأت حاجة قولّي")

    # ───────────────────────────────────────────── free text answers
    def has_pending_text(self):
        p = self.data.get("pending_text")
        return bool(p) and self._clock() < float(p.get("expires", 0))

    def set_series(self, name, episode=None):
        name = (name or "").strip(" .،,!؟?")
        with self._lock:
            s = self.data["series"]
            if name:
                if name != s.get("name"):
                    s["episode"] = None
                s["name"] = name
            if episode is not None:
                s["episode"] = int(episode)
            s["updated"] = self._clock()
            self.data["asked"]["series"] = self._clock()
            self.data["pending_text"] = None
            self._save()
            s = dict(s)
        if s.get("name") and s.get("episode"):
            return f"تمام 📺 {s['name']} الحلقة {_ar_num(s['episode'])}، هفتكرها"
        if s.get("name"):
            return f"تمام 📺 {s['name']}، هفتكره"
        return None

    def handle_text(self, text):
        """لو الكلام ده رد على سؤال من يوبي أو معلومة عنك، بيرجّع الرد. غير كده None."""
        t = _norm(text)
        if not t:
            return None
        low = t.lower()

        if self.has_pending_text():
            kind = self.data["pending_text"].get("kind")
            if kind == "series":
                if any(w in low for w in ("مش بتفرج", "ولا حاجة", "مفيش", "الغي", "إلغاء")):
                    with self._lock:
                        self.data["pending_text"] = None
                        self._save()
                    return "تمام 👌"
                ep = self._episode(t)
                name = self._series_name(t)
                if name or ep:
                    return self.set_series(name, ep)

        m = re.search(r"(?:بتفرج|بتفرّج|بتابع|بشوف)\s+(?:على\s+|علي\s+)?مسلسل\s+(.+)", t) or \
            re.search(r"(?:بتفرج|بتفرّج)\s+(?:على|علي)\s+(.+)", t)
        if m:
            ep = self._episode(m.group(1))
            name = self._series_name(m.group(1))
            if name:
                return self.set_series(name, ep)

        if self.data["series"].get("name") and re.search(r"(?:وصلت|انا في|أنا في|خلصت)\s*(?:ال)?حلق", t):
            ep = self._episode(t)
            if ep:
                return self.set_series(None, ep)

        if re.search(r"(?:شربت|شارب|[أاإ]شرب)\s+(?:كوباية\s+|كوبايه\s+)?(?:مياه|مية|ميه|ميا|ماء|مايه|كوباية|كوبايه)", t):
            return self._drank()

        if re.search(r"(?:كام|قد ايه|قد إيه)\s+(?:كوباية|كوبايه|مياه|مية)", t) or \
                re.search(r"شربت\s+كام", t):
            n, goal = int(self.data.get("water_cups", 0)), int(self.cfg["water_goal"])
            return f"شربت {_ar_num(n)} من {_ar_num(goal)} كوبايات النهارده 💧"

        m = re.search(r"^(?:انا|أنا)\s+(?:حاسس\s+(?:اني|إني)\s+)?"
                      r"(تعبان|تعبانه|مرهق|مضغوط|متوتر|مخنوق|زهقان|مبسوط|فرحان|كويس|تمام)", t)
        if m:
            w = m.group(1)
            value = ("tired" if w in ("تعبان", "تعبانه", "مرهق") else
                     "stressed" if w in ("مضغوط", "متوتر", "مخنوق", "زهقان") else "great")
            with self._lock:
                self.data["mood"] = {"day": self.data["day"], "value": value}
                self.data["asked"]["mood"] = self._clock()
                self._save()
            return self._pick(*self._MOOD_REPLIES[value])

        if re.search(r"(?:مش\s+(?:رايح|هروح|نازل)\s+(?:ال)?جيم|(?:النهارده|النهاردة|اليوم)\s+راح[ةه]\s+من\s+(?:ال)?جيم|اجاز[ةه]\s+من\s+(?:ال)?جيم)", t):
            with self._lock:
                self.data["gym"] = {"day": self.data["day"], "time": None, "reminded": True}
                self.data["asked"]["gym"] = self._clock()
                self._save()
            return "ماشي، يوم راحة من الجيم 💪 متنساش تتحرك شوية وتشرب مياه 💧"

        m = re.search(r"(?:هروح|رايح|هنزل)\s+(?:ال)?جيم\s+(?:ال)?(?:ساعة|ساعه)\s+(\d{1,2})(?::(\d{2}))?\s*(الصبح|صباحا|ص|بالليل|م|العصر|المغرب)?", t)
        if m:
            h = int(m.group(1))
            mi = int(m.group(2) or 0)
            part = m.group(3) or ""
            if part not in ("الصبح", "صباحا", "ص") and 1 <= h <= 11:
                h += 12
            if 0 <= h <= 23:
                return self.set_gym_time(f"{h:02d}:{mi:02d}")
        return None

    @staticmethod
    def _episode(text):
        m = _EP_RE.search(_norm(text))
        return int(m.group(1)) if m else None

    @staticmethod
    def _series_name(text):
        t = _norm(text)
        t = _EP_RE.sub(" ", t)
        t = re.sub(r"^(?:يا\s*يوبي[،,]?\s*)", "", t)
        t = re.sub(r"\b(?:انا|أنا|بتفرج|بتفرّج|بتابع|بشوف|على|علي|مسلسل|اسمه|اسمها|في|من|وصلت|ودلوقتي|دلوقتي)\b", " ", t)
        t = re.sub(r"[\s،,.!؟?]+", " ", t).strip()
        return t if len(t) >= 2 else None