# -*- coding: utf-8 -*-
"""
STT engine — مين يسمع الأمر: Groq ولا الـ GPU بتاعك.

Engines:
    groq-turbo : Groq whisper-large-v3-turbo   (fast, online)
    groq-v3    : Groq whisper-large-v3         (most accurate, online)
    gemini     : Gemini Flash hears the clip   (online; what a Gemini key alone gives)
    local      : faster-whisper on your GPU    (offline, default large-v3-turbo)

With only a Gemini key there is no Groq Whisper: both groq names mean the one "gemini"
engine, asked once. Then, in "auto", a local Whisper that really runs on the graphics card
goes first (a fraction of a second, no upload); when it isn't sure of what it heard, Gemini
hears the clip too.

engine="auto" tries the configured preference order and falls back when a
backend errors or the internet drops (a small circuit breaker skips Groq
for 60 s after repeated failures). Run tools/stt_benchmark.py to decide
which one wins on *your* Egyptian Arabic, then set `stt_engine`.

Personal vocabulary (vocab.py):
  prompt  → built by the caller with vocab.prompt() (Groq `prompt` /
            local `initial_prompt`)
  local   → also gets vocab.hotwords() as faster-whisper `hotwords`
  output  → vocab.apply_fixes() repairs known mis-hearings
"""

import io
import re
import threading
import time

try:
    import latency
except Exception:  # pragma: no cover
    latency = None

GROQ_MODELS = {"groq-turbo": "whisper-large-v3-turbo", "groq-v3": "whisper-large-v3"}

# v6.1: the turbo model sometimes writes Egyptian Arabic in Latin letters
# ("افتح لول" → "uptah lúlí"). Such results are re-heard by another engine.
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F]+")
_ACCENT_RE = re.compile(r"[\u00C0-\u024F]")
COMMON_LATIN = set("""
open close start stop play pause next previous search find run launch kill quit exit
volume up down mute unmute music song songs video youtube google chrome edge firefox
spotify discord steam epic valorant league legends of the a an to on off in my me
please hey hi hello yes no ok okay what time is it how are you screenshot settings
file files folder window windows app apps game games tab new and for with from
""".split())


def _mark(name, info=None):
    if latency is not None:
        latency.mark(name, info=info)


