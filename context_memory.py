# -*- coding: utf-8 -*-
"""
Enhanced Context Memory v2 — ذاكرة يوبي الذكية.

يحل محل context_memory.py القديم (68 سطر) بنسخة أقوى (~350 سطر):

  • Entity Tracking — يفتكر آخر app/game/file/website اتذكر
  • Multi-turn Context — سياق 10 أوامر بدل 3
  • Mood Detection — يحس إنك زهقان/مستعجل من أسلوب الكلام
  • Session Summary — يلخص الجلسة عند الإغلاق
  • Time-aware — يعرف الوقت ويقترح بناءً عليه
  • Topic Clustering — يعرف إنك في "وضع شغل" أو "وضع لعب"
  • Pronoun Resolution — يفهم "افتحه تاني" / "اقفله"

Usage:
    ctx = ContextMemory()
    ctx.push("user", "افتح كروم")
    ctx.set_entity("app", "chrome", "browser")
    ctx.push("assistant", "تم فتح كروم ✅")

    # Later...
    resolved = ctx.resolve_pronoun("اقفله")  # → "chrome"
    mood = ctx.detect_mood()                  # → "neutral"
    topic = ctx.current_topic()               # → "browsing"
"""

import json
import os
import re
import time
from collections import deque
from datetime import datetime

try:
    from yobi_logger import get_logger
    log = get_logger("context")
except ImportError:
    import logging
    log = logging.getLogger("context")

try:
    from config import cfg
    _CONTEXT_DEPTH = cfg.get("memory.context_depth", 10)
    _SESSION_SUMMARY = cfg.get("memory.session_summary_enabled", True)
    _ENTITY_TRACKING = cfg.get("memory.entity_tracking_enabled", True)
    _MOOD_DETECTION = cfg.get("memory.mood_detection_enabled", True)
    _TOPIC_CLUSTERING = cfg.get("memory.topic_clustering_enabled", True)
    _MAX_SESSION = cfg.get("memory.max_session_history", 200)
    _SUMMARY_PATH = cfg.get("memory.summary_save_path", "session_summaries.json")
except ImportError:
    _CONTEXT_DEPTH = 10
    _SESSION_SUMMARY = True
    _ENTITY_TRACKING = True
    _MOOD_DETECTION = True
    _TOPIC_CLUSTERING = True
    _MAX_SESSION = 200
    _SUMMARY_PATH = "session_summaries.json"

_HERE = os.path.dirname(os.path.abspath(__file__))


# ============================================================================
# Entity types for tracking
# ============================================================================
ENTITY_TYPES = {
    "app": "تطبيق",
    "game": "لعبة",
    "file": "ملف",
    "folder": "مجلد",
    "website": "موقع",
    "song": "أغنية",
    "person": "شخص",
    "setting": "إعداد",
}


# ============================================================================
# Mood indicators
# ============================================================================
MOOD_PATTERNS = {
    "bored": [
        "زهقان", "ملل", "زهق", "مش عارف اعمل ايه",
        "مش عارف أعمل إيه", "bored", "boring",
    ],
    "frustrated": [
        "مش شغال", "مش عايز", "ليه مش", "غلط", "خطأ",
        "مش فاهم", "تعبت", "frustrated",
    ],
    "happy": [
        "تمام", "حلو", "ممتاز", "عظيم", "جميل", "رائع",
        "شكرا", "شكراً", "thanks", "great", "awesome",
    ],
    "rushed": [
        "بسرعة", "بسرعه", "يالا", "quick", "fast", "hurry",
        "عاوز", "عايز دلوقتي",
    ],
    "curious": [
        "ازاي", "إزاي", "ليه", "ليش", "إيه", "ايه", "مين",
        "فين", "how", "why", "what",
    ],
    "tired": [
        "تعبان", "نعسان", "مش قادر", "خلاص", "كفاية",
        "tired", "sleepy",
    ],
}


# ============================================================================
# Topic clusters
# ============================================================================
TOPIC_KEYWORDS = {
    "gaming": [
        "لعبة", "لعبه", "العب", "ألعب", "game", "games", "steam",
        "valorant", "fortnite", "gta", "minecraft", "epic",
    ],
    "work": [
        "شغل", "ملف", "فولدر", "مشروع", "كود", "برمجة",
        "excel", "word", "powerpoint", "vscode", "code",
    ],
    "entertainment": [
        "فيلم", "مسلسل", "أغنية", "اغنية", "مزيكا", "يوتيوب",
        "نتفليكس", "سبوتيفاي", "netflix", "spotify", "youtube",
        "movie", "music",
    ],
    "browsing": [
        "كروم", "متصفح", "موقع", "سيرش", "جوجل", "chrome",
        "browser", "search", "google", "website",
    ],
    "system": [
        "صوت", "سطوع", "اطفي", "ريستارت", "سكرين شوت",
        "volume", "brightness", "shutdown", "restart",
    ],
    "social": [
        "واتساب", "تليجرام", "فيسبوك", "تويتر", "ديسكورد",
        "whatsapp", "telegram", "facebook", "twitter", "discord",
    ],
}


