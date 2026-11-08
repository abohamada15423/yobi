# -*- coding: utf-8 -*-
"""Arabic normalisation + WER/CER for benchmarking Egyptian Arabic STT."""

import re
import unicodedata

_DIAC = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06ED\u0640]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

# common spelling variants that shouldn't count as errors
_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
    "گ": "ك", "پ": "ب", "چ": "ج", "ڤ": "ف",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})


def normalize_ar(text):
    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    t = _DIAC.sub("", t).translate(_MAP)
    t = _PUNCT.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _edit(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(ref, hyp):
    r, h = normalize_ar(ref).split(), normalize_ar(hyp).split()
    return _edit(r, h) / max(1, len(r))


def cer(ref, hyp):
    r = normalize_ar(ref).replace(" ", "")
    h = normalize_ar(hyp).replace(" ", "")
    return _edit(list(r), list(h)) / max(1, len(r))
