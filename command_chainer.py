# -*- coding: utf-8 -*-
"""
Command Chainer — يقسم الأوامر المركبة لأوامر فردية متتالية.

مثال: "افتح Chrome وروح فيسبوك" → ["افتح Chrome", "افتح فيسبوك"]
"""

import re

# Explicit sequential separators (always split when non-question).
EXPLICIT_SEPARATORS = [
    "وبعد كده", "و بعد كده", "وبعدين", "و بعدين",
    " ثم ", " and then ", " then ",
]

# Soft conjunctions (" و ", " and ") — only split when not a question/media query
# and when the second clause is a clear command or target.
SOFT_SEPARATORS = [" و ", " and "]

# Verbs that can be carried forward to a bare target ("افتح كروم و سبوتيفاي")
_CARRY_VERBS = [
    "افتح", "افتحلي", "شغل", "شغلي", "اقفل", "انهي", "قفل", "نزل", "سطب",
    "open", "close", "install", "start", "launch", "kill",
]

# All standalone command verbs (never prepend a carry-verb onto these!)
_ALL_ACTION_VERBS = _CARRY_VERBS + [
    "علي", "وطي", "ارفع", "اخفض", "قلل", "زود", "اكتم", "كتم", "فك", "الغي", "إلغاء",
    "وقف", "كمل", "خلي", "ظبط", "اضبط", "اعمل", "اطفي", "نوم", "سجل", "خد",
    "فكرني", "نبهني", "ابحث", "دور", "هات", "روح", "وديني", "شيل", "فعل", "انسى",
    "امسح", "حدث", "افحص", "فحص", "اقترح",
    "mute", "unmute", "set", "play", "pause", "search", "remind", "lock", "shutdown", "restart",
]

_QUESTION_STARTS = (
    "ايه", "إيه", "ما ", "من ", "مين", "امتى", "إمتى", "ازاي", "إزاي",
    "ليه", "ليش", "هل", "كام", "كم", "فين", "وين", "قارن", "الفرق",
    "what", "who", "where", "when", "why", "how", "which",
)

_MEDIA_PREFIXES = (
    "شغل فيلم", "شغل اغنية", "شغل أغنية", "شغل اغنيه", "شغل مسلسل", "شغل سورة",
    "افتح فيلم", "افتح اغنية", "افتح أغنية", "ابحث عن", "دور على", "دور علي",
    "search for", "play song", "play movie",
)


def _starts_with_verb(text, verb_list):
    tl = text.lower().strip()
    return any(re.match(rf"^{re.escape(v)}(?:\s|$)", tl) for v in verb_list)


def split_compound_command(command):
    """Split a compound command into individual commands.

    Preserves questions ("ايه الفرق بين بايثون و جافا") and media titles
    ("شغل فيلم توم و جيري") as single commands, and avoids prepending "افتح"
    onto standalone verbs like "علي الصوت".
    """
    cmd = (command or "").strip()
    if not cmd:
        return [cmd]

    cmd_l = cmd.lower()
    # Never split questions
    if "?" in cmd_l or "؟" in cmd_l or cmd_l.startswith(_QUESTION_STARTS):
        return [cmd]

    parts = None
    used_soft = False

    for sep in EXPLICIT_SEPARATORS:
        if sep in cmd_l:
            cand = [p.strip() for p in re.split(re.escape(sep), cmd, flags=re.IGNORECASE) if p.strip()]
            if len(cand) > 1:
                parts = cand
                break

    if not parts and not cmd_l.startswith(_MEDIA_PREFIXES):
        for sep in SOFT_SEPARATORS:
            if sep in cmd_l:
                cand = [p.strip() for p in re.split(re.escape(sep), cmd, flags=re.IGNORECASE) if p.strip()]
                if len(cand) > 1:
                    # Only split on soft " و " if part 0 starts with an action verb
                    # and part 1 either starts with an action verb OR is a short target name (<= 3 words)
                    if _starts_with_verb(cand[0], _ALL_ACTION_VERBS) and all(
                        _starts_with_verb(p, _ALL_ACTION_VERBS) or (
                            _starts_with_verb(cand[0], _CARRY_VERBS) and len(p.split()) <= 3
                        )
                        for p in cand[1:]
                    ):
                        parts = cand
                        used_soft = True
                        break

    if not parts:
        return [cmd]

    first_intent = None
    first_lower = parts[0].lower()
    for verb in _CARRY_VERBS:
        if re.match(rf"^{re.escape(verb)}(?:\s|$)", first_lower):
            first_intent = verb
            break

    if first_intent and len(parts) > 1:
        for i in range(1, len(parts)):
            if _starts_with_verb(parts[i], _ALL_ACTION_VERBS):
                continue
            parts[i] = f"{first_intent} {parts[i]}"

    return parts
