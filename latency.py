# -*- coding: utf-8 -*-
"""
Latency tracker — بيقيس كل مرحلة في الدور الواحد.

Timeline of one voice turn:
    speech_end ──STT──▶ stt_done ── (LLM) ──▶ llm_first ── TTS ──▶ first_audio

Every module just calls `latency.mark("<name>")`; the tracker is thread-safe
and ignores marks when no turn is open. One log line per turn, a p50/p90
summary every N turns, and an optional CSV for tools/latency_report.py.

Marks:
    speech_end   — VAD decided the user stopped talking (turn starts here)
    stt_start / stt_done
    llm_start / llm_first   — brain request sent / first sentence ready
    tts_request  — first speak() of the turn
    tts_ready    — first audio synthesized
    first_audio  — first sample handed to the speaker (turn ends here)
"""

import csv
import os
import statistics
import threading
import time
from collections import deque

FIELDS = ["turn", "wall_time", "stt_engine", "stt_ms", "llm_first_ms", "tts_ms",
          "total_ms", "speech_ms"]


def _ms(a, b):
    if a is None or b is None:
        return None
    return max(0.0, (b - a) * 1000.0)


class LatencyTracker:
    def __init__(self, csv_path=None, summary_every=10, window=100, log=None,
                 enabled=True):
        self.enabled = enabled
        self._csv = csv_path
        self._every = max(1, int(summary_every))
        self._hist = deque(maxlen=window)
        self._lock = threading.Lock()
        self._turn = None
        self._n = 0
        self._log = log or (lambda m: print(m))

    # ------------------------------------------------------------ control
    def configure(self, csv_path=None, enabled=None, log=None, summary_every=None):
        if csv_path is not None:
            self._csv = csv_path
        if enabled is not None:
            self.enabled = enabled
        if log is not None:
            self._log = log
        if summary_every:
            self._every = int(summary_every)

    def start_turn(self, speech_end=None, speech_ms=None):
        if not self.enabled:
            return
        with self._lock:
            self._n += 1
            self._turn = {"turn": self._n, "speech_end": speech_end or time.perf_counter(),
                          "speech_ms": speech_ms, "done": False}

    def mark(self, name, t=None, info=None, once=True):
        if not self.enabled:
            return
        finish = False
        with self._lock:
            tr = self._turn
            if tr is None or tr.get("done"):
                return
            if once and name in tr:
                return
            tr[name] = t if t is not None else time.perf_counter()
            if info is not None:
                tr[name + "_info"] = info
            if name == "first_audio":
                finish = True
        if finish:
            # may be called from the audio callback → log/CSV off-thread
            threading.Thread(target=self._finish, daemon=True).start()

    def end_turn(self):
        """Close the turn even if Yobi never spoke (e.g. silent action)."""
        self._finish(force=True)

    def current(self):
        with self._lock:
            return dict(self._turn) if self._turn else None

    # ------------------------------------------------------------ results
    def _finish(self, force=False):
        with self._lock:
            tr = self._turn
            if tr is None or tr.get("done"):
                return
            if force and "stt_done" not in tr:
                self._turn = None
                return
            tr["done"] = True
            row = {
                "turn": tr["turn"],
                "wall_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stt_engine": tr.get("stt_done_info") or "",
                "stt_ms": _ms(tr.get("stt_start", tr.get("speech_end")), tr.get("stt_done")),
                "llm_first_ms": _ms(tr.get("llm_start"), tr.get("llm_first")),
                "tts_ms": _ms(tr.get("tts_request"), tr.get("first_audio")),
                "total_ms": _ms(tr.get("speech_end"), tr.get("first_audio")),
                "speech_ms": tr.get("speech_ms"),
            }
            self._hist.append(row)
            n = len(self._hist)
        self._log(self.format_row(row))
        self._write_csv(row)
        if n and row["turn"] % self._every == 0:
            self._log(self.format_summary())

    @staticmethod
    def _fmt(v):
        if v is None:
            return "—"
        return f"{v / 1000:.2f}s" if v >= 1000 else f"{v:.0f}ms"

    def format_row(self, r):
        parts = [f"STT {self._fmt(r['stt_ms'])}" + (f" ({r['stt_engine']})" if r["stt_engine"] else "")]
        if r["llm_first_ms"] is not None:
            parts.append(f"LLM أول جملة {self._fmt(r['llm_first_ms'])}")
        if r["tts_ms"] is not None:
            parts.append(f"TTS أول صوت {self._fmt(r['tts_ms'])}")
        parts.append(f"الإجمالي {self._fmt(r['total_ms'])}")
        return f"⏱️ دور #{r['turn']}: " + " | ".join(parts)

    def stats(self):
        out = {}
        rows = list(self._hist)
        for key in ("stt_ms", "llm_first_ms", "tts_ms", "total_ms"):
            vals = sorted(v[key] for v in rows if v[key] is not None)
            if not vals:
                continue
            p90 = vals[min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))]
            out[key] = {"n": len(vals), "p50": statistics.median(vals), "p90": p90}
        return out

    def format_summary(self):
        s = self.stats()
        names = {"stt_ms": "STT", "llm_first_ms": "LLM", "tts_ms": "TTS", "total_ms": "الإجمالي"}
        parts = [f"{names[k]} p50 {self._fmt(v['p50'])} / p90 {self._fmt(v['p90'])}"
                 for k, v in s.items()]
        return "📊 latency آخر {} دور: ".format(len(self._hist)) + " | ".join(parts)

    def _write_csv(self, row):
        if not self._csv:
            return
        try:
            new = not os.path.exists(self._csv)
            with open(self._csv, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                w.writerow({k: (round(v, 1) if isinstance(v, float) else v)
                            for k, v in row.items() if k in FIELDS})
        except Exception:
            pass


tracker = LatencyTracker()


def mark(name, t=None, info=None):
    tracker.mark(name, t, info)


def start_turn(speech_end=None, speech_ms=None):
    tracker.start_turn(speech_end, speech_ms)
