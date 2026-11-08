# -*- coding: utf-8 -*-
"""
Self-Learning — يوبي يتعلم من تجاربه.

يتتبع كل أمر اتقال:
  • نجح → يعزز الربط بين الجملة والفعل
  • فشل → يعلّم إن الجملة محتاجة توضيح
  • المستخدم صحّحه → يتعلم التصحيح للأبد
  • تكرر 3 مرات → يقترح على المستخدم يعلمه مرة واحدة

بيحفظ كل حاجة في learning_data.json.
"""

import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(_HERE, "learning_data.json")


class SelfLearner:
    """Learns from command outcomes and user corrections."""

    # بعد كام فشل نقترح على المستخدم يوضّح
    FAIL_THRESHOLD = 2

    # بعد كام تكرار نرفع الأمر لقايمة "متعلم جيدًا"
    SUCCESS_THRESHOLD = 3

    def __init__(self, path=DATA_PATH):
        self._path = path
        self._data = self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "commands": {},      # raw_command -> {resolved_to, action, success, fail, last_used}
            "corrections": {},   # wrong_phrase -> right_target
            "pending": [],       # [{"phrase": "...", "ts": ...}] waiting for user clarification
        }

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ── Normalization ────────────────────────────────────────

    @staticmethod
    def _key(phrase):
        import re
        return re.sub(r"\s+", " ", (phrase or "").lower().strip())

    # ── Recording ────────────────────────────────────────────

    def record_success(self, phrase, resolved_to, action):
        """Called after a command succeeds. Reinforces the phrase→action link."""
        k = self._key(phrase)
        if not k:
            return
        entry = self._data["commands"].setdefault(k, {
            "resolved_to": resolved_to,
            "action": action,
            "success": 0,
            "fail": 0,
            "last_used": 0,
        })
        entry["resolved_to"] = resolved_to
        entry["action"] = action
        entry["success"] = entry.get("success", 0) + 1
        entry["last_used"] = time.time()

        # Clear any pending correction for this phrase
        self._data["pending"] = [
            p for p in self._data.get("pending", []) if p.get("phrase") != k
        ]
        self._save()

    def record_failure(self, phrase):
        """Called when a command couldn't be resolved. Marks the phrase as
        needing clarification and adds it to the pending list if it hasn't
        been tried recently."""
        k = self._key(phrase)
        if not k:
            return
        entry = self._data["commands"].setdefault(k, {
            "resolved_to": None,
            "action": None,
            "success": 0,
            "fail": 0,
            "last_used": 0,
        })
        entry["fail"] = entry.get("fail", 0) + 1
        entry["last_used"] = time.time()

        # Add to pending only once
        pending_phrases = {p.get("phrase") for p in self._data.get("pending", [])}
        if k not in pending_phrases:
            self._data.setdefault("pending", []).append({
                "phrase": k,
                "ts": time.time(),
            })
        self._save()

    def record_correction(self, wrong_phrase, correct_target, action="open"):
        """The user explicitly corrected Yobi. Remember it forever."""
        k = self._key(wrong_phrase)
        if not k or not correct_target:
            return
        self._data.setdefault("corrections", {})[k] = {
            "target": correct_target,
            "action": action,
            "ts": time.time(),
        }
        # Also store as a learned command
        self._data["commands"][k] = {
            "resolved_to": correct_target,
            "action": action,
            "success": 1,
            "fail": 0,
            "last_used": time.time(),
        }
        # Remove from pending
        self._data["pending"] = [
            p for p in self._data.get("pending", []) if p.get("phrase") != k
        ]
        self._save()

    # ── Lookups ──────────────────────────────────────────────

    def lookup(self, phrase):
        """Return (resolved_to, action) if we've learned this phrase, else None."""
        k = self._key(phrase)
        if not k:
            return None

        # 1. Explicit correction wins
        corr = self._data.get("corrections", {}).get(k)
        if corr:
            return corr["target"], corr.get("action", "open")

        # 2. Learned command with decent success count
        entry = self._data.get("commands", {}).get(k)
        if entry and entry.get("resolved_to") and entry.get("success", 0) >= 1:
            return entry["resolved_to"], entry.get("action", "open")

        return None

    def needs_correction(self, phrase):
        """True if the phrase has failed enough times to ask the user."""
        k = self._key(phrase)
        if not k:
            return False
        entry = self._data.get("commands", {}).get(k)
        if not entry:
            return False
        return (
            entry.get("fail", 0) >= self.FAIL_THRESHOLD
            and entry.get("success", 0) == 0
        )

    def get_pending(self, max_age_seconds=7 * 24 * 3600):
        """Return phrases waiting for correction (recent ones only)."""
        now = time.time()
        return [
            p["phrase"] for p in self._data.get("pending", [])
            if (now - p.get("ts", 0)) < max_age_seconds
        ]

    def forget(self, phrase):
        """Remove a learned phrase (in case of a bad learning)."""
        k = self._key(phrase)
        if k in self._data.get("commands", {}):
            del self._data["commands"][k]
        if k in self._data.get("corrections", {}):
            del self._data["corrections"][k]
        self._data["pending"] = [
            p for p in self._data.get("pending", []) if p.get("phrase") != k
        ]
        self._save()

    def clear_all(self):
        self._data = {"commands": {}, "corrections": {}, "pending": []}
        self._save()

    def stats(self):
        cmds = self._data.get("commands", {})
        return {
            "total_commands": len(cmds),
            "well_learned": sum(1 for v in cmds.values() if v.get("success", 0) >= self.SUCCESS_THRESHOLD),
            "pending_corrections": len(self._data.get("pending", [])),
            "explicit_corrections": len(self._data.get("corrections", {})),
        }