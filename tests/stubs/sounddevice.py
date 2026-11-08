"""Fake sounddevice: real-time threads, a scriptable mic and an acoustic echo path."""
import threading, time
import numpy as np

class _TI:
    def __init__(self, now, adc=None, dac=None):
        self.currentTime = now; self.inputBufferAdcTime = adc if adc is not None else now - 0.01
        self.outputBufferDacTime = dac if dac is not None else now + 0.02

MIC = {"source": None, "echo_gain": 0.0, "echo_delay": 0.06}
SPEAKER = []            # list of (t, int16 array @48k)
_lock = threading.Lock()

def speaker_16k_since(t0):
    with _lock:
        chunks = [c for (t, c) in SPEAKER if t >= t0]
    if not chunks: return np.zeros(0, np.int16)
    x = np.concatenate(chunks)
    return x[::3]

class _Base:
    def __init__(self, samplerate=16000, channels=1, dtype="int16", blocksize=160, device=None, callback=None):
        self.sr = samplerate; self.bs = blocksize; self.cb = callback; self._stop = threading.Event(); self._t=None
    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True); self._t.start()
    def stop(self): self._stop.set()
    def close(self): self._stop.set()
    @property
    def latency(self): return 0.02

class InputStream(_Base):
    _n = 0
    def _run(self):
        period = self.bs / self.sr; nxt = time.time()
        while not self._stop.is_set():
            now = time.time()
            src = MIC["source"]
            x = src(self.bs, now) if src else np.zeros(self.bs, np.float32)
            x = np.asarray(x, np.float32)
            g = MIC["echo_gain"]
            MIC["last_echo"] = np.zeros(self.bs, np.float32)
            if g:
                with _lock:
                    past = [c for (t, c) in SPEAKER if now - MIC["echo_delay"] - 0.05 <= t <= now - MIC["echo_delay"]]
                if past:
                    e = np.concatenate(past)[::3][-self.bs:]
                    echo = np.zeros(self.bs, np.float32); echo[-len(e):] = g * e
                    MIC["last_echo"] = echo
                    x = x + echo
            buf = np.clip(x, -32768, 32767).astype(np.int16).reshape(-1, 1)
            self.cb(buf, self.bs, _TI(now), None)
            nxt += period; time.sleep(max(0, nxt - time.time()))

class OutputStream(_Base):
    def _run(self):
        period = self.bs / self.sr; nxt = time.time()
        while not self._stop.is_set():
            now = time.time()
            out = np.zeros((self.bs, 1), np.int16)
            self.cb(out, self.bs, _TI(now), None)
            with _lock:
                SPEAKER.append((now, out[:, 0].copy()))
                if len(SPEAKER) > 3000: del SPEAKER[:1000]
            nxt += period; time.sleep(max(0, nxt - time.time()))
