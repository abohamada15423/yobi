# -*- coding: utf-8 -*-
"""
Dataset recorder: كل أمر بتقوله ليوبي بيتحفظ كـ داتا تدريب، ومعاه هل نجح ولا لأ.

    data/commands/
        audio/2026-10-06/153012_ab12cd.wav      الصوت (بعد كلمة النداء بس)
        log.jsonl                               events بتتضاف بس، عمرها ما بتتعدل

كل سطر في log.jsonl event واحد:
    {"ev":"heard",  "id":..., "ts":..., "text":..., "engine":..., "conf":{...}, "low":bool, "wav":...}
    {"ev":"phrase", "id":..., "phrase":...}            النص بعد التصحيح والتقسيم
    {"ev":"label",  "id":..., "label":"correct|wrong|corrected", "target":...}

اللابل بييجي لوحده من LearningGuard:
    correct   → فتح حاجة وفضلت مفتوحة / اخترتها من الأزرار
    wrong     → قلت "لا / مش ده" أو قفلتها بسرعة
    corrected → قلت "لأ أقصد X"  (أغلى داتا: النص الغلط + الهدف الصح)

tools/export_dataset.py بيحوّل الـ log لملفات تدريب.
كله local على جهازك، مفيش أي حاجة بتتبعت برا.
"""

import json
import os
import queue
import secrets
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(_HERE, "data", "commands")


class DatasetRecorder:
    def __init__(self, root=DEFAULT_ROOT, enabled=True, save_audio=True,
                 max_audio_mb=2000, log=print):
        self.root = root
        self.enabled = bool(enabled)
        self.save_audio = bool(save_audio)
        self.max_bytes = int(max_audio_mb) * 1024 * 1024
        self._log = log
        self._lock = threading.Lock()
        self._current = None              # آخر أمر اتسمع
        self._by_phrase = {}              # phrase → (id, ts)
        self._audio_bytes = None          # بيتحسب مرة في الأول
        self._q = queue.Queue()
        if self.enabled:
            os.makedirs(os.path.join(self.root, "audio"), exist_ok=True)
            threading.Thread(target=self._writer, daemon=True).start()

    # ── API ──────────────────────────────────────────────────────
    def heard(self, audio, text, engine=None, conf=None, low=False):
        """نادِيها بعد ما الأمر يتسمع. بترجع id."""
        if not self.enabled or not text:
            return None
        rid = time.strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(3)
        wav_rel = None
        wav_bytes = None
        if self.save_audio and audio is not None and self._audio_room():
            try:
                wav_bytes = audio.get_wav_data()
                wav_rel = os.path.join("audio", rid[:8], rid + ".wav")
            except Exception:
                wav_bytes = None
        with self._lock:
            self._current = rid
        self._q.put(("event", {"ev": "heard", "id": rid, "ts": round(time.time(), 2),
                               "text": text, "engine": engine, "conf": conf,
                               "low": bool(low), "wav": wav_rel}))
        if wav_bytes:
            self._q.put(("wav", (wav_rel, wav_bytes)))
        return rid

    def bind_phrase(self, phrase):
        """الجملة اللي handle_command شغال عليها (بعد التصحيح/التقسيم) → آخر أمر اتسمع."""
        if not self.enabled or not phrase:
            return
        with self._lock:
            rid = self._current
            if not rid:
                return
            self._by_phrase[self._key(phrase)] = (rid, time.time())
            self._gc()
        self._q.put(("event", {"ev": "phrase", "id": rid, "phrase": phrase}))

    def label(self, phrase, label, target=None):
        """label: correct | wrong | corrected"""
        if not self.enabled or not phrase:
            return
        with self._lock:
            hit = self._by_phrase.get(self._key(phrase))
        if not hit:
            return
        ev = {"ev": "label", "id": hit[0], "label": label, "ts": round(time.time(), 2)}
        if target:
            ev["target"] = str(target)
        self._q.put(("event", ev))

    def flush(self, timeout=5.0):
        """للتستات ووقت القفل."""
        done = threading.Event()
        self._q.put(("flush", done))
        done.wait(timeout)

    # ── internals ────────────────────────────────────────────────
    @staticmethod
    def _key(p):
        return " ".join((p or "").lower().split())

    def _gc(self, max_age=600):
        now = time.time()
        for k in [k for k, (_, t) in self._by_phrase.items() if now - t > max_age]:
            del self._by_phrase[k]

    def _audio_room(self):
        if self._audio_bytes is None:
            total = 0
            for dp, _, fs in os.walk(os.path.join(self.root, "audio")):
                for f in fs:
                    try:
                        total += os.path.getsize(os.path.join(dp, f))
                    except OSError:
                        pass
            self._audio_bytes = total
        if self._audio_bytes >= self.max_bytes:
            if self.save_audio:
                self._log("ℹ️ داتا الصوت وصلت للحد، هكمل أسجل النص بس")
                self.save_audio = False
            return False
        return True

    def _writer(self):
        path = os.path.join(self.root, "log.jsonl")
        while True:
            kind, payload = self._q.get()
            try:
                if kind == "event":
                    with open(path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                elif kind == "wav":
                    rel, data = payload
                    full = os.path.join(self.root, rel)
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, "wb") as f:
                        f.write(data)
                    self._audio_bytes = (self._audio_bytes or 0) + len(data)
                elif kind == "flush":
                    payload.set()
            except Exception as e:
                self._log(f"⚠️ dataset recorder: {e}")


def load_records(root=DEFAULT_ROOT):
    """بيجمع الـ events لـ records: {id: {text, phrase, label, target, wav, ...}}.
    آخر label هو اللي بيكسب (مثلًا wrong وبعدها corrected)."""
    recs = {}
    path = os.path.join(root, "log.jsonl")
    if not os.path.exists(path):
        return recs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            r = recs.setdefault(ev.get("id"), {"id": ev.get("id")})
            kind = ev.get("ev")
            if kind == "heard":
                r.update({k: ev.get(k) for k in ("ts", "text", "engine", "conf", "low", "wav")})
            elif kind == "phrase":
                r.setdefault("phrases", []).append(ev.get("phrase"))
            elif kind == "label":
                r["label"] = ev.get("label")
                if ev.get("target"):
                    r["target"] = ev["target"]
    return recs
