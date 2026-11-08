# -*- coding: utf-8 -*-
"""
Offline wake word — "يا يوبي" من غير Whisper.

Runs an openWakeWord ONNX model on every 80 ms of (echo-cancelled) audio.
Fixes in v8:
  • Continuous trailing window (18 chunks = ~1.4s) after voice activity so
    openWakeWord's internal mel/embedding ring buffer never freezes at the end
    of saying "يا يوبي".
  • Default patience=1, threshold=0.35, vad_threshold=0.0 so short Egyptian
    Arabic wake phrases trigger reliably without Silero VAD false-rejections.
"""

import os
import queue
import threading
import time

import numpy as np

CHUNK = 1280      # 80 ms @ 16 kHz — what openWakeWord expects
MIN_RMS = 75.0    # low gate; trailing chunks still run for 1.4s after speech
TAIL_CHUNKS = 18  # keep feeding openWakeWord for ~1.44s after voice drops


class WakeWordDetector:
    def __init__(self, model, threshold=0.35, patience=1, cooldown=1.8,
                 vad_threshold=0.0, on_detect=None, log=print, debug=False):
        self.threshold = float(threshold)
        self.patience = max(1, int(patience))
        self.cooldown = float(cooldown)
        self.on_detect = on_detect
        self._log = log
        self.debug = debug
        self.event = threading.Event()
        self.last_time = 0.0
        self.last_score = 0.0
        self.peak_score = 0.0
        self._hits = 0
        self._tail = 0
        self._buf = np.zeros(0, np.int16)
        self._buf_t = 0.0
        self._q = queue.Queue(maxsize=400)
        self._model = self._load(model, vad_threshold)
        self.name = os.path.splitext(os.path.basename(str(model)))[0]
        self._paused = False
        self.boost = 0.0   # raised while Yobi talks without echo cancellation
        threading.Thread(target=self._worker, daemon=True).start()

    # ---------------------------------------------------------------- load
    def _load(self, model, vad_threshold):
        from openwakeword.model import Model
        path = str(model)
        is_file = path.lower().endswith((".onnx", ".tflite"))
        if is_file and not os.path.exists(path):
            raise FileNotFoundError(f"موديل النداء مش موجود: {path}")
        kwargs = {"wakeword_models": [path]}
        if path.lower().endswith(".onnx") or not is_file:
            kwargs["inference_framework"] = "onnx"
        if vad_threshold and float(vad_threshold) > 0.0:
            kwargs["vad_threshold"] = float(vad_threshold)
        for attempt in range(2):
            try:
                try:
                    return Model(**kwargs)
                except TypeError:
                    kwargs.pop("inference_framework", None)
                    kwargs.pop("vad_threshold", None)
                    return Model(**kwargs)
            except Exception:
                if attempt == 0:
                    try:
                        import openwakeword.utils as owu
                        owu.download_models()
                        continue
                    except Exception:
                        pass
                raise

    # ---------------------------------------------------------------- API
    def feed(self, frame, t=None):
        if self._paused:
            return
        try:
            self._q.put_nowait((t or time.time(), np.asarray(frame, np.int16)))
        except queue.Full:
            pass

    def pause(self, paused=True):
        self._paused = bool(paused)
        if self._paused:
            self.reset()

    def reset(self):
        self.event.clear()
        self._hits = 0
        self._tail = 0
        self._buf = np.zeros(0, np.int16)
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        try:
            self._model.reset()
        except Exception:
            pass

    def set_threshold(self, v):
        self.threshold = float(v)

    # ------------------------------------------------------------- worker
    def _worker(self):
        while True:
            t, fr = self._q.get()
            if self._paused:
                continue
            if not self._buf.size:
                self._buf_t = t
            self._buf = np.concatenate([self._buf, fr])
            while self._buf.size >= CHUNK:
                chunk, self._buf = self._buf[:CHUNK], self._buf[CHUNK:]
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                if rms >= MIN_RMS:
                    self._tail = TAIL_CHUNKS
                elif self._tail > 0:
                    self._tail -= 1
                else:
                    self._hits = 0
                    continue

                try:
                    scores = self._model.predict(chunk)
                except Exception as e:
                    self._log(f"⚠️ wake word predict: {e}")
                    time.sleep(0.5)
                    continue

                s = max(scores.values()) if scores else 0.0
                self.last_score = float(s)
                self.peak_score = max(self.peak_score * 0.995, self.last_score)
                thr = min(0.95, self.threshold + self.boost)
                if (self.debug and s > 0.12) or (s >= thr * 0.65 and s > 0.22):
                    self._log(f"👂 [Wake] score={s:.2f} (المطلوب={thr:.2f})")
                self._hits = self._hits + 1 if s >= thr else 0
                if self._hits >= self.patience and t - self.last_time > self.cooldown:
                    self._hits = 0
                    self._tail = 0
                    self.last_time = t
                    self.event.set()
                    if self.on_detect:
                        try:
                            self.on_detect(s, t)
                        except Exception:
                            pass
                    try:
                        self._model.reset()
                    except Exception:
                        pass