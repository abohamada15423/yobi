# -*- coding: utf-8 -*-
"""
Audio Input v4 — ودان يوبي.

Fixes in v4:
  • Hybrid VAD (_is_speech): combines WebRTC VAD with adaptive RMS energy so
    quieter microphones aren't ignored by strict WebRTC VAD.
  • Smart Wake Hand-off: distinguishes between "يا يوبي" (pause) and
    "يا يوبي افتح سبوتيفاي" (continuous command in the same breath).
  • Hybrid Wake Fallback: if the user speaks a short phrase while waiting for
    the ONNX wake word (e.g. saying "يوبي" without "يا") and the ONNX model
    doesn't fire, `pop_wake_candidate()` lets `voice_loop` verify it with
    Whisper so calling Yobi never fails.
"""

import collections
import queue
import threading
import time

import numpy as np
import speech_recognition as sr

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None

try:
    import webrtcvad
    _HAS_WEBRTCVAD = True
except ImportError:
    _HAS_WEBRTCVAD = False

try:
    import latency
except Exception:  # pragma: no cover
    latency = None

try:
    from audio_io import unreferenced_playing as _unreferenced
except Exception:  # pragma: no cover
    def _unreferenced():
        return False

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000   # 480
SAMPLE_WIDTH = 2


class HotkeyPressed(Exception):
    """Raised by listen(..., hotkey_wakes=True) when the hotkey is hit."""


