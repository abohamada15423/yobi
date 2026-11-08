# -*- coding: utf-8 -*-
"""
Personal vocabulary — الكلمات اللي Whisper لازم يعرفها عنك.

Builds the Whisper prompt automatically from:
  • installed apps / games / websites (known_targets)
  • things you actually use (usage counts, learned on the fly, case-folded)
  • your own list in vocab.json: friends, nicknames, extra words, fixes
"""

import json
import os
import re
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(_HERE, "vocab.json")

_BAD = re.compile(r"(://|\\|/|\.exe$|^\d+$|^[a-f0-9-]{16,}$)", re.I)


def _clean(term):
    t = str(term or "").strip()
    t = re.sub(r"\.(exe|lnk|url)$", "", t, flags=re.I)
    t = t.replace("_", " ").strip(" -.")
    t = re.sub(r"\s+", " ", t)
    if not t or len(t) < 2 or len(t) > 32 or _BAD.search(t):
        return ""
    return t


class PersonalVocab:
    def __init__(self, path=DEFAULT_PATH, max_chars=300, targets_source=None):
        self.path = path
        self.max_chars = max_chars
        self._targets_source = targets_source
        self._lock = threading.Lock()
        self.friends, self.extra, self.fixes, self.usage = [], [], {}, {}
        self._load()

    # ------------------------------------------------------------- storage
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        self.friends = [t for t in (data.get("friends") or []) if _clean(t)]
        self.extra = [t for t in (data.get("extra") or []) if _clean(t)]
        self.fixes = dict(data.get("fixes") or {})
        merged_usage = {}
        for k, v in (data.get("usage") or {}).items():
            ck = _clean(k).lower()
            if ck:
                merged_usage[ck] = merged_usage.get(ck, 0) + int(v)
        self.usage = merged_usage

    def save(self):
        with self._lock:
            data = {
                "friends": self.friends,
                "extra": self.extra,
                "fixes": self.fixes,
                "usage": dict(sorted(self.usage.items(), key=lambda kv: -kv[1])[:300]),
            }
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # --------------------------------------------------------------- input
    def set_targets_source(self, fn):
        """fn() -> iterable of app/game/site names (re-read on every prompt)."""
        self._targets_source = fn

    def bump(self, term, n=1, save=True):
        t = _clean(term).lower()
        if not t:
            return
        with self._lock:
            self.usage[t] = self.usage.get(t, 0) + n
        if save:
            self.save()

    def add(self, term, kind="extra"):
        t = _clean(term)
        if not t:
            return
        lst = self.friends if kind == "friends" else self.extra
        if t not in lst:
            lst.append(t)
            self.save()

    # -------------------------------------------------------------- output
    def terms(self):
        seen, out = set(), []

        def push(t):
            c = _clean(t)
            k = c.lower()
            if c and k not in seen:
                seen.add(k)
                out.append(c)

        for t in self.friends + self.extra:
            push(t)
        for t in self.fixes.values():
            push(t)
        with self._lock:
            used = sorted(self.usage.items(), key=lambda kv: -kv[1])
        for t, _ in used:
            push(t)
        if self._targets_source:
            try:
                for t in self._targets_source() or []:
                    if isinstance(t, str):
                        push(t)
            except Exception:
                pass
        return out

    def prompt(self, base="", max_chars=None):
        """Whisper prompt = base hint + as many ranked terms as fit."""
        budget = int(max_chars or self.max_chars)
        text = (base or "").strip()
        sep = "، "
        for t in self.terms():
            cand = (text + (sep if text else "") + t)
            if len(cand) > budget:
                break
            text = cand
        return text[:budget]

    def hotwords(self, n=30):
        """Space-separated hot words for faster-whisper's `hotwords`."""
        return " ".join(self.terms()[:n])

    def apply_fixes(self, text):
        """Replace common mis-hearings, e.g. 'فالورنت' -> 'Valorant'."""
        if not text or not self.fixes:
            return text
        out = text
        for wrong, right in sorted(self.fixes.items(), key=lambda kv: -len(kv[0])):
            if wrong:
                out = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", right, out, flags=re.I)
        return out