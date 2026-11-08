# -*- coding: utf-8 -*-
"""
Chat Memory — يحفظ محادثة يوبي مع المستخدم، على الميموري والقرص.

يستخدمه chat_engine عشان يبعت كل الـ history للـ LLM، فالمحادثة تبقى
طبيعية زي ChatGPT / Claude، مش سؤال-وجواب منفصلين.
"""

import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.join(_HERE, "chat_history.json")

# لو آخر محادثة كانت أقدم من كده، نبدأ من الأول.
_MAX_AGE_SEC = 24 * 3600        # 24 hours

# أقصى عدد رسائل نحتفظ بيها (user + assistant مع بعض)
_MAX_MESSAGES = 40              # ≈ 20 turn


class ChatMemory:
    """Conversation history store with optional disk persistence."""

    def __init__(self, path=_DEFAULT_PATH, persist=True,
                 max_messages=_MAX_MESSAGES):
        self._path = path
        self._persist = persist
        self._max_messages = max_messages
        self._messages = []      # list of {"role": "user"/"assistant", "content": str}
        self._load()

    # ── Public API ─────────────────────────────────────────────

    def add_user(self, text):
        if text and text.strip():
            self._push("user", text.strip())

    def add_assistant(self, text):
        if text and text.strip():
            self._push("assistant", text.strip())

    def get_messages(self):
        """Return a copy of the message list (for the LLM)."""
        return list(self._messages)

    def is_empty(self):
        return not self._messages

    def turn_count(self):
        return sum(1 for m in self._messages if m["role"] == "user")

    def clear(self):
        self._messages = []
        self._save()

    # ── Internal ───────────────────────────────────────────────

    def _push(self, role, content):
        self._messages.append({"role": role, "content": content})
        # Trim from the front, keeping it as an even user/assistant sequence
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]
        self._save()

    def _load(self):
        if not self._persist or not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            updated = data.get("updated_at", 0)
            if time.time() - updated > _MAX_AGE_SEC:
                return  # stale — start fresh
            msgs = data.get("messages", [])
            if isinstance(msgs, list):
                self._messages = [
                    m for m in msgs
                    if isinstance(m, dict)
                    and m.get("role") in ("user", "assistant")
                    and isinstance(m.get("content"), str)
                ]
        except (OSError, json.JSONDecodeError):
            pass

    def _save(self):
        if not self._persist:
            return
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "updated_at": time.time(),
                        "messages": self._messages,
                    },
                    f, ensure_ascii=False, indent=2,
                )
        except OSError:
            pass