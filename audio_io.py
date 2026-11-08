# -*- coding: utf-8 -*-
"""
Audio I/O engine — المايك والسماعة في مكان واحد عشان نلغي الصدى.

Why: to cancel echo, the canceller must see *exactly* what the speaker is
playing (the "reference") next to what the mic hears. So Yobi's voice (and
sound effects) are played through this engine instead of pygame/winsound,
and every mic frame is cleaned before VAD / wake word / Whisper see it.

    mic 16 kHz ─▶ [WebRTC AEC3 + NS + HPF] ─▶ subscribers (VAD, wake word)
                          ▲
    TTS / fx ─▶ 48 kHz speaker ─▶ ↓3 to 16 kHz ─▶ reverse stream (reference)

Echo canceller: WebRTC APM shipped in `pip install livekit` (Windows
wheels, no compiler). Without it the engine still works; Yobi just falls
back to "don't listen while talking, except the wake word".

Public:
    eng = get_audio_engine(create=True, aec=True, ...)
    eng.subscribe(cb)                # cb(frame_int16[160], t) cleaned 10 ms
    eng.subscribe(cb, raw=True)      # raw mic (diagnostics)
    eng.play(pcm_int16, sr, stop_event=None) -> bool   # blocking, speech
    eng.play_fx(pcm_int16, sr)       # non-blocking, mixed on top
    eng.stop_playback()
    eng.is_playing() / eng.aec_active / eng.has_output
"""

import math
import threading
import time

import numpy as np

try:
    import sounddevice as sd
    _HAS_SD = True
except Exception:  # pragma: no cover
    sd = None
    _HAS_SD = False

try:
    from livekit import rtc as _rtc
    _HAS_APM = hasattr(_rtc, "AudioProcessingModule")
except Exception:
    _rtc = None
    _HAS_APM = False

try:
    from scipy.signal import resample_poly as _resample_poly
except Exception:
    _resample_poly = None

IN_SR = 16000
IN_BLOCK = 160            # 10 ms (APM requirement)
OUT_SR = 48000
OUT_BLOCK = 480           # 10 ms


# ============================================================================
# DSP helpers
# ============================================================================
def resample(pcm, sr_in, sr_out):
    """int16 mono resample (polyphase if scipy is present, else linear)."""
    pcm = np.asarray(pcm)
    if sr_in == sr_out or pcm.size == 0:
        return pcm.astype(np.int16, copy=False)
    x = pcm.astype(np.float32)
    if _resample_poly is not None:
        g = math.gcd(int(sr_in), int(sr_out))
        y = _resample_poly(x, int(sr_out) // g, int(sr_in) // g)
    else:
        n = int(round(x.size * sr_out / sr_in))
        y = np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x)
    return np.clip(y, -32768, 32767).astype(np.int16)


def _lowpass(taps, cutoff):
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff * n) * np.blackman(taps)
    return (h / h.sum()).astype(np.float32)


class Decimator:
    """Streaming integer-factor decimator (48 kHz → 16 kHz for the AEC
    reference). Keeps filter state + phase across arbitrary block sizes."""

    def __init__(self, factor=3, taps=63):
        self.f = factor
        self.h = _lowpass(taps, 0.45 / factor)
        self.hist = np.zeros(taps - 1, np.float32)
        self.phase = 0

    def process(self, x):
        x = np.asarray(x, np.float32)
        buf = np.concatenate([self.hist, x])
        y = np.convolve(buf, self.h, mode="valid")          # len == len(x)
        out = y[self.phase::self.f]
        self.phase = (self.phase - len(x)) % self.f
        self.hist = buf[-(len(self.h) - 1):]
        return np.clip(out, -32768, 32767).astype(np.int16)


def tone(freqs, dur_ms, sr=OUT_SR, vol=0.22):
    """Soft sine chime (used by sounds.py so effects go through AEC too)."""
    out = []
    for f, d in zip(freqs, dur_ms if isinstance(dur_ms, (list, tuple)) else [dur_ms] * len(freqs)):
        n = int(sr * d / 1000)
        t = np.arange(n) / sr
        env = np.minimum(1, np.minimum(t / 0.008, (n / sr - t) / 0.03).clip(0, 1))
        out.append(np.sin(2 * np.pi * f * t) * env)
    y = np.concatenate(out) if out else np.zeros(0)
    return (y * vol * 32767).astype(np.int16)


