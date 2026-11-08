# -*- coding: utf-8 -*-
"""
TTS Engine v3 — يوبي يتكلم أونلاين وأوفلاين.

New in v3:
  • Two voices:
        edge  — Microsoft Edge neural (ar-EG Salma/Shakir), needs internet
        piper — Piper neural TTS, 100% offline (Arabic voice ar_JO-kareem)
    backend = "auto" (default): Edge, and Piper the moment Edge fails or the
    internet drops (Edge is skipped for 60 s after a failure, so there's no
    waiting on every sentence). Choose it in Settings → الصوت, or
    get_tts_engine().set_backend("auto" | "edge" | "piper").
  • Plays through the shared AudioEngine when present, so the echo
    canceller knows exactly what Yobi is saying (full-duplex barge-in).
    Falls back to pygame exactly like v2.
  • Latency marks: tts_request → tts_ready → first_audio (latency.py).

Kept from v2: pipelined synth/playback, instant stop(), LRU cache for short
phrases, is_speaking() / wait_until_done().

Public API (backward-compatible):
    speak(text) / speak_sync(text) / stop_speaking() / is_speaking()
    get_tts_engine() → set_enabled / set_voice / is_enabled / set_backend /
                       backend / status()
"""

import asyncio
import io
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import wave
from collections import OrderedDict

import numpy as np

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False

try:
    import miniaudio
    _HAS_MINIAUDIO = True
except ImportError:
    _HAS_MINIAUDIO = False

try:
    import audio_io
except Exception:  # pragma: no cover
    audio_io = None

try:
    import latency
except Exception:  # pragma: no cover
    latency = None

_HERE = os.path.dirname(os.path.abspath(__file__))
PREFS_PATH = os.path.join(_HERE, "tts_prefs.json")

DEFAULT_VOICE = "ar-EG-SalmaNeural"    # Egyptian Arabic female
FALLBACK_VOICE = "ar-EG-ShakirNeural"  # Egyptian Arabic male
RATE = "+10%"
VOLUME = "+0%"
DEFAULT_PIPER_MODEL = os.path.join(_HERE, "voices", "ar_JO-kareem-medium.onnx")
BACKENDS = ("auto", "edge", "piper")

_CACHE_MAX_ITEMS = 64
_CACHE_MAX_CHARS = 40   # only cache short phrases
_EDGE_TIMEOUT = 8.0
_EDGE_COOLDOWN = 60.0

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F" "\U0001F300-\U0001F5FF" "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF" "\U00002702-\U000027B0" "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff" "\u2640-\u2642" "\u2600-\u2B55"
    "\u200d" "\u23cf" "\u23e9" "\u231a" "\ufe0f" "\u3030"
    "]+",
    flags=re.UNICODE,
)
_MD_RE = re.compile(r"[*_`#>\[\]|~]+")


def _mark(name, info=None):
    if latency is not None:
        latency.mark(name, info=info)


def _load_prefs():
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_prefs(p):
    try:
        with open(PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================================
# Decoding helpers
# ============================================================================
def decode_mp3(data):
    """mp3 bytes -> (int16 mono ndarray, sample_rate) or None."""
    if _HAS_MINIAUDIO:
        try:
            d = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                                 nchannels=1, sample_rate=24000)
            return np.frombuffer(d.samples, dtype=np.int16).copy(), d.sample_rate
        except Exception:
            pass
    if _HAS_PYGAME:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, size=-16, channels=1)
            freq, _size, ch = pygame.mixer.get_init()
            snd = pygame.mixer.Sound(file=io.BytesIO(data))
            arr = pygame.sndarray.array(snd)
            if arr.ndim == 2:
                arr = arr.mean(axis=1)
            return np.asarray(arr, dtype=np.int16), int(freq)
        except Exception:
            pass
    return None


