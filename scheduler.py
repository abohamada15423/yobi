# -*- coding: utf-8 -*-
"""
Task Scheduler — يجدول أوامر وتذكيرات مؤقتة.

مثال: "فكرني بعد 10 دقايق" / "فكرني أروح الجيم كمان ساعة" / "اظبط تايمر لمدة نص ساعة"
"""
import re
import threading
from datetime import datetime, timedelta

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_WORD_NUMS = {
    "خمس": 5, "خمسة": 5, "خمسه": 5,
    "عشر": 10, "عشرة": 10, "عشره": 10,
    "خمستاش": 15, "تلت": 20, "ثلث": 20,
    "عشرين": 20, "تلاتين": 30, "ثلاثين": 30,
    "اربعين": 40, "أربعين": 40, "خمسين": 50,
}


class TaskScheduler:
    """Manages timed reminders and delayed command execution."""

    def __init__(self, on_notify, on_execute):
        self._tasks = []
        self._on_notify = on_notify
        self._on_execute = on_execute
        self._next_id = 0
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────

    def has_scheduled_intent(self, command):
        """Return True if the command contains scheduling language."""
        cmd = (command or "").lower()
        time_words = [
            "بعد", "كمان", "لمدة", "لمده", "فكرني", "نبهني",
            "remind", "timer", "تايمر", "schedule", "after",
        ]
        return any(w in cmd for w in time_words) and self._extract_minutes(cmd) is not None

    def parse_and_schedule(self, command):
        """Parse a scheduling command and register the task.

        Returns (success: bool, user_message: str | None).
        """
        cmd = (command or "").lower().strip()
        minutes = self._extract_minutes(cmd)
        if minutes is None:
            return False, None

        # Reminder / Timer
        if any(w in cmd for w in ["فكرني", "نبهني", "remind", "تذكير", "تايمر", "timer"]):
            reminder_text = self._extract_reminder_text(cmd)
            label = reminder_text or "تذكير ⏰"
            self._add_task(
                minutes, f"تذكير: {label}",
                lambda t=label: self._on_notify(t),
            )
            return True, f"تم! هفكرك بعد {self._format_duration(minutes)} ⏰"

        # Delayed command
        action = self._extract_action(cmd)
        if action:
            self._add_task(
                minutes, f"أمر مجدول: {action}",
                lambda a=action: self._on_execute(a),
            )
            return True, f"تم جدولة '{action}' بعد {self._format_duration(minutes)} ⏳"

        return False, None

    def list_tasks(self):
        """Return descriptions of pending tasks."""
        with self._lock:
            return [
                {"id": t["id"], "description": t["desc"], "execute_at": t["at"]}
                for t in self._tasks
            ]

    def cancel_all(self):
        """Cancel every pending task."""
        with self._lock:
            for t in self._tasks:
                t["timer"].cancel()
            self._tasks.clear()

    # ── Internals ───────────────────────────────────────────────

    def _add_task(self, minutes, desc, fn):
        with self._lock:
            self._next_id += 1
            tid = self._next_id
            at = (datetime.now() + timedelta(minutes=minutes)).isoformat()
            timer = threading.Timer(minutes * 60, self._fire, args=(tid,))
            timer.daemon = True
            self._tasks.append(
                {"id": tid, "desc": desc, "at": at, "fn": fn, "timer": timer}
            )
            timer.start()

    def _fire(self, tid):
        fn = None
        with self._lock:
            for t in self._tasks:
                if t["id"] == tid:
                    fn = t["fn"]
                    self._tasks.remove(t)
                    break
        if fn:
            try:
                fn()
            except Exception as e:
                print(f"⚠️ خطأ في تنفيذ المهمة المجدولة: {e}")

    # ── Time parsing helpers ────────────────────────────────────

    @staticmethod
    def _extract_minutes(cmd):
        cmd = (cmd or "").translate(_AR_DIGITS).lower()
        prep = r"(?:بعد|كمان|لمدة|لمده|كل)"

        # "بعد/كمان X دقيقة/دقايق"
        m = re.search(rf"{prep}\s+(\d+)\s*(?:دقيق[ةه]|دقايق|minute|minutes|min)", cmd)
        if m:
            return int(m.group(1))

        # "بعد/كمان X ساعة/ساعات"
        m = re.search(rf"{prep}\s+(\d+)\s*(?:ساع[ةه]|ساعات|hour|hours|hr)", cmd)
        if m:
            return int(m.group(1)) * 60

        # Dual forms: "ساعتين" / "دقيقتين"
        if re.search(rf"{prep}\s+ساعتين", cmd):
            return 120
        if re.search(rf"{prep}\s+دقيقتين", cmd):
            return 2

        # Fractions of an hour: "نص ساعة", "ربع ساعة", "تلت ساعة"
        if re.search(rf"{prep}\s+(?:نص|نصف)\s+ساع[ةه]", cmd):
            return 30
        if re.search(rf"{prep}\s+ربع\s+ساع[ةه]", cmd):
            return 15
        if re.search(rf"{prep}\s+(?:تلت|ثلث)\s+ساع[ةه]", cmd):
            return 20

        # Word numbers + minutes ("بعد عشر دقايق", "كمان خمس دقايق")
        for word, val in _WORD_NUMS.items():
            if re.search(rf"{prep}\s+{re.escape(word)}\s+(?:دقيق[ةه]|دقايق)", cmd):
                return val

        # "بعد/كمان ساعة" (no number)
        if re.search(rf"{prep}\s+ساع[ةه]", cmd):
            return 60
        if re.search(rf"{prep}\s+دقيق[ةه]", cmd):
            return 1

        # English: "after/in/for X minutes/hours"
        m = re.search(r"(?:after|in|for)\s+(\d+)\s*(?:minute|minutes|min)", cmd)
        if m:
            return int(m.group(1))

        m = re.search(r"(?:after|in|for)\s+(\d+)\s*(?:hour|hours|hr)", cmd)
        if m:
            return int(m.group(1)) * 60

        return None

    @staticmethod
    def _extract_reminder_text(cmd):
        m = re.search(
            r"(?:فكرني|نبهني|remind\s+me)\s+"
            r"(?:(?:إن|ان|عن|to|about|that|ب)\s+)?"
            r"(.+?)(?:\s+(?:بعد|كمان|لمدة|لمده|كل|after|in)\b|$)",
            cmd,
        )
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_action(cmd):
        word_nums_pat = "|".join(re.escape(w) for w in sorted(_WORD_NUMS, key=len, reverse=True))
        action = re.sub(
            rf"(?:بعد|كمان|لمدة|لمده|كل)\s+(?:(?:\d+|{word_nums_pat})\s*)?(?:دقيق[ةه]|دقايق|دقيقتين|ساع[ةه]|ساعتين|ساعات"
            r"|نص\s+ساع[ةه]|نصف\s+ساع[ةه]|ربع\s+ساع[ةه]|تلت\s+ساع[ةه]|ثلث\s+ساع[ةه])",
            "", cmd,
        )
        action = re.sub(
            r"(?:after|in|for)\s+(?:\d+\s*)?(?:minute|minutes|hour|hours|min|hr)",
            "", action,
        )
        action = action.strip()
        return action or None

    @staticmethod
    def _format_duration(minutes):
        if minutes >= 60:
            h = minutes // 60
            m = minutes % 60
            if m:
                return f"{h} ساعة و {m} دقيقة"
            return f"{h} ساعة"
        return f"{minutes} دقيقة"