# -*- coding: utf-8 -*-
"""
Addressed-Speech Classifier — يفرّق بين الكلام الموجّه ليوبي والكلام
الجانبي (ناس بتتكلم، تلفزيون، تفكير بصوت عالي).

Strategy:
  1. Explicit re-address ("يا يوبي", "يوبي") → always DIRECTED
  2. Short affirmation within 8s of Yobi asking something → DIRECTED
     (handles "أيوة" / "لا" / "تمام" replies to confirmations)
  3. Starts with a known command verb → DIRECTED
  4. Short question → DIRECTED
  5. Very long utterance (>18 words) → almost certainly AMBIENT
  6. Uncertain → optional LLM check (llama-3.1-8b-instant, ~100ms)
  7. No LLM → default DIRECTED (safer to over-respond than miss)
"""

import re
import time


# ---------------------------------------------------------------------------
# Heuristic signal sets
# ---------------------------------------------------------------------------

_ADDRESS_MARKERS = [
    "يا يوبي", "يوبي", "يا يوبى", "yobi", "hey yobi",
    "يا بوبي",  # common Whisper mishearing
]

# Command verbs — anything starting with these is unambiguously directed
_COMMAND_VERBS = [
    "افتح", "شغل", "اقفل", "انهي", "قفل", "نزل", "سطب",
    "علي", "وطي", "ارفع", "اخفض", "زود", "قلل", "اكتم",
    "خد", "اعمل", "روح", "ادخل", "ابحث", "سيرش", "دور",
    "قول", "قولي", "فكرني", "نبهني", "ذكرني",
    "open", "close", "launch", "run", "start", "play", "pause",
    "kill", "install", "search", "find", "set", "remind",
]

# Question indicators — presence + short length ≈ directed
_QUESTION_WORDS = [
    "إيه", "ايه", "كام", "كم", "مين", "فين", "وين",
    "ازاي", "إزاي", "ليه", "ليش", "امتى", "متى", "هل",
    "what", "who", "where", "when", "how", "why",
]

# Affirmations / negations — valid replies only right after Yobi asked
_SHORT_REPLIES = [
    "أيوة", "ايوه", "أه", "اه", "تمام", "ماشي", "لا", "لأ",
    "yes", "no", "ok", "okay", "yep", "nope", "sure",
    "الغاء", "إلغاء", "cancel",
]

# Ambient-looking patterns — words that rarely appear in a command to Yobi
_AMBIENT_HINTS = [
    "بيقولك", "بيقولي", "قلت لك", "قلتلي", "هو قال",
    "تعالى", "تعالي", "يلا بينا", "هيا بنا",
    "امبارح", "النهاردة كنا", "زميلي",
    "shut up", "come here", "let's go",
]


class AddressedClassifier:
    """Stateful classifier — remembers when Yobi just asked something,
    and tracks consecutive ambient detections so the conversation can
    auto-close when the user clearly isn't talking to Yobi."""

    # If Yobi just asked a confirmation within this window, a short reply
    # ("أيوة", "لا") is treated as directed.
    REPLY_WINDOW_SEC = 8.0

    # After this many consecutive ambient utterances, force-exit the
    # conversation so Yobi stops listening to background chatter.
    MAX_CONSECUTIVE_AMBIENT = 2

    # Utterances longer than this are almost certainly not commands.
    LONG_UTTERANCE_WORDS = 18

    def __init__(self, llm_client=None, llm_model="llama-3.1-8b-instant"):
        self._llm = llm_client
        self._llm_model = llm_model
        self._last_question_ts = 0.0
        self._consecutive_ambient = 0

    # ── Public API ─────────────────────────────────────────────

    def mark_yobi_asked(self):
        """Call this right after Yobi speaks a question/confirmation, so
        the user's short reply is recognized as directed."""
        self._last_question_ts = time.time()

    def reset(self):
        """Called when entering a fresh conversation after a wake word."""
        self._consecutive_ambient = 0
        self._last_question_ts = 0.0

    def is_addressed(self, text):
        """Return True if `text` looks like speech directed at Yobi."""
        if not text or not text.strip():
            return False

        t = text.strip()
        t_lower = t.lower()
        word_count = len(t.split())

        # 1. Explicit re-address — always wins
        if any(m in t_lower for m in _ADDRESS_MARKERS):
            self._consecutive_ambient = 0
            return True

        # 2. Short reply to a question Yobi just asked
        if (time.time() - self._last_question_ts) < self.REPLY_WINDOW_SEC:
            if word_count <= 4 and any(r in t_lower for r in _SHORT_REPLIES):
                self._consecutive_ambient = 0
                return True

        # 3. Ambient hints — strong negative signal
        if any(h in t_lower for h in _AMBIENT_HINTS):
            self._consecutive_ambient += 1
            return False

        # 4. Very long utterance → ambient
        if word_count > self.LONG_UTTERANCE_WORDS:
            self._consecutive_ambient += 1
            return False

        # 5. Starts with a command verb → directed
        first_word = t_lower.split()[0] if t_lower.split() else ""
        # Strip common prefixes (و، ف، ثم)
        first_word = re.sub(r"^[وفث]", "", first_word)
        if any(first_word.startswith(v) for v in _COMMAND_VERBS):
            self._consecutive_ambient = 0
            return True

        # 6. Short question → directed (whole-word match so 'والهلق'/'كمتلك' don't trigger)
        words_set = set(re.sub(r"[،,.!؟?\"'()\[\]]+", " ", t_lower).split())
        if word_count <= 12 and (words_set & set(_QUESTION_WORDS) or "؟" in t_lower or "?" in t_lower):
            self._consecutive_ambient = 0
            return True

        # 7. Uncertain — ask LLM if available
        if self._llm is not None:
            verdict = self._ask_llm(t)
            if verdict:
                self._consecutive_ambient = 0
            else:
                self._consecutive_ambient += 1
            return verdict

        # 8. No LLM → default to directed (safer)
        self._consecutive_ambient = 0
        return True

    def should_exit_conversation(self):
        """True if we've seen too many ambient utterances in a row."""
        return self._consecutive_ambient >= self.MAX_CONSECUTIVE_AMBIENT

    # ── Internal ───────────────────────────────────────────────

    def _ask_llm(self, text):
        """One quick classification call. Cheap model, low tokens."""
        try:
            resp = self._llm.chat.completions.create(
                model=self._llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify whether a spoken phrase is DIRECTED at "
                            "a voice assistant (a command or question addressed to it) "
                            "or AMBIENT (conversation between other people, TV audio, "
                            "or thinking out loud). The assistant is called 'Yobi' and "
                            "speaks Egyptian Arabic. Reply with exactly one word: "
                            "DIRECTED or AMBIENT."
                        ),
                    },
                    {"role": "user", "content": f'"{text}"'},
                ],
                temperature=0.0,
                max_tokens=3,
            )
            answer = resp.choices[0].message.content.upper()
            return "DIRECTED" in answer
        except Exception:
            # On network failure, assume directed (don't drop real commands)
            return True