def pcm_to_wav(pcm, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(np.asarray(pcm, np.int16).tobytes())
    return buf.getvalue()


# ============================================================================
# Piper (offline)
# ============================================================================
class PiperBackend:
    def __init__(self, model_path=DEFAULT_PIPER_MODEL, length_scale=None, exe=None):
        self.model_path = model_path
        self.length_scale = length_scale
        self.exe = exe
        self._voice = None
        self._lock = threading.Lock()
        self._sr = None
        self.error = None

    def configure(self, model_path=None, length_scale=None, exe=None):
        if model_path and model_path != self.model_path:
            self.model_path = model_path
            self._voice = None
        if length_scale is not None:
            self.length_scale = length_scale
        if exe:
            self.exe = exe

    @property
    def available(self):
        if not self.model_path or not os.path.exists(self.model_path):
            return False
        try:
            import piper  # noqa: F401
            return True
        except Exception:
            return bool(self._find_exe())

    def _find_exe(self):
        if self.exe and os.path.exists(self.exe):
            return self.exe
        for name in ("piper", "piper.exe"):
            p = shutil.which(name) or os.path.join(_HERE, "piper", name)
            if p and os.path.exists(p):
                return p
        return None

    def _sample_rate(self):
        if self._sr:
            return self._sr
        try:
            with open(self.model_path + ".json", "r", encoding="utf-8") as f:
                self._sr = int(json.load(f)["audio"]["sample_rate"])
        except Exception:
            self._sr = 22050
        return self._sr

    def _load(self):
        with self._lock:
            if self._voice is None:
                from piper import PiperVoice
                self._voice = PiperVoice.load(self.model_path)
            return self._voice

    def synth(self, text):
        """-> (int16 ndarray, sr)"""
        try:
            voice = self._load()
        except Exception as e:
            exe = self._find_exe()
            if not exe:
                self.error = str(e)
                raise
            return self._synth_exe(exe, text)
        sr = getattr(getattr(voice, "config", None), "sample_rate", None) or self._sample_rate()
        parts = []
        if hasattr(voice, "synthesize_stream_raw"):            # piper-tts <= 1.2
            kw = {"length_scale": self.length_scale} if self.length_scale else {}
            for b in voice.synthesize_stream_raw(text, **kw):
                parts.append(np.frombuffer(b, dtype=np.int16))
        else:                                                 # piper-tts >= 1.3
            syn = None
            if self.length_scale:
                try:
                    from piper import SynthesisConfig
                    syn = SynthesisConfig(length_scale=self.length_scale)
                except Exception:
                    syn = None
            for chunk in voice.synthesize(text, syn_config=syn) if syn else voice.synthesize(text):
                sr = getattr(chunk, "sample_rate", sr)
                parts.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16))
        pcm = np.concatenate(parts) if parts else np.zeros(0, np.int16)
        return pcm, int(sr)

    def _synth_exe(self, exe, text):
        args = [exe, "--model", self.model_path, "--output-raw"]
        if self.length_scale:
            args += ["--length-scale", str(self.length_scale)]
        flags = 0x08000000 if os.name == "nt" else 0    # CREATE_NO_WINDOW
        p = subprocess.run(args, input=text.encode("utf-8"), capture_output=True,
                           timeout=30, creationflags=flags)
        return np.frombuffer(p.stdout, dtype=np.int16).copy(), self._sample_rate()


