# -*- coding: utf-8 -*-
"""
Learning guard — يوبي ميتعلمش غير الحاجة اللي اشتغلت فعلًا.

القديم كان بيحفظ أي تخمين من الـ LLM في learned_commands.json على طول،
فاتحفظ "افتح valorant" → playvalorant.com و"افتح chrome" → chrome.google.com.

دلوقتي كل حاجة يوبي بيفتحها بتبقى "تحت التجربة" لمدة `delay` ثانية:
  • لو قلت "لا / مش ده / غلط" أو قفلت نفس البرنامج  → تتلغي ومتتحفظش
  • لو البرنامج (exe) مش شغال بعد المدة              → تتلغي
  • غير كده                                         → تتحفظ (commit)

لو إنت بنفسك اخترت من الأزرار ("قصدك X؟" → X) ده تأكيد صريح، فبيتحفظ على طول.
"""

import os
import re
import threading
import time

_NEGATION_RE = re.compile(
    r"^(?:لا+|لأ+|لاء|مش ده|مش دي|مش كده|غلط|انا مقلتش|مش ده اللي|no|nope|wrong)\b")


def _proc_running(exe_name):
    try:
        import psutil
    except Exception:
        return None          # مش قادرين نعرف → منعتبرهاش فشل
    exe_name = exe_name.lower()
    try:
        for p in psutil.process_iter(["name"]):
            if (p.info.get("name") or "").lower() == exe_name:
                return True
    except Exception:
        return None
    return False


class LearningGuard:
    def __init__(self, commit, delay=15.0, log=print, check_process=True, on_veto=None):
        """commit(phrase, target, action) بيتنادى لما الأمر يثبت إنه صح.
        on_veto(phrase) بيتنادى لما يطلع غلط (عشان ننسى أي تعلم قديم ليها)."""
        self._commit = commit
        self._on_veto = on_veto
        self.delay = float(delay)
        self._log = log
        self._check = check_process
        self._lock = threading.Lock()
        self._pending = []     # [{phrase, target, action, exe, ts, timer}]
        self.last_vetoed = None   # آخر جملة اتلغت (عشان "لأ أقصد X" يتعلم منها)

    # ── API ──
    def propose(self, phrase, target, action="open", launch=None):
        if not phrase or not target:
            return
        exe = None
        if isinstance(launch, str) and launch.lower().endswith(".exe"):
            exe = os.path.basename(launch)
        item = {"phrase": phrase, "target": target, "action": action,
                "exe": exe, "ts": time.time()}
        t = threading.Timer(self.delay, self._finish, args=(item,))
        t.daemon = True
        item["timer"] = t
        with self._lock:
            # أمر جديد لنفس الجملة يلغي القديم
            for p in [p for p in self._pending if p["phrase"] == phrase]:
                p["timer"].cancel()
                self._pending.remove(p)
            self._pending.append(item)
        t.start()

    def confirm_now(self, phrase, target, action="open"):
        """المستخدم اختار بنفسه → احفظ على طول."""
        try:
            self._commit(phrase, target, action)
        except Exception as e:
            self._log(f"⚠️ learning commit: {e}")

    def on_command(self, text):
        """نادِيها مع كل أمر جديد. ترجع True لو الأمر كان اعتراض ("لا مش ده")."""
        t = (text or "").strip().lower()
        if not t or not _NEGATION_RE.search(t):
            return False
        return self._veto_latest("المستخدم قال لا")

    def veto_latest(self, why="اتلغى"):
        """Cancel the most recent learning that's still waiting ("انسى ده" right after a command)."""
        return self._veto_latest(why)

    def on_close(self, target):
        """المستخدم قفل حاجة → لو هي اللي لسه فاتحينها، يبقى كانت غلط."""
        tl = (target or "").lower().strip()
        if not tl:
            return False
        with self._lock:
            hit = [p for p in self._pending
                   if tl in str(p["target"]).lower() or str(p["target"]).lower() in tl]
        if hit:
            return self._veto(hit[-1], "اتقفل بسرعة")
        return False

    def pending(self):
        with self._lock:
            return [dict(phrase=p["phrase"], target=p["target"]) for p in self._pending]

    def flush(self):
        """للتستات / وقت القفل: commit لكل اللي مستني."""
        with self._lock:
            items = list(self._pending)
        for it in items:
            it["timer"].cancel()
            self._finish(it)

    # ── internals ──
    def _veto_latest(self, why):
        with self._lock:
            if not self._pending:
                return False
            item = self._pending[-1]
        return self._veto(item, why)

    def _veto(self, item, why):
        item["timer"].cancel()
        with self._lock:
            if item not in self._pending:
                return False
            self._pending.remove(item)
        self.last_vetoed = item["phrase"]
        self._log(f"🧹 مش هتعلم '{item['phrase']}' → {item['target']} ({why})")
        if self._on_veto:
            try:
                self._on_veto(item["phrase"])
            except Exception as e:
                self._log(f"⚠️ on_veto: {e}")
        return True

    def _finish(self, item):
        with self._lock:
            if item not in self._pending:
                return
            self._pending.remove(item)
        if self._check and item.get("exe"):
            running = _proc_running(item["exe"])
            if running is False:
                self._log(f"🧹 مش هتعلم '{item['phrase']}': {item['exe']} مش شغال")
                return
        try:
            self._commit(item["phrase"], item["target"], item["action"])
        except Exception as e:
            self._log(f"⚠️ learning commit: {e}")
