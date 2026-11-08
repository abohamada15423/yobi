# -*- coding: utf-8 -*-
"""
Smart Suggestions — يتتبع أنماط الاستخدام ويقترح تطبيقات.

مثال: لو بتفتح Spotify كل يوم الساعة 8، يقترح عليك يفتحه.
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta

from aliases import ARABIC_TO_CANONICAL, normalize_name

_USAGE_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "usage_patterns.json"
)

SUGGESTION_TRIGGERS = [
    "اقترح عليا", "اقترحلي", "اقترح لي", "اقترح", "اقتراح",
    "زهقان", "ملل", "مش عارف العب ايه", "مش عارف أعمل ايه",
    "مش عارف اعمل ايه", "ايه اللي ممكن اعمله", "إيه اللي ممكن أعمله",
    "ايه رأيك", "إيه رأيك", "suggest", "what should i play", "what should i do", "bored",
]

_VERB_PREFIX_RE = re.compile(r"^(?:افتح|شغل|اقفل|قفل|ابحث|دور|عايز|open|play|launch|start)\b", re.I)


def is_suggestion_request(text):
    text_l = (text or "").lower().strip()
    return any(t in text_l for t in SUGGESTION_TRIGGERS)


def _canonical_app_name(name):
    """Normalize app/game names and reject URLs or full spoken command sentences."""
    n = normalize_name(str(name or ""))
    if not n or len(n) < 2 or len(n) > 40:
        return None
    if n.startswith(("http://", "https://", "steam://", "com.epic", "c:", "d:", "e:")):
        return None
    if "%" in n or n.endswith((".", "?", "!")) or len(n.split()) > 4:
        return None
    if _VERB_PREFIX_RE.search(n):
        return None
    return ARABIC_TO_CANONICAL.get(n, n)


class SmartSuggestions:
    """Track usage patterns and surface timely suggestions."""

    MIN_DATA_POINTS = 3
    SCORE_THRESHOLD = 0.3
    CHECK_INTERVAL = 300
    SUGGESTION_COOLDOWN_MINUTES = 90

    def __init__(self, on_suggest):
        self._on_suggest = on_suggest
        self._log = self._load()
        self._last_suggested_at = {}
        self._timer = None
        self._start()

    # ── Public ──────────────────────────────────────────────────

    def get_interactive_suggestion(self, command="", games_list=None, apps_list=None):
        """Generate a personalized recommendation based on user intent, time, and history."""
        import random
        now = datetime.now()
        cmd_l = (command or "").lower()

        is_game = any(w in cmd_l for w in ["لعبة", "لعبه", "العب", "ألعب", "game", "play"])

        candidate_games = []
        if games_list:
            for g in games_list:
                canon = _canonical_app_name(g)
                if canon and canon not in candidate_games:
                    candidate_games.append(canon)

        # 1. Game suggestion requested
        if is_game and candidate_games:
            frequent_games = [g for g in candidate_games if g in self._log]
            if frequent_games:
                chosen = random.choice(frequent_games[:4])
                return f"إيه رأيك نلعب {chosen.title()}؟ 🎮 من ألعابك المفضلة! تحب أفتحهالك؟"
            chosen = random.choice(candidate_games)
            return f"إيه رأيك نجرب نلعب {chosen.title()}؟ 🎮 قول 'افتح {chosen}' لو جاهز!"

        # 2. Check for strong habit at this specific hour
        best_app, best_score = None, 0
        for app, entries in self._log.items():
            if not _canonical_app_name(app):
                continue
            hour_hits = sum(1 for e in entries if e.get("hour") == now.hour)
            if hour_hits > best_score:
                best_score = hour_hits
                best_app = app

        if best_app and best_score >= 2:
            return f"عادةً في الوقت ده بتفتح {best_app} — تحب أفتحهولك؟ 💡"

        # 3. Contextual time-of-day suggestions
        if 0 <= now.hour < 6:
            options = [
                "السهرة رايقة! 🌙 إيه رأيك نشغل مزيكا هادية على سبوتيفاي أو يوتيوب؟",
                "لو حابب تسهر، إيه رأيك نتفرج على حلقة من مسلسل أو فيلم حلو؟ 🍿",
            ]
            if candidate_games:
                options.append(f"إيه رأيك في جيم {random.choice(candidate_games).title()} في هدوء الليل؟ 🎮")
            return random.choice(options)
        elif 6 <= now.hour < 12:
            return "صباح الفل! ☕ إيه رأيك نشغل شوية مزيكا رايقة أو نفتح برامج الشغل والبرمجة؟"
        elif 12 <= now.hour < 18:
            return "وقت نص اليوم! تحب تفتح يوتيوب، ولا نشغل أغاني في الخلفية؟ 🎵"
        else:
            if candidate_games:
                return f"مساء الروقان! 🍿 إيه رأيك في فيلم حلو، أو نلعب جيم {random.choice(candidate_games).title()}؟"
            return "مساء الروقان! 🍿 إيه رأيك نشغل فيلم على نتفليكس أو شوية مزيكا؟"

    def record_usage(self, app_name):
        """Log that *app_name* was opened right now."""
        canon = _canonical_app_name(app_name)
        if not canon:
            return
        now = datetime.now()
        entry = {
            "hour": now.hour,
            "day": now.weekday(),
            "date": now.strftime("%Y-%m-%d %H:%M"),
        }
        self._log.setdefault(canon, []).append(entry)
        self._log[canon] = self._log[canon][-100:]
        self._save()

    def stop(self):
        if self._timer:
            self._timer.cancel()

    # ── Internals ───────────────────────────────────────────────

    def _load(self):
        if os.path.exists(_USAGE_LOG):
            try:
                with open(_USAGE_LOG, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                merged = {}
                for k, entries in (raw or {}).items():
                    canon = _canonical_app_name(k)
                    if not canon or not isinstance(entries, list):
                        continue
                    merged.setdefault(canon, []).extend(entries)
                return merged
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def _save(self):
        try:
            with open(_USAGE_LOG, "w", encoding="utf-8") as f:
                json.dump(self._log, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _check(self):
        now = datetime.now()
        best_app, best_score = None, 0

        for app, entries in self._log.items():
            if not _canonical_app_name(app) or len(entries) < self.MIN_DATA_POINTS:
                continue
            hour_hits = sum(1 for e in entries if e["hour"] == now.hour)
            day_hour_hits = sum(
                1 for e in entries
                if e["hour"] == now.hour and e["day"] == now.weekday()
            )
            score = (hour_hits + day_hour_hits * 2) / len(entries)
            if score > best_score and score > self.SCORE_THRESHOLD:
                best_score, best_app = score, app

        if best_app:
            last_time = self._last_suggested_at.get(best_app)
            if last_time and (now - last_time) < timedelta(minutes=self.SUGGESTION_COOLDOWN_MINUTES):
                return
            self._last_suggested_at[best_app] = now
            self._on_suggest(
                best_app,
                f"عادةً بتفتح {best_app} الوقت ده — تحب أفتحه؟ 💡",
            )

    def _start(self):
        def _loop():
            self._check()
            self._timer = threading.Timer(self.CHECK_INTERVAL, _loop)
            self._timer.daemon = True
            self._timer.start()

        self._timer = threading.Timer(60, _loop)
        self._timer.daemon = True
        self._timer.start()