# ============================================================================
# Engine
# ============================================================================
class TTSEngine:
    """Non-blocking, pipelined TTS (Edge online, Piper offline)."""

    def __init__(self, voice=DEFAULT_VOICE, enabled=True):
        prefs = _load_prefs()
        self._voice = prefs.get("voice", voice)
        self._enabled = enabled
        self._backend = prefs.get("backend", "auto") if prefs.get("backend") in BACKENDS else "auto"
        self._backend_from_prefs = "backend" in prefs
        self.piper = PiperBackend(prefs.get("piper_model", DEFAULT_PIPER_MODEL),
                                  prefs.get("piper_length_scale"))
        self._rate = RATE
        self._volume = VOLUME
        self._edge_down_until = 0.0
        self.last_backend = None

        self._text_q = queue.Queue()
        self._audio_q = queue.Queue(maxsize=3)
        self._stop_event = threading.Event()
        self._generation = 0
        self._busy_lock = threading.Lock()
        self._pending = 0
        self._playing = False
        self._cache = OrderedDict()
        self._loop = asyncio.new_event_loop()

        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

    # ── Public API ──────────────────────────────────────────────

    def speak(self, text):
        if not self.is_enabled or not text:
            return
        clean = self._clean_text(text)
        if not clean:
            return
        _mark("tts_request")
        with self._busy_lock:
            self._pending += 1
        self._text_q.put((self._generation, clean))

    def speak_sync(self, text, timeout=60):
        self.speak(text)
        self.wait_until_done(timeout)

    def wait_until_done(self, timeout=60):
        end = time.time() + timeout
        while self.is_speaking() and time.time() < end:
            time.sleep(0.05)

    def is_speaking(self):
        with self._busy_lock:
            return self._pending > 0 or self._playing

    def set_enabled(self, enabled):
        self._enabled = enabled
        if not enabled:
            self.stop()

    def set_voice(self, voice_id):
        self._voice = voice_id
        self._cache.clear()
        p = _load_prefs()
        p["voice"] = voice_id
        _save_prefs(p)

    def set_rate(self, rate):
        """rate like '+10%' or an int percent."""
        if isinstance(rate, (int, float)):
            rate = f"{'+' if rate >= 0 else ''}{int(rate)}%"
        self._rate = rate
        self._cache.clear()

    @property
    def backend(self):
        return self._backend

    def set_backend(self, name, save=True):
        if name not in BACKENDS:
            raise ValueError(f"backend must be one of {BACKENDS}")
        self._backend = name
        self._cache.clear()
        if save:
            p = _load_prefs()
            p["backend"] = name
            _save_prefs(p)
            self._backend_from_prefs = True

    def configure(self, backend=None, piper_model=None, piper_length_scale=None,
                  piper_exe=None):
        """Called by agent.py from config.json. A choice made in Settings
        (tts_prefs.json) wins over config.json."""
        if backend in BACKENDS and not self._backend_from_prefs:
            self._backend = backend
        if piper_model and not os.path.isabs(piper_model):
            piper_model = os.path.join(_HERE, piper_model)
        self.piper.configure(piper_model, piper_length_scale, piper_exe)

    def status(self):
        return {
            "backend": self._backend,
            "edge_available": _HAS_EDGE_TTS,
            "edge_online": time.time() >= self._edge_down_until,
            "piper_available": self.piper.available,
            "piper_model": self.piper.model_path,
            "last_backend": self.last_backend,
            "through_audio_engine": bool(audio_io and audio_io.get_audio_engine()
                                         and audio_io.get_audio_engine().has_output),
        }

    def stop(self):
        """Stop immediately: current sentence + everything queued."""
        self._generation += 1
        self._stop_event.set()
        for q in (self._text_q, self._audio_q):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        with self._busy_lock:
            self._pending = 0
        eng = audio_io.get_audio_engine() if audio_io else None
        if eng is not None and eng.has_output:
            eng.stop_playback()
        if _HAS_PYGAME:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
                    pygame.mixer.stop()
            except Exception:
                pass

    @property
    def is_enabled(self):
        return self._enabled and (_HAS_EDGE_TTS or self.piper.available)

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text):
        clean = _EMOJI_RE.sub("", str(text))
        clean = _MD_RE.sub(" ", clean)
        clean = re.sub(r"https?://\S+", "", clean)
        return re.sub(r"\s+", " ", clean).strip()

    def _done_one(self):
        with self._busy_lock:
            self._pending = max(0, self._pending - 1)

    def _order(self):
        if self._backend == "piper":
            return ["piper", "edge"]
        return ["edge", "piper"]

    def _synthesize(self, text):
        """-> (kind, payload, backend) or None. kind: 'mp3' bytes | 'pcm' (arr, sr)."""
        for b in self._order():
            if b == "edge":
                if not _HAS_EDGE_TTS:
                    continue
                if time.time() < self._edge_down_until and self.piper.available:
                    continue
                try:
                    mp3 = self._loop.run_until_complete(
                        asyncio.wait_for(self._synth_edge(text), _EDGE_TIMEOUT))
                    if mp3:
                        return ("mp3", mp3, "edge")
                except Exception as e:
                    if self._stop_event.is_set():
                        return None
                    self._edge_down_until = time.time() + _EDGE_COOLDOWN
                    if self.piper.available:
                        print(f"⚠️ Edge TTS وقع ({str(e)[:60]}) — هتكلم بـ Piper أوفلاين")
                    else:
                        print(f"⚠️ TTS generation error: {e}")
            elif b == "piper" and self.piper.available:
                try:
                    pcm, sr = self.piper.synth(text)
                    if pcm.size:
                        return ("pcm", (pcm, sr), "piper")
                except Exception as e:
                    print(f"⚠️ Piper error: {e}")
        return None

    def _synth_loop(self):
        asyncio.set_event_loop(self._loop)
        while True:
            gen, text = self._text_q.get()
            if gen != self._generation:
                continue
            try:
                key = (self._backend, self._voice, self._rate, text)
                item = self._cache.get(key)
                if item is None:
                    item = self._synthesize(text)
                    if item and len(text) <= _CACHE_MAX_CHARS:
                        self._cache[key] = item
                        if len(self._cache) > _CACHE_MAX_ITEMS:
                            self._cache.popitem(last=False)
                else:
                    self._cache.move_to_end(key)
                if gen != self._generation or not item:
                    if gen == self._generation:
                        self._done_one()
                    continue
                if item[0] == "mp3":
                    eng = audio_io.get_audio_engine() if audio_io else None
                    if eng is not None and eng.has_output:
                        dec = decode_mp3(item[1])      # decode here, off the play loop
                        if dec is not None:
                            item = ("pcm", dec, item[2])
                _mark("tts_ready", info=item[2])
                self.last_backend = item[2]
                self._audio_q.put((gen, item))
            except Exception as e:
                print(f"⚠️ TTS generation error: {e}")
                if gen == self._generation:
                    self._done_one()

    async def _synth_edge(self, text):
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text=text, voice=self._voice,
                                           rate=self._rate, volume=self._volume)
        async for chunk in communicate.stream():
            if self._stop_event.is_set():
                break
            if chunk.get("type") == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    def _play_loop(self):
        while True:
            gen, item = self._audio_q.get()
            if gen != self._generation:
                continue
            self._stop_event.clear()
            self._playing = True
            try:
                self._play_item(item)
            except Exception as e:
                print(f"⚠️ Audio playback error: {e}")
            finally:
                self._playing = False
                if gen == self._generation:
                    self._done_one()

    @staticmethod
    def _first_audio():
        _mark("first_audio")

    def _play_item(self, item):
        kind, payload, _backend = item
        eng = audio_io.get_audio_engine() if audio_io else None
        if eng is not None and eng.has_output:
            pcm_sr = decode_mp3(payload) if kind == "mp3" else payload
            if pcm_sr is not None:
                pcm, sr = pcm_sr
                eng.play(pcm, sr, stop_event=self._stop_event, on_start=self._first_audio)
                return
            elif not getattr(self, "_warned_decode", False):
                self._warned_decode = True
                print("⚠️ مش قادر أفك الـ mp3 — اعمل pip install miniaudio عشان إلغاء الصدى يشتغل مع صوت Edge")
        if audio_io:
            audio_io.set_unreferenced(True)
        try:
            if kind == "mp3":
                self._play_mp3_fallback(payload)
            else:
                self._play_pcm_fallback(*payload)
        finally:
            if audio_io:
                audio_io.set_unreferenced(False)

    def _play_pcm_fallback(self, pcm, sr):
        wav = pcm_to_wav(pcm, sr)
        if _HAS_PYGAME:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            snd = pygame.mixer.Sound(file=io.BytesIO(wav))
            ch = snd.play()
            self._first_audio()
            while ch is not None and ch.get_busy():
                if self._stop_event.is_set():
                    ch.stop()
                    break
                time.sleep(0.03)
            return
        import winsound
        self._first_audio()
        winsound.PlaySound(wav, winsound.SND_MEMORY)

    def _play_mp3_fallback(self, audio):
        if _HAS_PYGAME:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(io.BytesIO(audio), "mp3")
            pygame.mixer.music.play()
            self._first_audio()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.03)
            return
        import ctypes
        import tempfile
        path = os.path.join(tempfile.gettempdir(), f"yobi_{int(time.time()*1000)}.mp3")
        with open(path, "wb") as f:
            f.write(audio)
        mci = ctypes.windll.winmm.mciSendStringW
        alias = f"yobi{int(time.time()*1000)}"
        mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
        mci(f"play {alias}", None, 0, None)
        self._first_audio()
        status = ctypes.create_unicode_buffer(32)
        while True:
            mci(f"status {alias} mode", status, 32, None)
            if status.value != "playing" or self._stop_event.is_set():
                break
            time.sleep(0.05)
        mci(f"close {alias}", None, 0, None)
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Sentence splitter for streamed LLM text
# ---------------------------------------------------------------------------
class SentenceStreamer:
    """Feed it token deltas; it calls on_sentence(text) each time a full
    sentence is ready, so TTS can start before the LLM finishes."""

    _HARD = re.compile(r"[.!?؟\n]+")
    _SOFT = re.compile(r"[،,؛:]\s")

    def __init__(self, on_sentence, min_chars=12, soft_split_at=90):
        self._buf = ""
        self._on_sentence = on_sentence
        self._min = min_chars
        self._soft = soft_split_at

    def _emit(self, upto):
        sentence, self._buf = self._buf[:upto], self._buf[upto:]
        if sentence.strip():
            self._on_sentence(sentence.strip())

    def feed(self, delta):
        if not delta:
            return
        self._buf += delta
        while True:
            hard = next((m for m in self._HARD.finditer(self._buf)
                         if m.end() >= self._min), None)
            if hard:
                self._emit(hard.end())
                continue
            if len(self._buf) >= self._soft:
                soft = None
                for m in self._SOFT.finditer(self._buf):
                    soft = m
                if soft and soft.end() >= self._min:
                    self._emit(soft.end())
                    continue
            return

    def flush(self):
        if self._buf.strip():
            self._on_sentence(self._buf.strip())
        self._buf = ""


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_engine = None
_engine_lock = threading.Lock()


def get_tts_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = TTSEngine()
        return _engine


def speak(text):
    get_tts_engine().speak(text)


def speak_sync(text):
    get_tts_engine().speak_sync(text)


def stop_speaking():
    get_tts_engine().stop()


def is_speaking():
    return get_tts_engine().is_speaking()