# ============================================================================
# Context Memory
# ============================================================================
class ContextMemory:
    """Enhanced context memory with entity tracking, mood detection,
    topic clustering, and session summaries."""

    def __init__(self):
        # Conversation history (role, text, timestamp)
        self._history = deque(maxlen=_MAX_SESSION)

        # Recent context window for LLM
        self._recent = deque(maxlen=_CONTEXT_DEPTH)

        # Entity tracking: type -> {name, category, timestamp, count}
        self._entities = {}

        # Last entity mentioned (for pronoun resolution)
        self._last_entity = None
        self._last_entity_type = None

        # Session stats
        self._session_start = time.time()
        self._command_count = 0
        self._topic_counts = {}

        # Mood tracking
        self._mood_history = deque(maxlen=20)
        self._current_mood = "neutral"

        # agent.py compatibility
        self.in_conversation = False
        self._last_action = None   # (intent, target)

        log.debug("ContextMemory v2 initialized")

    # ── agent.py compatibility (v1 API) ─────────────────────────
    # agent.py calls record() and resolve_reference(), which the v2 rewrite
    # dropped → every normal command crashed with AttributeError and got
    # swallowed by the main loop. These restore the old contract.

    def record(self, intent, target, result=None):
        """Remember the last action so 'اقفله' / 'افتحه تاني' work."""
        if not target:
            return
        self._last_action = (intent, str(target))
        self._last_entity = str(target)
        self._last_entity_type = "app"
        self.push("assistant", f"{intent} {target}: {result or ''}".strip())

    def resolve_reference(self, text):
        """Returns (intent, target) for pronoun commands, else (None, None)."""
        target = self.resolve_pronoun(text)
        if not target:
            return None, None
        t = text.lower()
        if any(w in t for w in ("اقفل", "قفل", "انهي", "close", "kill")):
            return "close", target
        return "open", target

    # ── Core API (backward-compatible) ──────────────────────────

    def push(self, role, text):
        """Add a message to context. role = 'user' | 'assistant'."""
        entry = {
            "role": role,
            "text": text,
            "timestamp": time.time(),
            "time_str": datetime.now().strftime("%H:%M:%S"),
        }
        self._history.append(entry)
        self._recent.append(entry)

        if role == "user":
            self._command_count += 1
            # Auto-detect entities
            if _ENTITY_TRACKING:
                self._auto_detect_entities(text)
            # Mood detection
            if _MOOD_DETECTION:
                self._update_mood(text)
            # Topic tracking
            if _TOPIC_CLUSTERING:
                self._update_topic(text)

    def get_recent(self, n=None):
        """Return last n context entries (default: context_depth)."""
        if n is None:
            n = _CONTEXT_DEPTH
        return list(self._recent)[-n:]

    def get_context_for_llm(self):
        """Return formatted context string for LLM system prompt."""
        if not self._recent:
            return ""

        lines = []
        for entry in self._recent:
            role_ar = "المستخدم" if entry["role"] == "user" else "يوبي"
            lines.append(f"[{entry['time_str']}] {role_ar}: {entry['text']}")

        context = "سياق المحادثة الأخيرة:\n" + "\n".join(lines)

        # Add entity context
        if self._last_entity:
            context += (
                f"\n\nآخر حاجة اتذكرت: {self._last_entity} "
                f"(نوع: {ENTITY_TYPES.get(self._last_entity_type, 'غير معروف')})"
            )

        # Add mood context
        if self._current_mood != "neutral":
            mood_ar = {
                "bored": "زهقان",
                "frustrated": "محبط",
                "happy": "مبسوط",
                "rushed": "مستعجل",
                "curious": "فضولي",
                "tired": "تعبان",
            }.get(self._current_mood, "")
            if mood_ar:
                context += f"\nملحوظة: المستخدم يبدو {mood_ar}"

        # Add topic context
        current = self.current_topic()
        if current:
            topic_ar = {
                "gaming": "لعب ألعاب",
                "work": "شغل",
                "entertainment": "ترفيه",
                "browsing": "تصفح",
                "system": "إعدادات النظام",
                "social": "سوشيال ميديا",
            }.get(current, current)
            context += f"\nالمستخدم حالياً في وضع: {topic_ar}"

        return context

    def clear(self):
        """Clear all context."""
        self._recent.clear()
        self._entities.clear()
        self._last_entity = None
        self._last_entity_type = None

    # ── Entity Tracking ────────────────────────────────────────

    def set_entity(self, entity_type, name, category=""):
        """Register an entity that was just mentioned/used."""
        self._entities[entity_type] = {
            "name": name,
            "category": category,
            "timestamp": time.time(),
            "count": self._entities.get(entity_type, {}).get("count", 0) + 1,
        }
        self._last_entity = name
        self._last_entity_type = entity_type
        log.debug(f"Entity tracked: {entity_type}={name} ({category})")

    def get_entity(self, entity_type):
        """Get the most recent entity of a given type."""
        entry = self._entities.get(entity_type)
        return entry["name"] if entry else None

    def get_last_entity(self):
        """Get the very last entity mentioned, regardless of type."""
        return self._last_entity, self._last_entity_type

    def _auto_detect_entities(self, text):
        """Try to detect entities from user text automatically."""
        text_l = text.lower().strip()

        # App/game detection — look for "افتح X" / "شغل X"
        m = re.search(
            r'(?:افتح|شغل|فتح|شغّل|open|launch|run)\s+(.+?)(?:\s+بعد|\s*$)',
            text_l
        )
        if m:
            target = m.group(1).strip()
            if len(target) > 1:
                # Guess type
                game_words = ["لعبة", "لعبه", "game"]
                if any(w in text_l for w in game_words):
                    self.set_entity("game", target, "game")
                else:
                    self.set_entity("app", target, "app")

        # File detection
        m = re.search(
            r'(?:ملف|فايل|file|فولدر|folder)\s+(.+?)(?:\s|$)',
            text_l
        )
        if m:
            self.set_entity("file", m.group(1).strip(), "file")

        # Website detection
        m = re.search(
            r'(?:موقع|site|website)\s+(.+?)(?:\s|$)',
            text_l
        )
        if m:
            self.set_entity("website", m.group(1).strip(), "website")

    # ── Pronoun Resolution ─────────────────────────────────────

    def resolve_pronoun(self, text):
        """Resolve pronouns like 'اقفله' / 'افتحه تاني' / 'شغله'.

        Returns the resolved entity name, or None.
        """
        text_l = text.lower().strip()

        # Arabic pronoun suffixes (word-bounded so 'تنزلها' won't match 'نزلها')
        pronoun_patterns = [
            r'(?:^|\s)(?:افتحه|شغله|اقفله|قفله|انهيه|نزله|سطبه)(?:\s+تاني|\s+مرة تاني)?(?:\s|$)',
            r'(?:^|\s)(?:افتحها|شغلها|اقفلها|قفلها|انهيها|نزلها|سطبها)(?:\s+تاني|\s+مرة تاني)?(?:\s|$)',
            r'(?:^|\s)(?:open|close|run|launch)\s+(?:it|that)(?:\s+again)?(?:\s|$)',
        ]

        for pattern in pronoun_patterns:
            if re.search(pattern, text_l):
                if self._last_entity:
                    log.info(
                        f"🔗 Pronoun resolved: '{text}' → '{self._last_entity}'"
                    )
                    return self._last_entity

        return None

    # ── Mood Detection ─────────────────────────────────────────

    def _update_mood(self, text):
        """Detect user mood from their message."""
        text_l = text.lower()
        detected = "neutral"

        for mood, patterns in MOOD_PATTERNS.items():
            if any(p in text_l for p in patterns):
                detected = mood
                break

        self._mood_history.append(detected)

        # Current mood is the most frequent recent mood
        if self._mood_history:
            from collections import Counter
            counts = Counter(self._mood_history)
            self._current_mood = counts.most_common(1)[0][0]

    def detect_mood(self):
        """Return the current detected mood."""
        return self._current_mood

    def get_mood_response_hint(self):
        """Return a hint for the LLM on how to respond based on mood."""
        hints = {
            "bored": "المستخدم زهقان — اقترح حاجات ممتعة أو ألعاب",
            "frustrated": "المستخدم محبط — كن صبور ومساعد وواضح",
            "happy": "المستخدم مبسوط — كن إيجابي ومرح",
            "rushed": "المستخدم مستعجل — رد بسرعة وباختصار",
            "curious": "المستخدم فضولي — أعطي تفاصيل ومعلومات",
            "tired": "المستخدم تعبان — اقترح راحة أو حاجات هادية",
            "neutral": "",
        }
        return hints.get(self._current_mood, "")

    # ── Topic Clustering ───────────────────────────────────────

    def _update_topic(self, text):
        """Track what topic/category the user is focused on."""
        text_l = text.lower()
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(k in text_l for k in keywords):
                self._topic_counts[topic] = self._topic_counts.get(topic, 0) + 1

    def current_topic(self):
        """Return the dominant topic in the current session."""
        if not self._topic_counts:
            return None
        return max(self._topic_counts, key=self._topic_counts.get)

    def topic_distribution(self):
        """Return topic distribution as percentages."""
        total = sum(self._topic_counts.values()) or 1
        return {
            topic: round(count / total * 100, 1)
            for topic, count in self._topic_counts.items()
        }

    # ── Time Awareness ─────────────────────────────────────────

    @staticmethod
    def time_context():
        """Return time-aware context string."""
        now = datetime.now()
        hour = now.hour

        if 0 <= hour < 6:
            period = "سهران بالليل 🌙"
            suggestion = "حاجة هادية أو ألعاب"
        elif 6 <= hour < 12:
            period = "الصبح ☀️"
            suggestion = "شغل أو موسيقى رايقة"
        elif 12 <= hour < 14:
            period = "الضهر 🌤️"
            suggestion = "بريك أو أكل"
        elif 14 <= hour < 18:
            period = "بعد الضهر 🌅"
            suggestion = "شغل أو ترفيه"
        elif 18 <= hour < 22:
            period = "بالليل 🌃"
            suggestion = "ألعاب أو أفلام"
        else:
            period = "متأخر بالليل 🌙"
            suggestion = "حاجة خفيفة أو نوم"

        day_names = {
            0: "الاتنين", 1: "التلات", 2: "الأربع",
            3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد",
        }
        day = day_names.get(now.weekday(), "")

        return {
            "period": period,
            "suggestion": suggestion,
            "day": day,
            "hour": hour,
            "is_weekend": now.weekday() in (4, 5),  # Friday, Saturday
        }

    # ── Session Summary ────────────────────────────────────────

    def session_summary(self):
        """Generate a summary of the current session."""
        duration = time.time() - self._session_start
        minutes = int(duration / 60)

        summary = {
            "duration_minutes": minutes,
            "command_count": self._command_count,
            "dominant_topic": self.current_topic(),
            "topic_distribution": self.topic_distribution(),
            "mood_trend": self._current_mood,
            "entities_used": {
                t: e["name"]
                for t, e in self._entities.items()
            },
            "timestamp": datetime.now().isoformat(),
        }

        # Generate Arabic summary text
        topic_ar = {
            "gaming": "ألعاب 🎮",
            "work": "شغل 💼",
            "entertainment": "ترفيه 🍿",
            "browsing": "تصفح 🌐",
            "system": "إعدادات ⚙️",
            "social": "سوشيال 💬",
        }.get(summary["dominant_topic"], "متنوع")

        summary["text"] = (
            f"جلسة {minutes} دقيقة | "
            f"{self._command_count} أمر | "
            f"موضوع: {topic_ar} | "
            f"مزاج: {self._current_mood}"
        )

        return summary

    def save_session_summary(self):
        """Save session summary to disk."""
        if not _SESSION_SUMMARY:
            return

        summary = self.session_summary()
        path = os.path.join(_HERE, _SUMMARY_PATH)

        summaries = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    summaries = json.load(f)
            except (json.JSONDecodeError, OSError):
                summaries = []

        summaries.append(summary)

        # Keep last 30 sessions
        summaries = summaries[-30:]

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summaries, f, ensure_ascii=False, indent=2)
            log.info(f"📝 Session summary saved: {summary['text']}")
        except OSError as e:
            log.error(f"Failed to save session summary: {e}")

    def load_past_sessions(self, n=5):
        """Load last n session summaries."""
        path = os.path.join(_HERE, _SUMMARY_PATH)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                summaries = json.load(f)
            return summaries[-n:]
        except (json.JSONDecodeError, OSError):
            return []

    # ── Stats ──────────────────────────────────────────────────

    def stats(self):
        """Return context stats."""
        return {
            "history_size": len(self._history),
            "recent_size": len(self._recent),
            "entities": len(self._entities),
            "command_count": self._command_count,
            "current_mood": self._current_mood,
            "current_topic": self.current_topic(),
            "session_minutes": int((time.time() - self._session_start) / 60),
        }