class _NullSource:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class VADRecognizer:
    def __init__(self, aggressiveness=2, end_silence_ms=600, preroll_ms=300,
                 min_speech_ms=180, hotkey="ctrl+alt+y", is_speaking=None,
                 stop_speaking=None, device=None, engine=None, wake=None,
                 barge_in="auto", verify_wake=None, log=print):
        self.end_silence_frames = max(1, end_silence_ms // FRAME_MS)
        self.preroll_frames = max(1, preroll_ms // FRAME_MS)
        self.min_speech_frames = max(1, min_speech_ms // FRAME_MS)
        self._vad = webrtcvad.Vad(aggressiveness) if _HAS_WEBRTCVAD else None
        self._vad_strict = webrtcvad.Vad(3) if _HAS_WEBRTCVAD else None
        self._noise_floor = 220.0
        self._is_speaking = is_speaking or (lambda: False)
        self._stop_speaking = stop_speaking or (lambda: None)
        self._log = log
        self.barge_in_check = None
        self.hotkey_event = threading.Event()
        self.engine = engine
        self.wake = wake
        self.barge_in = barge_in
        self.verify_wake = verify_wake

        self._frames = queue.Queue(maxsize=2000)
        self._replay = collections.deque()
        self._history = collections.deque(maxlen=int(4000 / FRAME_MS))
        self._acc = np.zeros(0, np.int16)
        self._acc_t = 0.0
        self._keep_from = None
        self._heard_until = None    # the time of the last frame of the last clip handed out
        self._stream = None

        # Track short speech bursts while waiting for ONNX wake word
        self._idle_voiced = []
        self._idle_silence = 0
        self._wake_candidate = None

        if engine is not None:
            engine.subscribe(self._on_engine_frame)
        else:
            if sd is None:
                raise ImportError("pip install sounddevice")
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=FRAME_SAMPLES, device=device, callback=self._on_audio,
            )
            self._stream.start()

        self._hotkey = None         # hotkey.Watcher, made on first use
        self.on_hotkey = None       # called the moment the wake key goes down (the agent's chime)
        self.key_pressed = False    # the wake was the key itself, not the island's Talk button
        self.key_time = 0.0         # when the key last went down
        self.key_capturing = False  # listen_until_key() is recording: the next press ends it
        self.set_hotkey(hotkey)

    def set_hotkey(self, hotkey):
        """Watch this wake key, replacing the one before it (the settings window changes it live)."""
        try:
            if self._hotkey is None:
                import hotkey as hk
                self._hotkey = hk.Watcher(self._on_hotkey)
            if self._hotkey.set(hotkey):
                return True
            print(f"⚠️ hotkey '{hotkey}' مش زرار معروف")
        except Exception as e:
            print(f"⚠️ hotkey '{hotkey}' مش متسجل: {e}")
        return False

    # ── sr-compatible surface ───────────────────────────────────

    def microphone(self):
        return _NullSource()

    @property
    def has_wake_model(self):
        return self.wake is not None

    @property
    def full_duplex(self):
        return bool(self.engine is not None and getattr(self.engine, "aec_active", False))

    def adjust_for_ambient_noise(self, source=None, duration=1.0):
        """Measure the room's noise floor."""
        self._drain()
        n = max(1, int(duration * 1000 / FRAME_MS))
        levels = []
        for _ in range(n):
            try:
                levels.append(self._rms(self._get(timeout=1.0)[1]))
            except queue.Empty:
                break
        if levels:
            self._noise_floor = float(np.clip(np.percentile(levels, 80), 120.0, 900.0))

    def pop_wake_candidate(self):
        """Return a captured short speech clip (sr.AudioData) if the user spoke
        while waiting for the ONNX wake model, else None."""
        c, self._wake_candidate = self._wake_candidate, None
        return c

    def wait_for_wake(self, hotkey_wakes=True, timeout=None):
        """Block until the offline wake word fires (True) or timeout (False).
        Also collects short speech bursts into `_wake_candidate` so `voice_loop`
        can fall back to Whisper if the user said 'يوبي' without 'يا'."""
        if self.wake is None:
            raise RuntimeError("no wake word model")
        if not hotkey_wakes:
            self.hotkey_event.clear()
            self.key_pressed = False
        start = time.time()
        if self.wake.event.is_set() and self.wake.last_time < start - 1.0:
            self.wake.event.clear()
        while True:
            if hotkey_wakes and self.hotkey_event.is_set():
                self.hotkey_event.clear()
                self._idle_voiced.clear()
                raise HotkeyPressed()
            if timeout is not None and time.time() - start > timeout:
                return False
            self.wake.boost = 0.20 if (self._is_speaking() and not self.full_duplex) else 0.0
            if not self.wake.event.wait(0.04):
                self._scan_idle_speech()
                if self._wake_candidate is not None:
                    return False
                continue
            self.wake.event.clear()
            self._idle_voiced.clear()
            self._wake_candidate = None
            t_hit = self.wake.last_time
            if self._is_speaking() and self.barge_in != "off":
                self._stop_speaking()
            if self.verify_wake is not None:
                clip = self._recent_audio(seconds=1.8, until=t_hit + 0.15)
                try:
                    ok = bool(self.verify_wake(clip))
                except Exception:
                    ok = True
                if not ok:
                    self._log(f"🤔 نداء مش مؤكد (score {self.wake.last_score:.2f}) — اتجاهل")
                    continue
            # Keep only frames AFTER the wake word hit (+0.12s) so the wake word
            # itself doesn't get re-captured as an empty command
            self._keep_from = t_hit + 0.12
            return True

    def wait_for_key(self, timeout=1.0):
        """Wake by key only (Settings → wake: key): no model listens while Yobi
        sleeps, old audio is just dropped. True when the hotkey (or the island) was pressed."""
        end = time.time() + timeout
        while time.time() < end:
            if self.hotkey_event.wait(0.05):
                self.hotkey_event.clear()
                self._idle_voiced.clear()
                self._wake_candidate = None
                return True
            self._drop_stale()
        return False

    def keep_what_follows(self):
        """The clip just handed out was only the wake word ("يا يوبي", a breath, then the
        command): the next listen() starts where it ended, so what was said while the wake
        word was being checked isn't thrown away as old audio."""
        if self._heard_until is not None:
            self._keep_from = self._heard_until

    def take_key_press(self):
        """True once after the wake key itself was pressed (the island's Talk button sets only
        the event): the agent then records until the key is pressed again."""
        pressed, self.key_pressed = self.key_pressed, False
        return pressed

    def listen_until_key(self, max_seconds=60, no_speech_timeout=10):
        """Record from the wake key press until the key is pressed again: silence doesn't end
        it, so a pause to think is fine. `max_seconds` ends it anyway; nothing said within
        `no_speech_timeout` (or by the second press) raises sr.WaitTimeoutError."""
        self.hotkey_event.clear()
        self.key_pressed = False
        self._keep_from = None
        pressed_at = self.key_time if time.time() - self.key_time < 5 else time.time()
        self._drop_before(pressed_at)
        self.key_capturing = True
        start = time.time()
        frames, speech = [], 0
        try:
            while not self.hotkey_event.is_set():
                waited = time.time() - start
                if waited > max_seconds or (speech < self.min_speech_frames and waited > no_speech_timeout):
                    break
                try:
                    _, frame = self._get(timeout=0.05)
                except queue.Empty:
                    continue
                frames.append(frame)
                if self._is_speech(frame):
                    speech += 1
        finally:
            self.key_capturing = False
            self.hotkey_event.clear()
            self.key_pressed = False
        if speech < self.min_speech_frames:
            raise sr.WaitTimeoutError("nothing said before the key was pressed again")
        if latency is not None:
            latency.start_turn(time.perf_counter(), speech_ms=speech * FRAME_MS)
        return sr.AudioData(b"".join(frames), SAMPLE_RATE, SAMPLE_WIDTH)

    def _scan_idle_speech(self):
        """Drain old frames while watching for a short spoken wake phrase."""
        if self._is_speaking():
            self._idle_voiced.clear()
            self._trim_queue()
            return
        max_idle_frames = int(3200 / FRAME_MS)
        while True:
            try:
                t, fr = self._frames.get_nowait()
            except queue.Empty:
                break
            if self._is_speech(fr):
                self._idle_voiced.append(fr)
                self._idle_silence = 0
                if len(self._idle_voiced) > max_idle_frames:
                    # Too long to be a wake word — discard
                    self._idle_voiced.clear()
            elif self._idle_voiced:
                self._idle_voiced.append(fr)
                self._idle_silence += 1
                if self._idle_silence >= self.end_silence_frames:
                    speech_len = len(self._idle_voiced) - self._idle_silence
                    if self.min_speech_frames <= speech_len <= max_idle_frames:
                        self._heard_until = t
                        pcm = b"".join(self._idle_voiced)
                        self._wake_candidate = sr.AudioData(pcm, SAMPLE_RATE, SAMPLE_WIDTH)
                    self._idle_voiced.clear()
                    self._idle_silence = 0
                    break

    def listen(self, source=None, timeout=None, phrase_time_limit=None,
               hotkey_wakes=False):
        """Block until one utterance is captured."""
        if not hotkey_wakes:
            self.hotkey_event.clear()
            self.key_pressed = False
        keep_from, self._keep_from = self._keep_from, None
        if keep_from is None:
            if self._wait_for_tts_to_finish(hotkey_wakes):
                keep_from, self._keep_from = self._keep_from, None
        if keep_from is not None:
            self._drop_before(keep_from)
        else:
            self._drop_stale()

        start = time.time()
        ring = collections.deque(maxlen=self.preroll_frames)
        voiced, silence_run, speech_frames = [], 0, 0
        triggered = False
        max_frames = int((phrase_time_limit or 30) * 1000 / FRAME_MS)

        while True:
            if hotkey_wakes and self.hotkey_event.is_set():
                self.hotkey_event.clear()
                raise HotkeyPressed()
            try:
                t_frame, frame = self._get(timeout=0.1)
            except queue.Empty:
                frame = None

            if not triggered:
                if timeout is not None and time.time() - start > timeout:
                    raise sr.WaitTimeoutError("listening timed out")
                if frame is None:
                    continue
                ring.append(frame)
                if self._is_speech(frame):
                    speech_frames += 1
                    if speech_frames >= 2:          # ~60ms of voice → start
                        triggered = True
                        voiced.extend(ring)
                        ring.clear()
                else:
                    speech_frames = max(0, speech_frames - 1)
                continue

            if frame is None:
                continue
            voiced.append(frame)
            if self._is_speech(frame):
                silence_run = 0
            else:
                silence_run += 1
            if silence_run >= self.end_silence_frames or len(voiced) >= max_frames:
                break

        if len(voiced) - silence_run < self.min_speech_frames:
            remaining = None if timeout is None else max(0.5, timeout - (time.time() - start))
            return self.listen(source, remaining, phrase_time_limit, hotkey_wakes)

        self._heard_until = t_frame
        if latency is not None:
            latency.start_turn(time.perf_counter(),
                               speech_ms=(len(voiced) - silence_run) * FRAME_MS)
        pcm = b"".join(voiced)
        return sr.AudioData(pcm, SAMPLE_RATE, SAMPLE_WIDTH)

    # ── Internal: frame plumbing ────────────────────────────────

    def _put(self, t, frame):
        self._history.append((t, frame))
        try:
            self._frames.put_nowait((t, frame))
        except queue.Full:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                pass

    def _get(self, timeout=0.1):
        if self._replay:
            return self._replay.popleft()
        return self._frames.get(timeout=timeout)

    def _on_audio(self, indata, frames, time_info, status):
        """Own-stream mode (no AudioEngine)."""
        t = time.time()
        frame = bytes(indata)
        self._put(t, frame)
        if self.wake is not None:
            self.wake.feed(np.frombuffer(frame, np.int16), t)

    def _on_engine_frame(self, frame10, t):
        """AudioEngine mode: 10 ms cleaned frames → 30 ms VAD frames."""
        if self.wake is not None:
            self.wake.feed(frame10, t)
        if not self._acc.size:
            self._acc_t = t
        self._acc = np.concatenate([self._acc, frame10])
        while self._acc.size >= FRAME_SAMPLES:
            fr, self._acc = self._acc[:FRAME_SAMPLES], self._acc[FRAME_SAMPLES:]
            self._put(self._acc_t, fr.tobytes())
            self._acc_t = t

    def _on_hotkey(self):
        self.key_time = time.time()
        self.key_pressed = True
        try:
            if self.on_hotkey is not None:
                self.on_hotkey()
            self._stop_speaking()
        finally:
            self.hotkey_event.set()     # a failing chime must not swallow the press

    def _drain(self):
        self._replay.clear()
        self._idle_voiced.clear()
        self._wake_candidate = None
        while True:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                return

    def _trim_queue(self, keep_s=1.0):
        if self._frames.qsize() * FRAME_MS / 1000.0 > keep_s * 2:
            self._drop_before(time.time() - keep_s)

    def _drop_before(self, cutoff):
        kept = [it for it in self._replay if it[0] >= cutoff]
        self._replay.clear()
        while True:
            try:
                item = self._frames.get_nowait()
            except queue.Empty:
                break
            if item[0] >= cutoff:
                kept.append(item)
        self._replay.extend(kept)

    def _drop_stale(self):
        self._drop_before(time.time() - self.preroll_frames * FRAME_MS / 1000.0)

    def _recent_audio(self, seconds=1.8, until=None):
        until = until or time.time()
        frames = [f for (t, f) in list(self._history) if until - seconds <= t <= until]
        return sr.AudioData(b"".join(frames), SAMPLE_RATE, SAMPLE_WIDTH)

    # ── Internal: talking over Yobi ──────────────────────────────

    def _wait_for_tts_to_finish(self, hotkey_wakes):
        if not self._is_speaking():
            return False
        use_wake = self.wake is not None and self.barge_in in ("auto", "wake")
        use_speech = self.full_duplex and self.barge_in in ("auto", "speech")
        if use_wake:
            self.wake.event.clear()
            self.wake.boost = 0.0 if self.full_duplex else 0.20
        try:
            return self._tts_wait_loop(hotkey_wakes, use_wake, use_speech)
        finally:
            if self.wake is not None:
                self.wake.boost = 0.0

    def _tts_wait_loop(self, hotkey_wakes, use_wake, use_speech):
        recent = collections.deque(maxlen=12)
        held = collections.deque(maxlen=int(1500 / FRAME_MS))
        floor = 200.0
        while self._is_speaking():
            if self.hotkey_event.is_set():
                if not hotkey_wakes:
                    self.hotkey_event.clear()
                return False
            if use_wake and self.wake.event.is_set():
                self.wake.event.clear()
                self._stop_speaking()
                self._log("✋ قاطعتني بالنداء")
                self._keep_from = self.wake.last_time + 0.10
                return True
            if use_speech:
                try:
                    item = self._get(timeout=0.05)
                except queue.Empty:
                    continue
                held.append(item)
                fr = item[1]
                if _unreferenced():
                    recent.append(False)
                    continue
                rms = self._rms(fr)
                strict = self._is_speech(fr, strict=True)
                if not strict:
                    floor = floor * 0.95 + rms * 0.05
                need = max(500.0, floor * 3.0)
                erle = getattr(self.engine, "erle_db", None)
                if erle is not None and erle < 10:
                    need *= 1.7
                recent.append(strict and rms > need)
                if len(recent) >= 10 and sum(recent) >= 8:
                    self._stop_speaking()
                    self._log("✋ قاطعتني (full-duplex)")
                    start = len(held) - len(recent) - self.preroll_frames
                    self._replay.extendleft(reversed(list(held)[max(0, start):]))
                    self._keep_from = 0.0
                    return True
                continue
            if not use_wake and self.barge_in_check is not None:
                try:
                    audio = self._listen_raw(max_seconds=4)
                except Exception:
                    continue
                if audio is not None and self._is_speaking() and self.barge_in_check(audio):
                    self._stop_speaking()
                    return False
                continue
            time.sleep(0.05)
        if not self.full_duplex:
            time.sleep(0.15)
            self._drain()
        return False

    def _listen_raw(self, max_seconds=4):
        voiced, silence_run, started = [], 0, False
        deadline = time.time() + max_seconds + 2
        while time.time() < deadline and self._is_speaking():
            try:
                _, frame = self._get(timeout=0.1)
            except queue.Empty:
                continue
            sp = self._is_speech(frame)
            if not started:
                if sp:
                    started = True
                    voiced.append(frame)
                continue
            voiced.append(frame)
            silence_run = 0 if sp else silence_run + 1
            if silence_run >= self.end_silence_frames or len(voiced) * FRAME_MS >= max_seconds * 1000:
                break
        if len(voiced) < self.min_speech_frames:
            return None
        return sr.AudioData(b"".join(voiced), SAMPLE_RATE, SAMPLE_WIDTH)

    @staticmethod
    def _rms(frame):
        a = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a * a))) if a.size else 0.0

    def _is_speech(self, frame, strict=False):
        if len(frame) != FRAME_SAMPLES * SAMPLE_WIDTH:
            return False
        rms = self._rms(frame)
        vad = self._vad_strict if strict else self._vad
        if vad is not None:
            try:
                if vad.is_speech(frame, SAMPLE_RATE):
                    return rms > 95.0
            except Exception:
                pass
        # Fallback to RMS energy so softer microphones still trigger reliably
        return rms > max(220.0 if not strict else 380.0,
                         self._noise_floor * (2.4 if strict else 1.65))