class STTEngine:
    def __init__(self, groq_client=None, engine="auto", order=None,
                 local_model="large-v3-turbo", local_device="cuda",
                 local_compute="float16", vocab=None, is_silent=None,
                 is_hallucination=None, log=print, prompt_chars=300):
        self.groq = groq_client
        self.engine = engine
        self.order = order or ["groq-turbo", "local", "groq-v3"]
        self.local_model_name = local_model
        self.local_device = local_device
        self.local_compute = local_compute
        self.vocab = vocab
        self.prompt_chars = prompt_chars
        self._is_silent = is_silent or (lambda a: False)
        self._is_hallu = is_hallucination or (lambda t: False)
        self._log = log
        self._local = None
        self._local_lock = threading.Lock()
        self._fail = {}            # engine -> (count, last_time)
        self.last_engine = None
        self.stats = {}            # engine -> list of ms
        # v7: ثقة Whisper في آخر حاجة سمعها (avg_logprob / no_speech_prob)
        self.last_conf = None      # {"avg_logprob": float, "no_speech_prob": float}
        self.last_low = False      # True = يوبي مش واثق من اللي سمعه
        self._verbose_ok = True    # لو Groq رفض verbose_json نرجع للعادي
        self.local_gpu = None      # True once the local model has really run on the graphics card
        self.low_logprob = -0.85
        self.low_no_speech = 0.6

    # --------------------------------------------------------------- public
    def set_engine(self, name):
        self.engine = name

    def transcribe(self, audio, prompt="", lang="ar", engine=None, mark=True):
        """audio: speech_recognition.AudioData (or anything with get_wav_data())."""
        if audio is None or self._is_silent(audio):
            return ""
        wav = audio.get_wav_data()
        # The caller builds the prompt (agent uses vocab.prompt for commands,
        # short hints like "أيوة لا" for confirmations).
        prompt = (prompt or "")[: self.prompt_chars]
        self.last_conf = None
        self.last_low = False
        if mark:
            _mark("stt_start")
        last_err = None
        fallback = None                 # an unsure result kept in case nothing better comes
        cands = self._candidates(engine)
        i = 0
        while i < len(cands):
            eng = cands[i]
            i += 1
            t0 = time.perf_counter()
            self.last_conf = None
            try:
                if eng == "local":
                    text = self._local_transcribe(wav, prompt, lang)
                else:
                    text = self._groq_transcribe(wav, GROQ_MODELS.get(eng, GROQ_MODELS["groq-turbo"]), prompt, lang)
            except Exception as e:
                last_err = e
                self._record_fail(eng)
                self._log(f"⚠️ STT {eng} فشل: {str(e)[:120]}")
                continue
            ms = (time.perf_counter() - t0) * 1000
            self.stats.setdefault(eng, []).append(ms)
            self._fail.pop(eng, None)
            text = (text or "").strip()
            self._log(f"👂 {eng} سمع في {ms:.0f}ms: '{text}'")
            if lang == "ar" and i < len(cands) and self.looks_romanized(text):
                self._log(f"🔁 الكلام اتكتب بحروف إنجليزي ('{text}') — بعيد السمع بموديل تاني")
                fallback = fallback or (text, eng, self.last_conf)
                # the full large-v3 model is the best at Arabic script → try it next
                if "groq-v3" in cands[i:]:
                    cands.remove("groq-v3")
                    cands.insert(i, "groq-v3")
                continue
            # the local model isn't sure and a cloud one is next: a second opinion costs a moment
            # only on the unclear clips
            if (eng == "local" and text and fallback is None and i < len(cands) and cands[i] != "local"
                    and self.is_low_confidence(text)):
                self._log("🔁 الموديل المحلي مش واثق — بسمعها بالموديل التاني كمان")
                fallback = (text, eng, self.last_conf)
                continue
            if fallback and (not text or (lang == "ar" and self.looks_romanized(text))):
                text, eng, self.last_conf = fallback
            return self._finish(text, eng, mark)
        if fallback:                    # the second opinion failed: the unsure one is all there is
            text, eng, self.last_conf = fallback
            return self._finish(text, eng, mark)
        if last_err is not None:
            self._log(f"⚠️ كل محركات السمع فشلت: {last_err}")
        return ""

    def _finish(self, text, eng, mark):
        self.last_engine = eng
        if self.vocab is not None:
            text = self.vocab.apply_fixes(text)
        text = text.lower()
        if mark:
            _mark("stt_done", info=eng)
        if self._is_hallu(text):
            self._log(f"🚫 تجاهلت هالوسينيشن Whisper: '{text}'")
            return ""
        self.last_low = self.is_low_confidence(text)
        if self.last_low:
            self._log(f"🤔 مش واثق من اللي سمعته: '{text}' ({self.last_conf})")
        return text

    def is_low_confidence(self, text=None):
        """True لو Whisper نفسه مش واثق، أو النص طالع بحروف غريبة
        ('шагал', 'ufta hlúl')، أو فضل بحروف لاتيني لأمر عربي."""
        try:
            from target_resolver import text_looks_garbled
            if text and text_looks_garbled(text):
                return True
        except Exception:
            pass
        if text and self.looks_romanized(text):
            return True
        c = self.last_conf or {}
        lp, ns = c.get("avg_logprob"), c.get("no_speech_prob")
        if lp is not None and lp < self.low_logprob:
            return True
        if ns is not None and ns > self.low_no_speech:
            return True
        return False

    @staticmethod
    def _conf_from_segments(segs):
        vals, ns = [], []
        for sg in segs or []:
            get = sg.get if isinstance(sg, dict) else (lambda k, d=None, _s=sg: getattr(_s, k, d))
            lp = get("avg_logprob")
            if lp is not None:
                vals.append(float(lp))
            n = get("no_speech_prob")
            if n is not None:
                ns.append(float(n))
        if not vals and not ns:
            return None
        return {"avg_logprob": (sum(vals) / len(vals)) if vals else None,
                "no_speech_prob": max(ns) if ns else None}

    def looks_romanized(self, text):
        """True when an Arabic command came back in Latin letters."""
        t = (text or "").strip()
        if not t:
            return False
        if _ACCENT_RE.search(t):
            return True            # "lúlí", "júru", "ḥ" … even if preceded by Arabic "افتح"
        if _ARABIC_RE.search(t):
            return False
        words = [w.lower() for w in _LATIN_WORD_RE.findall(t)]
        if not words:
            return False
        known = set(COMMON_LATIN)
        if self.vocab is not None:
            try:
                for term in self.vocab.terms():
                    known.update(w.lower() for w in _LATIN_WORD_RE.findall(term))
            except Exception:
                pass
        unknown = [w for w in words if w not in known]
        return len(unknown) * 2 > len(words)

    def warmup(self):
        """Load the local model in the background so the first offline
        command isn't slow."""
        if "local" in self._candidates(None):
            threading.Thread(target=self._get_local, daemon=True).start()

    # ------------------------------------------------------------ internals
    @property
    def gemini_only(self):
        """The cloud client is Gemini with no Groq key behind it: no Whisper online."""
        return bool(getattr(self.groq, "is_gemini", False) and getattr(self.groq, "_groq_stt", None) is None)

    def _candidates(self, engine):
        eng = engine or self.engine
        auto = not eng or eng == "auto"
        order = list(self.order) if auto else [eng] + [e for e in self.order if e != eng]
        # an explicit choice still falls back if it fails
        if self.gemini_only:            # both groq names are the same Gemini call: ask it once
            order = ["gemini" if e in GROQ_MODELS else e for e in order]
            if auto and self.local_gpu and "local" in order:
                order = ["local"] + order
        else:
            order = [e for e in order if e != "gemini"]
        order = list(dict.fromkeys(order))
        now = time.time()
        out = []
        for e in order:
            if e not in ("local", "gemini") and e not in GROQ_MODELS:
                continue
            if e != "local" and self.groq is None:
                continue
            n, t = self._fail.get(e, (0, 0))
            if n >= 2 and now - t < 60:
                continue   # circuit open
            out.append(e)
        return out or ["local"]

    def _record_fail(self, eng):
        n, _ = self._fail.get(eng, (0, 0))
        self._fail[eng] = (n + 1, time.time())

    def _groq_transcribe(self, wav, model, prompt, lang):
        kwargs = dict(file=("command.wav", wav), model=model, prompt=prompt,
                      temperature=0.0)
        if lang:
            kwargs["language"] = lang
        if self._verbose_ok:
            try:
                resp = self.groq.audio.transcriptions.create(
                    response_format="verbose_json", **kwargs)
                segs = getattr(resp, "segments", None)
                if segs is None:
                    extra = getattr(resp, "model_extra", None) or {}
                    segs = extra.get("segments")
                if segs is None and isinstance(resp, dict):
                    segs = resp.get("segments")
                self.last_conf = self._conf_from_segments(segs)
                text = getattr(resp, "text", None)
                if text is None and isinstance(resp, dict):
                    text = resp.get("text")
                return text or ""
            except TypeError:
                self._verbose_ok = False   # SDK قديم
            except Exception as e:
                if "response_format" not in str(e).lower():
                    raise
                self._verbose_ok = False
        resp = self.groq.audio.transcriptions.create(**kwargs)
        return getattr(resp, "text", "") or ""

    def _get_local(self):
        with self._local_lock:
            if self._local is not None:
                return self._local
            from faster_whisper import WhisperModel
            try:
                m = WhisperModel(self.local_model_name, device=self.local_device,
                                 compute_type=self.local_compute)
                if self.local_device != "cpu":
                    # the GPU libraries load on first use: a PC with a card but without them
                    # (cublas...) fails here, once, not on every command later
                    import numpy as np
                    list(m.transcribe(np.zeros(8000, dtype=np.float32), language="ar", beam_size=1)[0])
                self._local, self.local_gpu = m, self.local_device != "cpu"
            except Exception as e:
                self._log(f"⚠️ مش قادر أشغل {self.local_model_name} على {self.local_device} "
                          f"({str(e)[:80]}) — هجرب الـ CPU")
                self._local = WhisperModel(
                    "small" if "large" in self.local_model_name else self.local_model_name,
                    device="cpu", compute_type="int8")
                self.local_gpu = False
            if self.local_gpu:
                self._log(f"⚡ السمع المحلي ({self.local_model_name}) شغال على كارت الشاشة")
            return self._local

    def _local_transcribe(self, wav, prompt, lang):
        model = self._get_local()
        # a wider search hears names better; on the card it costs next to nothing
        kwargs = dict(language=lang, beam_size=5 if self.local_gpu else 1, vad_filter=True,
                      initial_prompt=prompt or None, condition_on_previous_text=False)
        if self.vocab is not None:
            hw = self.vocab.hotwords()
            if hw:
                kwargs["hotwords"] = hw
        with io.BytesIO(wav) as f:
            try:
                segments, _ = model.transcribe(f, **kwargs)
            except TypeError:
                kwargs.pop("hotwords", None)   # old faster-whisper
                f.seek(0)
                segments, _ = model.transcribe(f, **kwargs)
            segments = list(segments)
            self.last_conf = self._conf_from_segments(segments)
            return "".join(s.text for s in segments)