# ============================================================================
# Engine
# ============================================================================
class AudioEngine:
    def __init__(self, aec=True, noise_suppression=True, high_pass=True, agc=False,
                 input_device=None, output_device=None, log=print, extra_delay_ms=0):
        if not _HAS_SD:
            raise RuntimeError("sounddevice مش متسطب")
        self._log = log
        self._subs, self._raw_subs = [], []
        self._sub_lock = threading.Lock()
        self._extra_delay = extra_delay_ms

        self._apm = None
        if aec or noise_suppression:
            if _HAS_APM:
                try:
                    self._apm = _rtc.AudioProcessingModule(
                        echo_cancellation=bool(aec), noise_suppression=bool(noise_suppression),
                        high_pass_filter=bool(high_pass), auto_gain_control=bool(agc))
                except Exception as e:
                    log(f"⚠️ WebRTC APM فشل: {e}")
            elif aec:
                log("ℹ️ إلغاء الصدى محتاج: pip install livekit — يوبي هيشتغل بالطريقة القديمة")
        self.aec_active = bool(self._apm is not None and aec)

        # playback state
        self._play_lock = threading.Lock()
        self._speech = np.zeros(0, np.int16)
        self._fx = np.zeros(0, np.int16)
        self._drained = threading.Event()
        self._drained.set()
        self._last_audible = 0.0
        self._first_sample_cb = None
        self._dec = Decimator(OUT_SR // IN_SR)
        self._ref_acc = np.zeros(0, np.int16)
        self._in_acc = np.zeros(0, np.int16)
        self._out_delay = 0.0
        self._in_delay = 0.0
        self.level = 0.0
        self.erle_db = None           # rough echo reduction while playing
        self._erle_acc = [0.0, 0.0]

        self._in = sd.InputStream(samplerate=IN_SR, channels=1, dtype="int16",
                                  blocksize=IN_BLOCK, device=input_device,
                                  callback=self._on_input)
        self._out = None
        try:
            self._out = sd.OutputStream(samplerate=OUT_SR, channels=1, dtype="int16",
                                        blocksize=OUT_BLOCK, device=output_device,
                                        callback=self._on_output)
            self._out.start()
        except Exception as e:
            log(f"⚠️ مش قادر أفتح السماعة من محرك الصوت ({e}) — الصوت هيرجع لـ pygame")
            self._out = None
            self.aec_active = False
        self._in.start()

    # ------------------------------------------------------------ public
    @property
    def has_output(self):
        return self._out is not None

    def subscribe(self, cb, raw=False):
        with self._sub_lock:
            (self._raw_subs if raw else self._subs).append(cb)

    def unsubscribe(self, cb):
        with self._sub_lock:
            for lst in (self._subs, self._raw_subs):
                if cb in lst:
                    lst.remove(cb)

    def play(self, pcm, sr, stop_event=None, on_start=None, timeout=120):
        """Queue speech and block until it finished (True) or was stopped (False)."""
        if self._out is None:
            raise RuntimeError("no output stream")
        data = resample(pcm, sr, OUT_SR)
        if data.size == 0:
            return True
        with self._play_lock:
            self._speech = np.concatenate([self._speech, data])
            self._drained.clear()
            if on_start is not None:
                self._first_sample_cb = on_start
        end = time.time() + timeout
        while not self._drained.wait(0.02):
            if stop_event is not None and stop_event.is_set():
                self.stop_playback()
                return False
            if time.time() > end:
                self.stop_playback()
                return False
        return True

    def play_fx(self, pcm, sr):
        if self._out is None:
            raise RuntimeError("no output stream")
        data = resample(pcm, sr, OUT_SR)
        with self._play_lock:
            if self._fx.size < data.size:
                self._fx = np.concatenate([self._fx, np.zeros(data.size - self._fx.size, np.int16)])
            mix = self._fx[:data.size].astype(np.int32) + data
            self._fx[:data.size] = np.clip(mix, -32768, 32767)

    def stop_playback(self):
        with self._play_lock:
            self._speech = np.zeros(0, np.int16)
            self._first_sample_cb = None
            self._drained.set()

    def is_playing(self):
        with self._play_lock:
            if self._speech.size:
                return True
        return time.time() - self._last_audible < 0.12

    def close(self):
        for s in (self._in, self._out):
            try:
                if s is not None:
                    s.stop()
                    s.close()
            except Exception:
                pass

    # ---------------------------------------------------------- callbacks
    def _on_output(self, outdata, frames, time_info, status):
        cb = None
        with self._play_lock:
            sp = self._speech[:frames]
            self._speech = self._speech[frames:]
            fx = self._fx[:frames]
            self._fx = self._fx[frames:]
            if sp.size and self._first_sample_cb is not None:
                cb, self._first_sample_cb = self._first_sample_cb, None
            if not self._speech.size:
                self._drained.set()
        chunk = np.zeros(frames, np.int32)
        if sp.size:
            chunk[:sp.size] += sp
        if fx.size:
            chunk[:fx.size] += fx
        chunk = np.clip(chunk, -32768, 32767).astype(np.int16)
        outdata[:, 0] = chunk
        if sp.size or fx.size:
            self._last_audible = time.time()
        try:
            self._out_delay = max(0.0, float(time_info.outputBufferDacTime - time_info.currentTime))
        except Exception:
            pass
        if cb is not None:
            try:
                cb()
            except Exception:
                pass
        if self._apm is not None:
            ref = self._dec.process(chunk)
            self._ref_acc = np.concatenate([self._ref_acc, ref])
            while self._ref_acc.size >= IN_BLOCK:
                fr, self._ref_acc = self._ref_acc[:IN_BLOCK], self._ref_acc[IN_BLOCK:]
                try:
                    self._apm.process_reverse_stream(
                        _rtc.AudioFrame(fr.tobytes(), IN_SR, 1, IN_BLOCK))
                except Exception:
                    pass

    def _on_input(self, indata, frames, time_info, status):
        now = time.time()
        pcm = np.asarray(indata[:, 0], dtype=np.int16)
        self._in_acc = np.concatenate([self._in_acc, pcm])
        try:
            self._in_delay = max(0.0, float(time_info.currentTime - time_info.inputBufferAdcTime))
        except Exception:
            pass
        while self._in_acc.size >= IN_BLOCK:
            raw, self._in_acc = self._in_acc[:IN_BLOCK].copy(), self._in_acc[IN_BLOCK:]
            clean = raw
            if self._apm is not None:
                try:
                    if self.aec_active:
                        self._apm.set_stream_delay_ms(
                            int((self._in_delay + self._out_delay) * 1000) + self._extra_delay)
                    fr = _rtc.AudioFrame(raw.tobytes(), IN_SR, 1, IN_BLOCK)
                    self._apm.process_stream(fr)
                    clean = np.frombuffer(bytes(fr.data), dtype=np.int16).copy()
                except Exception:
                    clean = raw
            if self.aec_active and self.is_playing():
                r = float(np.mean(raw.astype(np.float32) ** 2))
                c = float(np.mean(clean.astype(np.float32) ** 2))
                a = self._erle_acc
                a[0] = a[0] * 0.98 + r
                a[1] = a[1] * 0.98 + c
                if a[0] > 1e3:
                    self.erle_db = 10 * math.log10((a[0] + 1) / (a[1] + 1))
            self.level = self.level * 0.8 + 0.2 * min(1.0, float(np.sqrt(np.mean(
                clean.astype(np.float32) ** 2))) / 3000.0)
            with self._sub_lock:
                subs, raws = list(self._subs), list(self._raw_subs)
            for cb in raws:
                try:
                    cb(raw, now)
                except Exception:
                    pass
            for cb in subs:
                try:
                    cb(clean, now)
                except Exception:
                    pass


# ============================================================================
# Playback that bypasses the engine (pygame/winsound fallback): the echo
# canceller has no reference for it, so full-duplex barge-in must pause.
# ============================================================================
_unref = threading.Event()


def set_unreferenced(on):
    (_unref.set if on else _unref.clear)()


def unreferenced_playing():
    return _unref.is_set()


# ============================================================================
# Singleton
# ============================================================================
_engine = None
_engine_lock = threading.Lock()


def get_audio_engine(create=False, **kwargs):
    """Return the shared engine (create=True builds it once; failures -> None)."""
    global _engine
    with _engine_lock:
        if _engine is None and create:
            try:
                _engine = AudioEngine(**kwargs)
            except Exception as e:
                (kwargs.get("log") or print)(f"⚠️ محرك الصوت مشتغلش: {e}")
                _engine = None
        return _engine


def set_audio_engine(engine):
    """For tests / custom setups."""
    global _engine
    with _engine_lock:
        _engine = engine
