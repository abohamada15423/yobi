# -*- coding: utf-8 -*-
"""
Spoken-text normalization: replace Arabic phonetic spellings of English
names with their canonical English form, then fuzzy-match the remainder
against known targets.

Split out from agent.py so it can be imported (and unit-tested) without
pulling in Whisper, Groq, the registry scan, or a GPU.
(Recovered from bytecode.)
"""

import difflib
import re

from aliases import ARABIC_TO_CANONICAL

# Intent words stripped before fuzzy-matching the target part.
_INTENT_WORDS = ["افتح", "شغل", "اقفل", "انهي", "قفل", "نزل", "سطب", "يفتح"]


def normalize_transcription(text, known_targets):
    text_lower = text.lower().strip()

    # 1. Arabic pronunciation → English name (longest alias first, word-bounded).
    for arabic in sorted(ARABIC_TO_CANONICAL, key=len, reverse=True):
        pat = re.compile(rf"(?<!\w){re.escape(arabic)}(?!\w)", flags=re.IGNORECASE)
        if pat.search(text_lower):
            english = ARABIC_TO_CANONICAL[arabic]
            text_lower = pat.sub(english, text_lower)
            print(f"🔄 ترجمة: '{arabic}' → '{english}'")

    # 2. Fuzzy-match what's left (minus the verb) against known targets.
    target_part = text_lower
    for intent_word in _INTENT_WORDS:
        target_part = re.sub(rf"(?<!\w){re.escape(intent_word)}(?!\w)", "", target_part).strip()

    if target_part and len(target_part) > 2:
        targets_str = [str(t) for t in known_targets if isinstance(t, str) and not str(t).startswith("__")]
        # v7: 0.6 كانت بتغيّر كلامك لاسم برنامج غلط قبل ما العقل يشوفه
        matches = difflib.get_close_matches(target_part, targets_str, n=1, cutoff=0.88)
        if matches:
            print(f"🔄 تطابق تقريبي: '{target_part}' → '{matches[0]}'")
            text_lower = re.sub(rf"(?<!\w){re.escape(target_part)}(?!\w)", matches[0], text_lower, count=1)

    return text_lower
