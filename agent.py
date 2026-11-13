# -*- coding: utf-8 -*-
import difflib
import io
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
import webbrowser
import psutil
import threading
import speech_recognition as sr
from faster_whisper import WhisperModel
from groq import Groq
from app_scanner import load_or_scan_installed_apps, resolve_target
from game_scanner import scan_all_games, bounded_game_search
from aliases import ARABIC_TO_CANONICAL, normalize_name
from transliteration import normalize_transcription
from addressing import AddressedClassifier, wake_pattern
from file_ops import match_file_command
from device_control import match_device_command
from smart_scan import run_full_scan
from chat_engine import ChatEngine
from self_learning import SelfLearner
from credentials import save_credentials, delete_credentials, has_credentials
from auto_login import (
    try_auto_login, launcher_for_game,
    resolve_account_key, label_for_account_key,
)
from login_dialog import show_login_dialog
from vision_agent import (
    load_tasks,
    save_tasks,
    find_matching_task,
    run_task_live,
    record_demo,
    describe_demo,
    describe_screen,
)
from system_control import match_system_command, pick_processes
from ui import DynamicIsland
from context_memory import ContextMemory
from command_chainer import split_compound_command
from island_voice import match_island_command, open_page as island_open_page   # the island's pages and prayer times
import target_resolver as _tr                      # v7: فهم أسماء البرامج
from smart_open import smart_open, exe_matches     # v7: افتح/اسأل/ابحث
from learning_guard import LearningGuard           # v7: يتعلم الصح بس
from dataset_recorder import DatasetRecorder       # v7.1: داتا تدريب من استخدامك
from intent_model import IntentModel               # v7.2: موديل الأوامر (اختياري)
from scheduler import TaskScheduler
from natural_qa import is_question, try_system_answer, answer_with_llm
from smart_suggestions import SmartSuggestions, is_suggestion_request
from media_handler import handle_media_or_search
from tts_engine import speak, stop_speaking, get_tts_engine, is_speaking
from brain import Brain
from yobi_tools import YobiTools
from audio_input import VADRecognizer, HotkeyPressed
from sounds import play_wake, play_success, play_error, play_listening, play_hide
from tray_icon import YobiTray

# ── v4 hearing (all optional — Yobi still runs without any of them) ──
try:
    import latency as yobi_latency
except Exception:
    yobi_latency = None
try:
    from audio_io import get_audio_engine
except Exception:
    get_audio_engine = None
try:
    from wake_word import WakeWordDetector
except Exception:
    WakeWordDetector = None
try:
    from stt_engine import STTEngine
except Exception:
    STTEngine = None
try:
    from vocab import PersonalVocab
except Exception:
    PersonalVocab = None
try:
    from companion import Companion
except Exception:
    Companion = None

# ── v6: Yobi replies in writing (typewriter + soft sound), voice is optional ──
from tts_engine import speak as _tts_speak
_REPLY_ISLAND = None      # set in __main__ once the island exists
_COMPANION = None         # set in voice_loop()
_GAME_COMPANION = None    # set in __main__


def _reply_cfg():
    rc = {"voice": False, "chime": True}
    try:
        rc.update(CONFIG.get("replies") or {})
    except Exception:
        pass
    return rc


def speak(text):
    """v6: replaces the voice reply. The text is written on the island like
    Yobi is talking; real voice only when config "replies": {"voice": true}."""
    if not text:
        return
    rc = _reply_cfg()
    isl = _REPLY_ISLAND
    if isl is not None:
        try:
            isl.after(0, lambda t=str(text), c=bool(rc.get("chime", True)): isl.say(t, chime=c))
        except Exception:
            pass
    if rc.get("voice"):
        _tts_speak(text)
    elif yobi_latency is not None:
        yobi_latency.mark("tts_request")
        yobi_latency.mark("first_audio")


# Overridable from config.json → "hearing": {...}
HEARING_DEFAULTS = {
    "audio_engine": True,          # shared mic+speaker engine (needed for AEC)
    "aec": True,                   # WebRTC echo cancellation (pip install livekit)
    "noise_suppression": True,
    "agc": True,
    "aec_extra_delay_ms": 0,
    "input_device": None,
    "output_device": None,
    "wake_model": "models/ya_yobi.onnx",   # openWakeWord model (or e.g. "hey_jarvis")
    "wake_threshold": 0.35,
    "wake_patience": 1,
    "wake_verify_whisper": False,  # double-check hits with Whisper (new models)
    "wake_debug": False,
    "barge_in": "auto",            # auto | wake | speech | off
    "stt_engine": "auto",          # auto | groq-turbo | groq-v3 | local
    "stt_order": ["groq-turbo", "local", "groq-v3"],
    "stt_local_model": "large-v3-turbo",
    "stt_local_device": "cuda",
    "stt_local_compute": "float16",
    "stt_warmup_local": True,      # preload local model → instant offline fallback
    "vocab_max_chars": 360,
    "tts_backend": None,           # auto | edge | piper (Settings choice wins)
    "piper_model": "voices/ar_JO-kareem-medium.onnx",
    "piper_length_scale": None,
    "piper_exe": None,
    "latency_log": True,
    "latency_csv": "latency_log.csv",
}

# ── New modules (backward-compatible) ──────────────────────────
try:
    from yobi_logger import log as yobi_log, get_logger, timed
    _HAS_LOGGER = True
except ImportError:
    _HAS_LOGGER = False
    yobi_log = None

try:
    from config import cfg
    _HAS_CONFIG = True
except ImportError:
    _HAS_CONFIG = False
    cfg = None

try:
    from retry_handler import with_retry, api_call, health, is_online
    _HAS_RETRY = True
except ImportError:
    _HAS_RETRY = False

try:
    from game_companion import GameCompanion, handle_game_query
    _HAS_GAME_COMPANION = True
except ImportError:
    _HAS_GAME_COMPANION = False

try:
    from chat_window import ChatWindow
    _HAS_CHAT_WINDOW = True
except ImportError:
    _HAS_CHAT_WINDOW = False

try:
    from overlay_ui import GameOverlay
    _HAS_OVERLAY = True
except ImportError:
    _HAS_OVERLAY = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    print("⚠️ يرجى تثبيت المكتبات أولاً: pip install arabic-reshaper python-bidi")
    sys.exit(1)

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def print_ar(text):
    try:
        reshaped_text = arabic_reshaper.reshape(str(text))
        bidi_text = get_display(reshaped_text)
        print(bidi_text)
    except Exception:
        try:
            print(str(text))
        except Exception:
            pass


# ==========================================
# Whisper Silence-Hallucination Filter
# ==========================================
_WHISPER_HALLUCINATIONS = {
    "اشترك في القناة", "اشتركو في القناة", "اشتركوا في القناة",
    "اشترك في قناتي", "اشترك بالقناة", "اشتركوا بالقناة",
    "لا تنسى الاشتراك", "لا تنسوا الاشتراك", "لا تنسي الاشتراك",
    "شكرا للمشاهدة", "شكراً للمشاهدة", "شكرا على المشاهدة",
    "شكرا لمشاهدتكم", "شكرا علي المشاهده",
    "ترجمة نانسي قنقر", "ترجمة نانسي قنق", "نانسي قنقر",
    "مشاهدة ممتعة", "اتمنى لكم مشاهدة ممتعة",
    "subscribe", "subscribe to my channel", "please subscribe",
    "thanks for watching", "thank you for watching",
    "thanks for watching!", "please like and subscribe",
    "like and subscribe", "hit the bell",
    "sous-titres", "untertitel", "amara.org",
    "www.zeoflix.com", "字幕", "sottotitoli",
    "...", "..", "،", "؛", "-", "_",
}


def _is_hallucination(text):
    if not text:
        return True
    t = text.strip().lower()
    t_clean = re.sub(r"[،.,؛;!؟?\"'()\[\]\s]+", " ", t).strip()
    if not t_clean or len(t_clean) < 3:
        return True
    words = t_clean.split()
    if t_clean in ("انتهى", "موسيقى", "ترجمة") or "المترجم" in t_clean:
        return True
    if len(words) >= 3 and max(words.count(w) for w in set(words)) / len(words) >= 0.45:
        return True
    if len(words) >= 6 and len(set(words)) / len(words) <= 0.45:
        return True
    for h in _WHISPER_HALLUCINATIONS:
        h_clean = re.sub(r"[،.,؛;!؟?\"'()\[\]\s]+", " ", h.lower()).strip()
        if not h_clean:
            continue
        if t_clean == h_clean:
            return True
        if h_clean in t_clean and len(t_clean) - len(h_clean) <= 12:
            return True
    return False


def _audio_is_silent(audio, rms_threshold=90):
    try:
        wav_bytes = audio.get_wav_data()
        if not wav_bytes:
            return True
        import numpy as _np
        pcm = _np.frombuffer(audio.get_raw_data(convert_width=2), dtype=_np.int16).astype(_np.float32)
        return pcm.size == 0 or float(_np.sqrt(_np.mean(pcm * pcm))) < rms_threshold
    except Exception:
        return False


# ==========================================
# 1. API & OS Setup
# ==========================================
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE, override=True)
except ImportError:
    pass


def _scan_env_file():
    """Directly read .env in the project folder so keys are always found
    even if python-dotenv is missing or env vars were cached by Windows."""
    found_gemini = ""
    found_groq = ""
    if os.path.exists(_ENV_FILE):
        try:
            with open(_ENV_FILE, "r", encoding="utf-8", errors="replace") as ef:
                for raw in ef:
                    line = raw.strip().strip('"').strip("'")
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip().upper()
                        v = v.strip().strip('"').strip("'")
                        if v.startswith("AIza"):
                            found_gemini = v
                        elif v.startswith("gsk_"):
                            found_groq = v
                        elif k in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v:
                            found_gemini = v
                        elif k == "GROQ_API_KEY" and v:
                            found_groq = v
                    else:
                        if line.startswith("AIza"):
                            found_gemini = line
                        elif line.startswith("gsk_"):
                            found_groq = line
        except Exception:
            pass
    return found_gemini, found_groq

# ==========================================
# Gemini Flash Client (Drop-in OpenAI/Groq-compatible adapter)
# Supports: streaming SSE, tool calling, vision (base64 JPEG), JSON mode,
# and audio transcription (via Groq Whisper if GROQ_API_KEY is set, or
# directly via Gemini Flash multimodal audio if only GEMINI_API_KEY is set).
# ==========================================
import base64
import urllib.error
import urllib.request


class _AttrObj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class GeminiClient:
    """Drop-in replacement for Groq client powered by Google Gemini Flash."""
    is_gemini = True
    OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    NATIVE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

    def __init__(self, gemini_key: str, groq_stt_client=None, default_model: str = "gemini-3.5-flash"):
        self.api_key = (gemini_key or "").strip()
        self._groq_stt = groq_stt_client
        self.default_model = default_model
        self.chat = _AttrObj(completions=_AttrObj(create=self._chat_create))
        self.audio = _AttrObj(transcriptions=_AttrObj(create=self._audio_transcribe))

    def _resolve_model(self, model: str) -> str:
        m = (model or self.default_model).strip()
        # Automatically map any legacy Groq/Llama/OpenAI model names to Gemini Flash
        if not m.startswith("gemini-"):
            return self.default_model
        return m

    @staticmethod
    def _clean_messages(messages):
        cleaned = []
        for msg in messages or []:
            m = dict(msg)
            if m.get("role") == "assistant" and m.get("content") is None:
                m["content"] = ""
            if m.get("role") == "tool" and not m.get("content"):
                m["content"] = "done"
            cleaned.append(m)
        return cleaned

    def _native_chat_fallback(self, model, messages, temperature, max_tokens, response_format):
        """Fallback to native Google generateContent endpoint."""
        sys_parts = []
        contents = []
        for m in messages or []:
            role = m.get("role", "user")
            c = m.get("content") or ""
            parts = []
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append({"text": item.get("text", "")})
                        elif item.get("type") == "image_url":
                            u = (item.get("image_url") or {}).get("url", "")
                            if "base64," in u:
                                b64 = u.split("base64,", 1)[1]
                                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
            else:
                parts.append({"text": str(c)})
            if role == "system":
                sys_parts.extend(parts)
            else:
                g_role = "model" if role == "assistant" else "user"
                contents.append({"role": g_role, "parts": parts})
        if not contents:
            contents = [{"role": "user", "parts": [{"text": "hi"}]}]
        gen_cfg = {
            "temperature": float(temperature) if temperature is not None else 0.6,
            "maxOutputTokens": int(max_tokens) if max_tokens is not None else 500,
        }
        if response_format and response_format.get("type") == "json_object":
            gen_cfg["responseMimeType"] = "application/json"
        body = {"contents": contents, "generationConfig": gen_cfg}
        if sys_parts:
            body["systemInstruction"] = {"parts": sys_parts}
        url = self.NATIVE_URL.format(model=model, key=self.api_key)
        req = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        cands = res.get("candidates") or []
        text = ""
        if cands:
            pts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in pts).strip()
        if response_format and response_format.get("type") == "json_object":
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        return _AttrObj(choices=[_AttrObj(message=_AttrObj(content=text, tool_calls=[]))])

    FALLBACK_MODELS = [
        "gemini-3.5-flash",          # gemini-3.8-flash hung for 60 s in testing (2026-11-08): last
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
    ]

    def _candidate_models(self, requested_model=None):
        primary = self._resolve_model(requested_model)
        order = [primary] + [m for m in self.FALLBACK_MODELS if m != primary]
        return order

    def _chat_create(self, model=None, messages=None, tools=None, tool_choice=None,
                     temperature=0.6, max_tokens=500, stream=False,
                     response_format=None, **extra):
        candidates = self._candidate_models(model)
        cleaned_msgs = self._clean_messages(messages)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        last_err = None

        for idx_m, target_model in enumerate(candidates):
            payload = {
                "model": target_model,
                "messages": cleaned_msgs,
                "temperature": float(temperature) if temperature is not None else 0.6,
                "max_tokens": int(max_tokens) if max_tokens is not None else 500,
                "stream": bool(stream),
            }
            if tools:
                payload["tools"] = tools
                if tool_choice:
                    payload["tool_choice"] = tool_choice
            if response_format:
                payload["response_format"] = response_format

            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(self.OPENAI_URL, data=data, headers=headers, method="POST")

            if stream:
                try:
                    resp = urllib.request.urlopen(req, timeout=35)
                    if idx_m > 0:
                        print_ar(f"🔄 تم التحويل تلقائياً للموديل المتاح: {target_model}")
                        self.default_model = target_model
                    return self._stream_from_open_resp(resp)
                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="replace")
                    last_err = RuntimeError(f"Gemini Stream HTTP {e.code} ({target_model}): {err_body[:180]}")
                    if e.code in (400, 404, 429, 500, 502, 503, 504):
                        print_ar(f"⚠️ الموديل {target_model} مشغول (HTTP {e.code}) — بجرب الموديل البديل...")
                        continue
                    raise last_err from e
                except Exception as e:
                    last_err = e
                    continue

            try:
                with urllib.request.urlopen(req, timeout=35) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                if idx_m > 0:
                    print_ar(f"🔄 تم التحويل تلقائياً للموديل المتاح: {target_model}")
                    self.default_model = target_model
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                last_err = RuntimeError(f"Gemini HTTP {e.code} ({target_model}): {err_body[:180]}")
                if not tools and e.code in (400, 404):
                    try:
                        return self._native_chat_fallback(target_model, messages, temperature, max_tokens, response_format)
                    except Exception:
                        pass
                if e.code in (400, 404, 429, 500, 502, 503, 504):
                    continue
                raise last_err from e
            except Exception as e:
                last_err = e
                continue

            choice0 = (body.get("choices") or [{}])[0]
            msg = choice0.get("message") or {}
            content = msg.get("content") or ""
            if response_format and response_format.get("type") == "json_object":
                content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.I)
                content = re.sub(r"\s*```$", "", content.strip())
            tcs = []
            for idx, tc in enumerate(msg.get("tool_calls") or []):
                fn = tc.get("function") or {}
                tcs.append(_AttrObj(
                    index=idx,
                    id=tc.get("id") or f"call_{idx}",
                    type="function",
                    function=_AttrObj(name=fn.get("name", ""), arguments=fn.get("arguments", "{}")),
                ))
            return _AttrObj(choices=[_AttrObj(message=_AttrObj(content=content, tool_calls=tcs))])

        # Final emergency fallback to Groq if all Gemini models returned 503/429 and Groq key exists
        if self._groq_stt is not None:
            try:
                print_ar("🔄 كل موديلات Gemini مشغولة حالياً — بستخدم Groq احتياطياً لهذا الرد...")
                g_kwargs = dict(
                    model="llama-3.3-70b-versatile",
                    messages=cleaned_msgs,
                    temperature=float(temperature) if temperature is not None else 0.6,
                    max_tokens=int(max_tokens) if max_tokens is not None else 500,
                    stream=bool(stream),
                )
                if tools:
                    g_kwargs["tools"] = tools
                    if tool_choice:
                        g_kwargs["tool_choice"] = tool_choice
                if response_format:
                    g_kwargs["response_format"] = response_format
                return self._groq_stt.chat.completions.create(**g_kwargs)
            except Exception:
                pass

        raise last_err or RuntimeError("All Gemini Flash models are currently unavailable")

    def _stream_from_open_resp(self, resp):

        def _gen():
            try:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        pkt = json.loads(data_str)
                    except Exception:
                        continue
                    choices = pkt.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    raw_tcs = delta.get("tool_calls") or []
                    tc_objs = []
                    for idx_f, tc in enumerate(raw_tcs):
                        fn = tc.get("function") or {}
                        tc_objs.append(_AttrObj(
                            index=tc.get("index", idx_f),
                            id=tc.get("id"),
                            function=_AttrObj(
                                name=fn.get("name", ""),
                                arguments=fn.get("arguments", ""),
                            ),
                        ))
                    yield _AttrObj(choices=[_AttrObj(delta=_AttrObj(
                        content=text,
                        tool_calls=tc_objs if tc_objs else None,
                    ))])
            finally:
                try:
                    resp.close()
                except Exception:
                    pass

        return _gen()

    def _audio_transcribe(self, file, model="whisper-large-v3-turbo", prompt="",
                          language="ar", temperature=0.0, response_format=None, **kw):
        """Use Groq Whisper if a Groq key is available; otherwise transcribe via Gemini Flash."""
        if self._groq_stt is not None:
            try:
                g_kwargs = dict(file=file, model=model, prompt=prompt,
                                temperature=temperature, language=language)
                if response_format:
                    g_kwargs["response_format"] = response_format
                return self._groq_stt.audio.transcriptions.create(**g_kwargs)
            except Exception as e:
                print_ar(f"⚠️ Groq STT fallback to Gemini Flash: {str(e)[:80]}")

        wav_bytes = file[1] if isinstance(file, (tuple, list)) else file.read()
        b64_audio = base64.b64encode(wav_bytes).decode("ascii")
        if language == "ar":
            sys_inst = (
                "You are the speech-to-text of a voice assistant. The speaker gives a short command "
                "in Egyptian Arabic and may say the English name of an app, a game or a website. "
                "Write exactly the words that were said and nothing else: Arabic words in Arabic "
                "letters, English names in English letters. Do not translate, correct, answer or "
                "explain, and add no punctuation. If there is no clear speech, return nothing. "
                "Words and names that are often said (use one only if it was really said): "
                + prompt[:400]
            )
        else:
            sys_inst = (
                "You are the speech-to-text of a voice assistant. Write exactly the English words "
                "that were said and nothing else, with no punctuation. If there is no clear speech, "
                "return nothing. Names that are often said (use one only if it was really said): "
                + prompt[:400]
            )
        body = json.dumps({
            "contents": [{
                "parts": [
                    {"text": sys_inst},
                    {"inline_data": {"mime_type": "audio/wav", "data": b64_audio}},
                ]
            }],
            # room to spare: a model that thinks first spends part of this before the words
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 512},
        }).encode("utf-8")
        # a model that's out of quota (429) or busy (503) mustn't leave the command empty: try the next one
        # (three at most, 10 s each: after that the local Whisper hears it instead of the user waiting minutes)
        res, last_err = None, None
        for m in self._candidate_models()[:3]:
            req = urllib.request.Request(
                self.NATIVE_URL.format(model=m, key=self.api_key),
                data=body, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code not in (429, 500, 503, 404):
                    raise
        if res is None:
            raise last_err or RuntimeError("no model could transcribe")
        cands = res.get("candidates") or []
        text = ""
        if cands:
            parts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
        return _AttrObj(text=text, segments=[])


# First run on a new PC (no key at all yet): ask for the keys in a small window instead of stopping.
if not (any(_scan_env_file()) or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GROQ_API_KEY") or os.environ.get("YOBI_NO_KEY")):
    try:
        from first_run import ask_keys
        if ask_keys(_ENV_FILE) is None:
            print_ar("👋 مفيش مفتاح — يوبي مش هيشتغل من غيره")
            sys.exit(0)
    except SystemExit:
        raise
    except Exception as _e:
        print_ar(f"⚠️ شاشة المفاتيح: {_e}")

_env_gemini, _env_groq = _scan_env_file()
_raw_gemini_key = (
    _env_gemini
    or os.environ.get("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or ""
).strip()
_raw_groq_key = (
    _env_groq
    or os.environ.get("GROQ_API_KEY")
    or ""
).strip()

# Smart detection: if the user pasted a Gemini key (starts with "AIza") into GROQ_API_KEY
if not _raw_gemini_key and _raw_groq_key.startswith("AIza"):
    _raw_gemini_key = _raw_groq_key
    _raw_groq_key = ""

GEMINI_API_KEY = _raw_gemini_key
GROQ_API_KEY = _raw_groq_key

_groq_stt_only = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

if GEMINI_API_KEY:
    groq_client = GeminiClient(gemini_key=GEMINI_API_KEY, groq_stt_client=_groq_stt_only)
    _MODEL_CANDIDATES = [
        "gemini-3.5-flash",          # gemini-3.8-flash hung for 60 s in testing (2026-11-08): last
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    ]
    print_ar("✨ تم تفعيل Google Gemini Flash كعقل أساسي ليوبي!")
elif _groq_stt_only is not None:
    print_ar("⚠️ GEMINI_API_KEY مش موجود في .env — شغال مؤقتاً بمفتاح Groq (ضيف GEMINI_API_KEY في .env لتشغيل Gemini Flash)")
    groq_client = _groq_stt_only
    _MODEL_CANDIDATES = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-20b",
    ]
else:
    # no key at all (a friend chose "continue without a key"): everyday commands only, understood
    # on this PC by local_brain and heard by the local Whisper; chat and questions need Gemini
    print_ar("🔌 مفيش مفتاح — يوبي شغال أوامر بس بالموديل المحلي (الدردشة محتاجة مفتاح Gemini)")
    groq_client = None
    _MODEL_CANDIDATES = []

_RUNTIME_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".yobi_runtime.json")


def _pick_working_model():
    forced = os.environ.get("YOBI_MODEL")
    if forced:
        return forced
    if groq_client is None:
        return "local"
    try:
        with open(_RUNTIME_CACHE, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if (time.time() - cached.get("ts", 0) < 12 * 3600
                and cached.get("model") in _MODEL_CANDIDATES):
            print_ar(f"✅ الموديل (من الكاش): {cached['model']}")
            return cached["model"]
    except Exception:
        pass
    m = _probe_models()
    try:
        with open(_RUNTIME_CACHE, "w", encoding="utf-8") as f:
            json.dump({"model": m, "ts": time.time()}, f)
    except Exception:
        pass
    return m


def _probe_models():
    for m in _MODEL_CANDIDATES:
        try:
            groq_client.chat.completions.create(
                model=m,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            print_ar(f"✅ الموديل الشغال: {m}")
            return m
        except Exception as e:
            err = str(e)
            if len(err) > 120:
                err = err[:120] + "..."
            print_ar(f"❌ {m} مش متاح ({err})")
    print_ar("⚠️ مفيش موديل متاح — هستخدم أول واحد")
    return _MODEL_CANDIDATES[0]


BEST_MODEL = _pick_working_model()


def _find_nvidia_dll_dirs():
    import importlib
    dirs = []
    for pkg_name in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            pkg = importlib.import_module(pkg_name)
        except ModuleNotFoundError:
            continue
        pkg_root = list(pkg.__path__)[0]
        for subfolder in ("bin", "lib"):
            candidate = os.path.join(pkg_root, subfolder)
            if os.path.isdir(candidate):
                dirs.append(candidate)
    return dirs


_nvidia_dll_dirs = _find_nvidia_dll_dirs()
if platform.system() == "Windows":
    for _d in _nvidia_dll_dirs:
        os.add_dll_directory(_d)
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")

CURRENT_OS = platform.system().lower()
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
if not os.path.exists(CONFIG_PATH):           # a new PC: start from the shared defaults
    import shutil
    shutil.copyfile(os.path.join(os.path.dirname(CONFIG_PATH), "config.example.json"), CONFIG_PATH)
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

LEARNED_COMMANDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_commands.json")


def load_learned_commands():
    if os.path.exists(LEARNED_COMMANDS_PATH):
        try:
            with open(LEARNED_COMMANDS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_learned_commands(data):
    try:
        with open(LEARNED_COMMANDS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


LEARNED_COMMANDS = load_learned_commands()
LAST_LEARNED_KEY = None

APPS_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installed_apps_cache.json")
INSTALLED_APPS = load_or_scan_installed_apps(APPS_CACHE_PATH, CURRENT_OS)

print_ar("🎮 جاري قراءة مكتبات Steam و Epic Games...")
GAMES = scan_all_games()
print_ar(f"✅ لقيت {len(GAMES)} لعبة.")

try:
    from launcher_discovery import scan_all_other_launchers
    _extra = scan_all_other_launchers()
    if _extra:
        GAMES.update(_extra)
        print_ar(f"✅ لقيت {len(_extra)} لعبة إضافية من launchers تانية.")
except Exception as _e:
    print_ar(f"⚠️ launcher_discovery: {_e}")

TASKS = load_tasks()
print_ar(f"🧠 عندي {len(TASKS)} مهمة متعلمة.")

try:
    _scan_cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "smart_scan_cache.json")
    if not os.path.exists(_scan_cache):
        print_ar("🔍 أول تشغيل — بعمل فحص شامل للجهاز...")
        run_full_scan(force=True)
except Exception as _e:
    print_ar(f"⚠️ smart_scan: {_e}")


# ==========================================
# 2. Hybrid Whisper Loading
# ==========================================
def _load_wake_model():
    size = os.environ.get("YOBI_WAKE_MODEL", "small")
    try:
        if (CONFIG.get("hearing") or {}).get("stt_local_device") == "cpu":
            raise RuntimeError("stt_local_device = cpu")
        m = WhisperModel(size, device="cuda", compute_type="float16")
        # the GPU libraries load on first use: a PC with a card but without them (cublas...) fails
        # here, once, not on every wake check later
        import numpy as np
        list(m.transcribe(np.zeros(8000, dtype=np.float32), language="ar", beam_size=1)[0])
        return m
    except Exception as e:
        print_ar(f"⚠️ مفيش GPU شغال ({str(e)[:80]}) — هشتغل على الـ CPU")
        cpu_size = "base" if size in ("small", "medium", "large-v3") else size
        return WhisperModel(cpu_size, device="cpu", compute_type="int8")


class _LazyWhisper:
    def __init__(self):
        self._m = None
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            if self._m is None:
                print_ar("🧠 جاري تحميل Whisper للنداء...")
                self._m = _load_wake_model()
            return self._m

    def transcribe(self, *args, **kwargs):
        return self.get().transcribe(*args, **kwargs)


wake_model = _LazyWhisper()
_STT = None


def transcribe_local(audio, lang, model, initial_prompt=None):
    if _audio_is_silent(audio):
        return ""
    wav_bytes = audio.get_wav_data()
    with io.BytesIO(wav_bytes) as wav_io:
        segments, _ = model.transcribe(
            wav_io, language=lang, beam_size=1, vad_filter=True,
            initial_prompt=initial_prompt,
        )
        text = "".join(segment.text for segment in segments)
    text = text.strip().lower()
    if _is_hallucination(text):
        return ""
    return text


def transcribe_groq(audio, prompt_text="", lang="ar"):
    if _STT is not None:
        return _STT.transcribe(audio, prompt=prompt_text, lang=lang)
    if _audio_is_silent(audio) or groq_client is None:        # no key: only the local Whisper hears
        return ""
    try:
        wav_bytes = audio.get_wav_data()
        safe_prompt = (prompt_text or "")[:850]
        kwargs = dict(
            file=("command.wav", wav_bytes),
            model="whisper-large-v3",
            prompt=safe_prompt,
            temperature=0.0,
        )
        if lang:
            kwargs["language"] = lang
        response = groq_client.audio.transcriptions.create(**kwargs)
        text = response.text.strip().lower()
        if _is_hallucination(text):
            print_ar(f"🚫 تجاهلت هالوسينيشن Whisper: '{text}'")
            return ""
        return text
    except Exception as e:
        print_ar(f"⚠️ خطأ في سمع Groq: {e}")
        return ""


# ==========================================
# 3. Parsers & Logic
# ==========================================
def detect_intent(text):
    if not text:
        return None
    text_l = text.lower().strip()
    first_words = " ".join(text_l.split()[:4])

    open_verbs = [
        "open", "start", "launch", "run",
        "افتح", "افتحلي", "افتحي", "شغل", "شغلي", "شغللي", "يفتح", "وفتح", "وشغل",
    ]
    close_verbs = [
        "close", "kill", "terminate", "stop",
        "اقفل", "اقفلي", "انهي", "قفل", "اغلق", "سكر",
    ]
    install_verbs = ["install", "download", "setup", "نزل", "سطب"]

    for w in open_verbs:
        if re.search(rf"(?:^|\s){re.escape(w)}(?:\s|$)", first_words):
            return "open"
    for w in close_verbs:
        if re.search(rf"(?:^|\s){re.escape(w)}(?:\s|$)", first_words):
            return "close"
    for w in install_verbs:
        if re.search(rf"(?:^|\s){re.escape(w)}(?:\s|$)", first_words):
            return "install"
    return None


def parse_command_llm(command, known_targets):
    if groq_client is None:
        return None, None
    try:
        prompt = f"""You are 'Yobi'. Convert command to JSON. Intents: "open", "close", "install", "unknown".
        Rules: "افتح" -> open, "اقفل" -> close.

        Choosing the entity for "open"/"close":
        - The speech-to-text is noisy Egyptian Arabic. Map what was said to the closest name in Targets (by sound, e.g. "يورو ترك" -> "euro truck simulator 2", "فالو" -> "valorant") and return that name EXACTLY as listed.
        - Prefer local apps/games over websites when both exist (valorant the game, not playvalorant.com).
        - Return a URL ONLY for famous sites you are certain about (youtube, facebook, netflix...). NEVER invent a domain.
        - If nothing in Targets plausibly matches, or the text is gibberish, return {{"intent": "unknown", "entity": ""}}.
        - If the command is conversational (a question, opinion, greeting, etc.), return {{"intent": "unknown", "entity": ""}}.

        Respond ONLY with pure JSON.
        Examples:
        {{"intent": "open", "entity": "spotify"}}
        {{"intent": "open", "entity": "https://www.facebook.com"}}
        {{"intent": "close", "entity": "chrome"}}
        {{"intent": "unknown", "entity": ""}}

        Command: "{command}"
        Targets: {known_targets}"""
        response = groq_client.chat.completions.create(
            model=BEST_MODEL,
            messages=[
                {"role": "system", "content": "Output pure JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("intent"), data.get("entity")
    except Exception as e:
        print_ar(f"⚠️ خطأ في عقل Groq: {e}")
        return None, None


def _match_known_target_in_text(cmd_l, known_targets):
    """Matches known targets safely (longest first, word-bounded for short names
    so 'x' or 'ea' never match inside 'excel' or 'steam')."""
    candidates = [t for t in known_targets if isinstance(t, str) and len(t.strip()) >= 2]
    for t in sorted(set(candidates), key=len, reverse=True):
        tl = t.lower().strip()
        if len(tl) <= 4:
            if re.search(rf"(?:^|\s){re.escape(tl)}(?:\s|$)", cmd_l):
                return t
        elif tl in cmd_l:
            return t
    return None


def parse_command(command, known_targets):
    cmd_norm = command.lower().strip()
    if cmd_norm in LEARNED_COMMANDS:
        return LEARNED_COMMANDS[cmd_norm]["intent"], LEARNED_COMMANDS[cmd_norm]["target"]

    close = difflib.get_close_matches(cmd_norm, LEARNED_COMMANDS.keys(), n=1, cutoff=0.84)
    if close:
        return LEARNED_COMMANDS[close[0]]["intent"], LEARNED_COMMANDS[close[0]]["target"]

    intent = detect_intent(command)
    target = _match_known_target_in_text(cmd_norm, known_targets)
    if intent and target:
        return intent, target

    intent, target = parse_command_llm(command, known_targets)
    if intent == "unknown":
        return None, None
    return intent, target


def parse_command_source(command):
    cmd_norm = command.lower().strip()
    if cmd_norm in LEARNED_COMMANDS:
        return "learned"
    if difflib.get_close_matches(cmd_norm, LEARNED_COMMANDS.keys(), n=1, cutoff=0.84):
        return "learned"
    return "llm"


def _is_not_found(res):
    return res in ("مش لاقي البرنامج ده", "مش لاقي حاجة أفتحها", "البرنامج مش شغال")


_PROCESS_ALIASES = {
    "vscode": ["code"],
    "visual studio code": ["code"],
    "microsoft visual studio code": ["code"],
    "edge": ["msedge"],
    "microsoft edge": ["msedge"],
    "chrome": ["chrome"],
    "google chrome": ["chrome"],
    "brave": ["brave"],
    "word": ["winword"],
    "excel": ["excel"],
    "powerpoint": ["powerpnt"],
    "riot client": ["riotclientservices", "riotclientux"],
    "league of legends": ["leagueclient", "league of legends", "leagueclientux"],
    "valorant": ["valorant", "valorant-win64-shipping"],
    "teamfight tactics": ["tftclient", "leagueclient"],
    "euro truck simulator 2": ["eurotrucks2"],
    "euro truck simulator": ["eurotrucks2"],
    "assetto corsa competizione": ["acc", "ac2-win64-shipping"],
    "forza horizon 6": ["forzahorizon6"],
    "forza horizon": ["forzahorizon6", "forzahorizon5"],
    "elden ring": ["eldenring"],
    "the last of us": ["tlou-i"],
    "the last of us part i": ["tlou-i"],
    "the outlast trials": ["totclient-win64-shipping"],
    "rocket league": ["rocketleague"],
    "overwatch": ["overwatch"],
    "minecraft": ["javaw", "tlauncher", "minecraft.windows"],
    "tlauncher": ["tlauncher", "javaw"],
    "wemod": ["wand", "wemod"],
}


class DesktopAgent:
    def __init__(self, config, installed_apps, games):
        self.websites = config["websites"]
        self.local_apps = config["local_apps"].get(CURRENT_OS, {})
        self.installed_apps = installed_apps
        self.games = games
        self.recognizer = None

    def _catalog_sig(self):
        return (len(self.websites), len(self.local_apps), len(self.games),
                len(self.installed_apps))

    @property
    def catalog(self):
        sig = self._catalog_sig()
        if getattr(self, "_catalog", None) is None or self._catalog_sig_cache != sig:
            self._catalog = _tr.Catalog(self.websites, self.local_apps,
                                        self.games, self.installed_apps)
            self._catalog_sig_cache = sig
        return self._catalog

    def resolve(self, name, utterance=None, stt_low=False):
        return _tr.resolve(self.catalog, name, utterance=utterance, stt_low=stt_low,
                           cfg=CONFIG.get("resolver"))

    def launch(self, entry):
        launch = entry.launch
        if entry.kind == "site":
            webbrowser.open(launch)
            return "تم فتح الموقع"
        if entry.kind == "game":
            if isinstance(launch, list):
                subprocess.Popen(launch)
            else:
                os.startfile(launch)
            return "تم تشغيل اللعبة 🎮"
        if entry.kind == "app" and not os.path.exists(str(launch)):
            subprocess.Popen(["cmd", "/c", "start", "", launch], shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "تم تشغيل البرنامج"
        os.startfile(launch)
        return "تم تشغيل البرنامج"

    def find_on_disk(self, name):
        found = bounded_game_search((name or "").lower().strip())
        if found and exe_matches(name, found):
            return found
        return None

    def open_target(self, target):
        if not target:
            return "مش لاقي حاجة أفتحها"
        target = target.lower().strip()

        if not _tr.is_url(target):
            r = self.resolve(target)
            if r.status == "ok" or (r.status == "ask" and r.score >= 0.8):
                return self.launch(r.best)
            found = self.find_on_disk(target)
            if found:
                os.startfile(found)
                return "لقيتها وفتحتها! 🚀"
            return "مش لاقي البرنامج ده"

        url = target if target.startswith(("http://", "https://")) else f"https://{target}"
        webbrowser.open(url)
        return "تم فتح الموقع"

    def kill_process(self, process):
        process = (process or "").lower().strip().replace(".exe", "")
        if not process:
            return "البرنامج مش شغال"

        candidates = {process}
        if process in _PROCESS_ALIASES:
            candidates.update(_PROCESS_ALIASES[process])

        try:
            res = self.resolve(process)
            if res.best is not None and res.status == "ok":   # only a name the resolver is sure of
                disp = res.best.display.lower().strip()
                candidates.add(disp)
                if disp in _PROCESS_ALIASES:
                    candidates.update(_PROCESS_ALIASES[disp])
                launch = res.best.launch
                if isinstance(launch, list) and launch:
                    launch = launch[0]
                if isinstance(launch, str) and launch.lower().endswith(".exe"):
                    stem = os.path.splitext(os.path.basename(launch))[0].lower()
                    if stem:
                        candidates.add(stem)
        except Exception:
            pass

        procs = []
        for proc in psutil.process_iter(["name"]):
            try:
                pname = (proc.info["name"] or "").lower().replace(".exe", "")
                if pname:
                    procs.append((proc, pname))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        targets = pick_processes(procs, candidates)
        # ask nicely first (the app can save), force only what's still running after 3 s
        for proc in targets:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        _, alive = psutil.wait_procs(targets, timeout=3)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return "تم الإغلاق" if targets else "البرنامج مش شغال"


# ==========================================
# 4. Background Voice Loop
# ==========================================
def voice_loop(island, agent, known_targets, listening_enabled):
    global _STT, _COMPANION
    H = dict(HEARING_DEFAULTS)
    H.update(CONFIG.get("hearing") or {})
    _here = os.path.dirname(os.path.abspath(__file__))

    def _abs(p):
        return p if (not p or os.path.isabs(p) or not str(p).lower().endswith((".onnx", ".tflite", ".csv"))) \
            else os.path.join(_here, p)

    if yobi_latency is not None:
        yobi_latency.tracker.configure(csv_path=_abs(H["latency_csv"]) if H["latency_csv"] else None,
                                       enabled=bool(H["latency_log"]), log=print_ar)

    audio_engine = None
    if get_audio_engine is not None and H["audio_engine"]:
        audio_engine = get_audio_engine(
            create=True, aec=H["aec"], noise_suppression=H["noise_suppression"],
            agc=H["agc"], input_device=H["input_device"], output_device=H["output_device"],
            extra_delay_ms=H["aec_extra_delay_ms"], log=print_ar)

    def _wake_by_key():
        """Settings → wake: "key" = only the hotkey or the island wakes Yobi, no model listens."""
        tools = getattr(island, "_tools", None)
        cfg = tools.cfg if tools is not None else (CONFIG.get("island") or {})
        return cfg.get("wake") == "key"

    def _wake_key():
        tools = getattr(island, "_tools", None)
        cfg = tools.cfg if tools is not None else (CONFIG.get("island") or {})
        return cfg.get("wake_key") or CONFIG.get("hotkey", "ctrl+alt+y")

    wake_detector = None
    if WakeWordDetector is not None and H["wake_model"]:
        try:
            wake_detector = WakeWordDetector(
                _abs(H["wake_model"]), threshold=H["wake_threshold"],
                patience=H["wake_patience"], log=print_ar, debug=H["wake_debug"])
        except Exception as e:
            print_ar(f"ℹ️ النداء offline مش شغال ({str(e)[:90]}) — هستخدم Whisper للنداء")
            wake_detector = None
    if wake_detector is None and not _wake_by_key():
        threading.Thread(target=wake_model.get, daemon=True).start()

    vocab = None
    if PersonalVocab is not None:
        vocab = PersonalVocab(max_chars=H["vocab_max_chars"],
                              targets_source=lambda: agent.catalog.display_names(
                                  limit=80, prefer=list(vocab.usage) if vocab else None))

    if STTEngine is not None:
        _STT = STTEngine(
            groq_client, engine=H["stt_engine"], order=H["stt_order"],
            local_model=H["stt_local_model"], local_device=H["stt_local_device"],
            local_compute=H["stt_local_compute"], vocab=vocab,
            is_silent=_audio_is_silent, is_hallucination=_is_hallucination,
            log=print_ar, prompt_chars=H["vocab_max_chars"])
        if H["stt_engine"] == "local" or H["stt_warmup_local"]:
            _STT.warmup()

    try:
        get_tts_engine().configure(backend=H["tts_backend"], piper_model=H["piper_model"],
                                   piper_length_scale=H["piper_length_scale"],
                                   piper_exe=H["piper_exe"])
    except Exception as e:
        print_ar(f"⚠️ إعداد TTS: {e}")

    def _verify_wake(audio):
        t = transcribe_local(audio, "ar", wake_model, initial_prompt="يا يوبي")
        return _has_wake(t)

    recognizer = VADRecognizer(
        aggressiveness=CONFIG.get("vad_aggressiveness", 2),
        end_silence_ms=CONFIG.get("end_silence_ms", 600),
        hotkey=_wake_key(),
        is_speaking=is_speaking,
        stop_speaking=stop_speaking,
        engine=audio_engine,
        wake=wake_detector,
        barge_in=H["barge_in"],
        verify_wake=_verify_wake if (wake_detector and H["wake_verify_whisper"]) else None,
        log=print_ar,
    )
    agent.recognizer = recognizer
    _tts_status = get_tts_engine().status()
    print_ar(
        "👂 السمع: "
        + ("إلغاء صدى ✅" if recognizer.full_duplex else "إلغاء صدى ❌")
        + " | " + (f"نداء offline ✅ ({wake_detector.name})" if wake_detector else "نداء بـ Whisper")
        + " | STT: " + (H["stt_engine"] if _STT else "groq")
        + f" | TTS: {_tts_status['backend']}"
        + (" + Piper احتياطي" if _tts_status["piper_available"] else "")
    )
    mic = recognizer.microphone()

    with mic as source:
        print_ar("🎙️ بظبط المايك... (ثانية واحدة)")
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
    print_ar(f"⌨️ اختصار النداء/المقاطعة: {_wake_key()}")
    if getattr(island, "_tools", None) is not None:
        island._tools.on_wake_key = recognizer.set_hotkey      # the settings window changes it live
    key_chime = [0.0]
    turn_gen = [0]              # raised when Yobi starts listening: a late "hide" from the turn before is dropped
    KEY_HINT = "سامعك.. دوس الزرار تاني لما تخلص ⌨️"

    def _key_pressed():         # heard and shown at once, even when the loop is busy
        if recognizer.key_capturing:        # the second press: done talking
            island.after(0, lambda: island.set_state("thinking"))
            return
        key_chime[0] = time.time()
        play_wake()
        if listening_enabled.is_set() and not context.in_conversation:
            turn_gen[0] += 1
            island.after(0, lambda: island.set_state("listening", KEY_HINT))
    recognizer.on_hotkey = _key_pressed

    wake_words = CONFIG.get("wake_words",
                            ["يوبي", "يو بي", "yobi", "youbi", "yopi", "يا يوبي", "يوبى", "يايوبي", "يا يوبى", "بوبي", "يا بوبي"])
    # a wake word counts only as a word of its own: "ub" mustn't match inside "youtube"
    _WAKE_RE = wake_pattern(wake_words)

    def _has_wake(text):
        return bool(_WAKE_RE and _WAKE_RE.search(text or ""))

    refresh_phrases = ["حدث البرامج", "refresh apps"]
    scan_phrases = refresh_phrases + [
        "افحص جهازي", "فحص جهازي", "فحص الجهاز", "فحص شامل",
        "افحص كل البرامج", "افحص البرامج", "سكان للجهاز", "deep scan",
    ]
    forget_phrases = ["انسى ده", "forget that"]
    learn_task_phrases = ["تعلم مهمة", "learn task", "علمني مهمة"]
    save_login_phrases = [
        "احفظ بيانات", "احفظ لوجين", "علمني ادخل", "علمني أدخل",
        "save credentials", "save login", "سجل بيانات الدخول",
    ]
    forget_login_phrases = [
        "امسح بيانات", "امسح لوجين", "forget credentials",
        "امسح بيانات الدخول",
    ]
    forget_learned_phrases = [
        "انسى اللي اتعلمته", "forget learned", "امسح التعلم",
        "امسح كل التعلم",
    ]
    exit_phrases = [
        "خلاص", "شكرا", "شكراً", "باي", "مع السلامة",
        "bye", "thanks", "done", "يكفي", "كفاية",
    ]

    context = ContextMemory()
    addressed = AddressedClassifier(llm_client=groq_client, llm_model=BEST_MODEL)

    # Yobi just asked something (buttons, or a reply ending in "؟"): a short answer is meant for Yobi
    def _marks_question(name):
        orig = getattr(island, name)

        def wrapped(*a, **k):
            text = str(a[0] if a else k.get("question") or k.get("text") or "")
            if name == "ask" or text.rstrip().endswith(("؟", "?")):
                addressed.mark_yobi_asked()
            return orig(*a, **k)
        setattr(island, name, wrapped)
    for _name in ("ask", "say"):
        _marks_question(_name)
    chat_engine = ChatEngine(groq_client, BEST_MODEL)
    learner = SelfLearner()
    chat_mode_active = False

    pending_suggestion = {"app": None, "expires": 0.0}

    _stats = learner.stats()
    print_ar(f"🧠 اتعلمت {_stats['total_commands']} أمر "
             f"({_stats['well_learned']} منهم مضمون).")

    def _on_sched_notify(msg):
        island.after(0, lambda m=msg: island.set_state("info", f"⏰ {m}"))

    def _on_sched_execute(cmd):
        island.after(0, lambda c=cmd: island.set_state("info", f"⏰ بنفذ: {c}"))
        si, st = parse_command(cmd, known_targets)
        r = None
        if si == "open" and st:
            r = agent.open_target(st)
        elif si == "close" and st:
            r = agent.kill_process(st)
        else:
            sm = match_system_command(cmd)
            if sm:
                af, _, _ = sm
                r = af()
        if r:
            island.after(0, lambda x=r: island.set_state("success", x))

    scheduler = TaskScheduler(on_notify=_on_sched_notify, on_execute=_on_sched_execute)

    def _on_yobi_suggest(app_name, message):
        pending_suggestion["app"] = app_name
        pending_suggestion["expires"] = time.time() + 30

        def _answer(value):
            if pending_suggestion["app"] != app_name:
                return
            pending_suggestion["app"] = None
            pending_suggestion["expires"] = 0.0
            if value == "yes":
                threading.Thread(target=_accept_suggestion, args=(app_name,),
                                 daemon=True).start()
            else:
                island.say("تمام، سيبناها 👌", state="info")

        def _show():
            island.ask(message, [("افتحه ✅", "yes"), ("مش دلوقتي", "no")],
                       _answer, timeout_ms=30000)

            def _auto_hide():
                if (pending_suggestion["app"] == app_name
                        and time.time() >= pending_suggestion["expires"]):
                    pending_suggestion["app"] = None
            island.after(30500, _auto_hide)

        island.after(0, _show)

    def _accept_suggestion(app):
        print_ar(f"👍 المستخدم وافق على اقتراح (زرار): {app}")
        island.after(0, lambda: island.set_state("thinking"))
        r = agent.open_target(app)
        context.record("open", app, r)
        chat_engine.set_last_action(r)
        island.after(0, lambda x=r: island.set_state("success", x))
        play_success()

    suggestions = SmartSuggestions(on_suggest=_on_yobi_suggest)

    # ── v6: Yobi checks on you (water, tea, gym, music, series) ──
    companion = None
    comp_cfg = CONFIG.get("companion") or {}
    if Companion is not None:
        def _c_ask(question, options, on_answer, timeout_s):
            island.after(0, lambda: island.ask(question, options, on_answer,
                                               timeout_ms=int(timeout_s * 1000)))

        def _c_say(text):
            island.after(0, lambda t=text: island.say(t, state="info"))

        def _c_free():
            g = _GAME_COMPANION
            try:
                if g is not None and g.get_current_game():
                    return False
            except Exception:
                pass
            if context.in_conversation:
                return False
            return island.is_free(min_idle_s=comp_cfg.get("min_idle_s", 90))

        def _c_run(cmd):
            threading.Thread(target=lambda: handle_command(cmd, None, trusted=True),
                             daemon=True).start()

        def _c_game():
            g = _GAME_COMPANION
            try:
                return g.get_current_game() if g is not None else None
            except Exception:
                return None

        def _c_idle():
            try:
                import ctypes

                class _LII(ctypes.Structure):
                    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
                lii = _LII()
                lii.cbSize = ctypes.sizeof(lii)
                if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                    return 0.0
                idle = (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
            except Exception:
                return 0.0
            if idle >= float(comp_cfg.get("away_min", 10)) * 60 and _audio_playing():
                return 0.0
            return idle

        def _audio_playing():
            try:
                import ctypes
                import comtypes
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
                comtypes.CoInitialize()
                dev = AudioUtilities.GetSpeakers()
                dev = getattr(dev, "_dev", dev)
                iface = dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
                meter = ctypes.cast(iface, ctypes.POINTER(IAudioMeterInformation))
                return float(meter.GetPeakValue()) > 0.01
            except Exception:
                return False

        try:
            companion = Companion(_c_ask, _c_say, is_free=_c_free, run_command=_c_run,
                                  config=comp_cfg, log=print_ar,
                                  get_game=_c_game, idle_s=_c_idle)
            companion.start()
            _COMPANION = companion
            island.after(0, lambda: island.set_companion_toggle(
                lambda: companion.enabled, companion.toggle))
            if hasattr(island, "set_companion"):          # new island: water count on the panel
                island.after(0, lambda: island.set_companion(companion))
            print_ar("💬 يوبي هيسألك ويطمن عليك " + ("✅" if companion.enabled else "(مقفول)"))
        except Exception as e:
            print_ar(f"⚠️ أسئلة يوبي مش شغالة: {e}")
            companion = None

    def _barge_in_check(audio):
        if _wake_by_key():                      # the hotkey interrupts; no Whisper listens
            return False
        t = transcribe_local(audio, "ar", wake_model, initial_prompt="يا يوبي")
        hit = _has_wake(t)
        if hit:
            print_ar(f"✋ قاطعتني: '{t}'")
        return hit

    recognizer.barge_in_check = _barge_in_check

    def _ask_confirm(description):
        done = threading.Event()
        res = {"ok": False, "answered": False}

        def _answer(value):
            res["ok"] = (value == "yes")
            res["answered"] = True
            done.set()

        island.after(0, lambda d=description: island.ask(
            f"متأكد إنك عايز {d}؟", [("أيوه، نفّذ ✅", "yes"), ("لا، إلغاء", "no")],
            _answer, timeout_ms=20000))
        done.wait(21)
        if not res["ok"]:
            msg = "تمام، لغيتها 👌" if res["answered"] else "ملغية، مردّتش عليّا ⏱️"
            island.after(0, lambda m=msg: island.say(m, state="info", chime=False))
        return res["ok"]

    def _maybe_auto_login(target_used):
        launcher = launcher_for_game(target_used)
        if not launcher:
            return
        acct_key = resolve_account_key(launcher, target_used)
        acct_label = label_for_account_key(acct_key)

        def _run():
            island.after(0, lambda l=acct_label: island.set_state(
                "thinking", f"بجهزلك {l}... 🔐"))
            try:
                ok = try_auto_login(launcher, game_name=target_used,
                                    on_step=lambda m: print_ar(f"🔐 {m}"))
                if ok:
                    island.after(0, lambda l=acct_label: island.set_state(
                        "success", f"دخلت بحساب {l} ✅"))
                    speak(f"دخلت بحساب {acct_label}")
                else:
                    island.after(0, lambda: island.set_state("info", "اكتب بياناتك بنفسك ⌨️"))
            except Exception as e:
                print_ar(f"⚠️ فشل الـ auto-login: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _on_tool_opened(target, result):
        context.record("open", target, result)
        chat_engine.set_last_action(result)
        _maybe_auto_login(target)

    _dcfg = CONFIG.get("dataset") or {}
    try:
        recorder = DatasetRecorder(enabled=_dcfg.get("enabled", True),
                                   save_audio=_dcfg.get("save_audio", True),
                                   max_audio_mb=_dcfg.get("max_audio_mb", 2000),
                                   log=print_ar)
    except Exception as e:
        print_ar(f"⚠️ dataset recorder مش شغال: {e}")
        recorder = DatasetRecorder(enabled=False)

    _icfg = CONFIG.get("intent_model") or {}
    intent_model = None
    if _icfg.get("enabled", True):
        intent_model = IntentModel.load(log=print_ar)
        if intent_model is not None and _icfg.get("threshold"):
            intent_model.threshold = float(_icfg["threshold"])

    def _record_heard(audio, text):
        try:
            recorder.heard(audio, text,
                           engine=getattr(_STT, "last_engine", None),
                           conf=getattr(_STT, "last_conf", None),
                           low=stt_state["low"])
        except Exception as e:
            print_ar(f"⚠️ dataset recorder: {e}")

    def _commit_learning(phrase, target, action):
        global LAST_LEARNED_KEY
        recorder.label(phrase, "correct", target)
        learner.record_success(phrase, target, action)
        key = (phrase or "").lower().strip()
        if action in ("open", "close") and key and key != str(target).lower():
            LEARNED_COMMANDS[key] = {"intent": action, "target": target}
            save_learned_commands(LEARNED_COMMANDS)
        if action == "open":
            suggestions.record_usage(target)
            if vocab is not None:
                vocab.bump(target)
        LAST_LEARNED_KEY = key                    # so "انسى ده" knows what to forget
        print_ar(f"📚 اتعلمت: '{phrase}' → {target}")

    def _forget_learning(phrase):
        recorder.label(phrase, "wrong")
        key = (phrase or "").lower().strip()
        learner.forget(key)
        if LEARNED_COMMANDS.pop(key, None) is not None:
            save_learned_commands(LEARNED_COMMANDS)

    _rcfg = CONFIG.get("resolver") or {}
    guard = LearningGuard(_commit_learning, delay=float(_rcfg.get("learn_delay_s", 15)),
                          log=print_ar, on_veto=_forget_learning)

    def _ask_choice(question, options):
        done = threading.Event()
        res = {"v": None}

        def _answer(value):
            res["v"] = value
            done.set()

        island.after(0, lambda q=question, o=options: island.ask(
            q, list(o), _answer, timeout_ms=15000))
        done.wait(16)
        return res["v"]

    stt_state = {"low": False}

    tools = YobiTools(
        agent, scheduler, groq_client,
        confirm=_ask_confirm,
        choose=_ask_choice,
        guard=guard,
        on_opened=_on_tool_opened,
        on_action=lambda d: chat_engine.set_last_action(d),
    )
    # the local model: commands with no key or no internet. Trained on this PC's programs, games
    # and sites (and what Yobi learned here) in the background; cached, so later starts are instant
    local_holder = {}

    def _train_local():
        try:
            import local_brain
            local_holder["lb"] = local_brain.for_catalog(agent.catalog, log=print_ar)
        except Exception as e:
            local_holder.setdefault("lb", False)      # failed (not "still training"): don't wait for it
            print_ar(f"⚠️ الموديل المحلي: {e}")

    threading.Thread(target=_train_local, name="local-brain", daemon=True).start()
    brain = Brain(groq_client, CONFIG.get("brain_model") or BEST_MODEL, tools,
                  fallback_engine=chat_engine, local=lambda: local_holder.get("lb"))
    print_ar(f"🧠 العقل الجديد شغال على: {brain.model}" if groq_client is not None
             else "🧠 العقل: الموديل المحلي (أوامر بس، من غير مفتاح)")

    agent.chat_engine = brain
    agent.context = context
    agent.client = groq_client

    def _needs_key():
        """No key: seeing the screen and learning tasks need Gemini — say so instead of failing."""
        if groq_client is not None:
            return False
        from brain import NEEDS_KEY
        island.after(0, lambda: island.say(NEEDS_KEY, state="info"))
        return True

    def _do_chat(user_text):
        nonlocal chat_mode_active
        chat_mode_active = True
        island.after(0, lambda: island.set_state("thinking", "بفكر... 💬"))
        ctx = ChatEngine.build_context(agent, scheduler)
        shown = []

        def _on_sentence(sentence):
            if yobi_latency is not None:
                yobi_latency.mark("llm_first")
            shown.append(sentence)
            if _reply_cfg().get("voice"):
                display = " ".join(shown)[-300:]
                island.after(0, lambda d=display: island.set_state("info", d))
                _tts_speak(sentence)
            else:
                if yobi_latency is not None and len(shown) == 1:
                    yobi_latency.mark("tts_request")
                    yobi_latency.mark("first_audio")
                full = " ".join(shown)
                first = len(shown) == 1
                island.after(0, lambda f=full, c=first: island.say(
                    f, state="info", chime=c and _reply_cfg().get("chime", True)))

        def _on_tool(name, _args):
            island.after(0, lambda: island.set_state("thinking", "بنفذ... ⚙️"))

        if yobi_latency is not None:
            yobi_latency.mark("llm_start")
        brain.run(user_text, on_sentence=_on_sentence, extra_context=ctx,
                  known_targets=agent.catalog.display_names(
                      limit=120, prefer=list(vocab.usage) if vocab else None),
                  on_tool=_on_tool, stt_low=stt_state["low"])
        if not shown:
            island.after(0, lambda: island.set_state("hide"))
        return brain.last_actions

    # a command that opened one of the island's pages ends the conversation, so Yobi
    # doesn't go back to listening (that would take the island and close the page)
    end_conversation = {"now": False}

    def handle_command(command, cmd_audio, trusted=False):
        nonlocal chat_mode_active
        global LAST_LEARNED_KEY
        recorder.bind_phrase(command)

        # 0.-1 — v7: "لا / مش ده / غلط"
        if guard.on_command(command):
            if len(command.split()) <= 3 and not re.search(
                    r"(اقصد|أقصد|قصدت|قصدي|عايز|كنت)", command):
                island.after(0, lambda: island.say(
                    "تمام، مش هحفظها. قولي تقصد إيه 👂", state="info"))
                return

        # 0.0 — v6: answer to a question Yobi asked
        if companion is not None and companion.has_pending_text():
            rep_ = companion.handle_text(command)
            if rep_:
                island.after(0, lambda r=rep_: island.say(r, state="success"))
                return

        # 0. Ambient filter
        if not trusted and not addressed.is_addressed(command):
            print_ar(f"🤫 تجاهلت كلام جانبي: '{command}'")
            return

        # 0.1 — Explicit teach: "علم نفسك إن X يعني Y"
        teach_m = re.match(
            r"(?:علم نفسك إن|علم نفسك ان|اتعلم إن|اتعلم ان|خلي)\s+(.+?)\s+"
            r"(?:يعني|معناها|=|معناه)\s+(.+)",
            command.lower().strip(),
        )
        if teach_m:
            phrase = teach_m.group(1).strip()
            target = teach_m.group(2).strip()
            quick = agent.open_target(target)
            if not _is_not_found(quick):
                learner.record_correction(phrase, target, "open")
                island.after(0, lambda p=phrase, t=target: island.set_state(
                    "success", f"اتعلمت: '{p}' → {t}"))
                play_success()
                speak(f"اتعلمت إن {phrase} يعني {target}")
                return
            else:
                island.after(0, lambda: island.set_state(
                    "error", f"مش لاقي '{target}'"))
                speak("مش لاقي الهدف ده")
                return

        # 0.2 — Forget all learned
        if any(p in command for p in forget_learned_phrases):
            s = learner.stats()
            learner.clear_all()
            msg = f"مسحت كل التعلم ({s['total_commands']} أمر)"
            island.after(0, lambda m=msg: island.set_state("success", m))
            speak(msg)
            return

        # 0.3 — Explicit correction ("لأ، أقصد X")
        corr_m = re.match(
            r"(?:لأ|لا|لأ مش|لأ انا|لا انا|مش كده|مش ده)\s*[،,.]?\s*"
            r"(?:انا\s+)?(?:اقصد|قصدت|أقصد|عايز|كنت عايز)\s+(.+)",
            command.lower().strip(),
        )
        if corr_m:
            correct = corr_m.group(1).strip()
            quick = agent.open_target(correct)
            if not _is_not_found(quick):
                last_failed = learner._data.get("pending", [])
                if guard.last_vetoed:
                    recorder.label(guard.last_vetoed, "corrected", correct)
                    learner.record_correction(guard.last_vetoed, correct)
                    print_ar(f"📚 اتعلمت: '{guard.last_vetoed}' → '{correct}'")
                    guard.last_vetoed = None
                elif last_failed:
                    last_phrase = last_failed[-1].get("phrase", "")
                    if last_phrase:
                        learner.record_correction(last_phrase, correct)
                        print_ar(f"📚 اتعلمت: '{last_phrase}' → '{correct}'")
                island.after(0, lambda: island.set_state("success", "اتعلمت ✅"))
                play_success()
                speak("تمام، اتعلمت")
                return

        # 0.4 — Check self-learner for a known phrase
        learned = learner.lookup(command)
        if learned:
            resolved_to, action = learned
            print_ar(f"🧠 اتعلمت قبل كده: '{command}' → {action} {resolved_to}")
            island.after(0, lambda: island.set_state("thinking"))
            try:
                if action == "open":
                    r = agent.open_target(resolved_to)
                    if not _is_not_found(r):
                        context.record("open", resolved_to, r)
                        guard.propose(command, resolved_to, "open")
                        _maybe_auto_login(resolved_to)
                        island.after(0, lambda x=r: island.set_state("success", x))
                        play_success()
                        speak(r)
                        return
                elif action == "close":
                    r = agent.kill_process(resolved_to)
                    guard.on_close(resolved_to)
                    learner.record_success(command, resolved_to, "close")
                    island.after(0, lambda x=r: island.set_state("success", x))
                    play_success()
                    speak(r)
                    return
            except Exception as e:
                print_ar(f"⚠️ فشل استرجاع التعلم: {e}")

        # 0.45 — v6: things you tell Yobi about yourself
        if companion is not None:
            rep_ = companion.handle_text(command)
            if rep_:
                island.after(0, lambda r=rep_: island.say(r, state="success"))
                return

        # 0.5 — Response to a pending suggestion?
        if pending_suggestion["app"] and time.time() < pending_suggestion["expires"]:
            cmd_l = command.lower().strip()
            yes_words = ["أيوة", "ايوه", "اه", "تمام", "ماشي", "طبعا",
                         "اكيد", "yes", "yep", "ok", "sure", "open it",
                         "افتحه", "افتحها", "شغله", "شغلها"]
            no_words = ["لا", "لأ", "مش دلوقتي", "مش دلوأتي", "بعدين",
                        "no", "not now", "later", "cancel"]

            if any(w in cmd_l for w in yes_words):
                app = pending_suggestion["app"]
                pending_suggestion["app"] = None
                pending_suggestion["expires"] = 0.0
                print_ar(f"👍 المستخدم وافق على اقتراح: {app}")
                island.after(0, lambda: island.set_state("thinking"))
                r = agent.open_target(app)
                context.record("open", app, r)
                chat_engine.set_last_action(r)
                island.after(0, lambda x=r: island.set_state("success", x))
                play_success()
                speak(r)
                return

            if any(w in cmd_l for w in no_words):
                pending_suggestion["app"] = None
                pending_suggestion["expires"] = 0.0
                island.after(0, lambda: island.set_state("info", "تمام، سيبناها 👌"))
                island.after(2000, lambda: island.set_state("hide"))
                speak("تمام")
                return

        # 1. Context references
        ctx_i, ctx_t = context.resolve_reference(command)
        if ctx_i and ctx_t:
            island.after(0, lambda: island.set_state("thinking"))
            r = agent.open_target(ctx_t) if ctx_i == "open" else agent.kill_process(ctx_t)
            context.record(ctx_i, ctx_t, r)
            chat_engine.set_last_action(f"{ctx_i} {ctx_t}")
            island.after(0, lambda x=r: island.set_state("success", x))
            play_success()
            speak(r)
            return

        # 2. Full rescan
        if any(p in command for p in scan_phrases):
            island.after(0, lambda: island.set_state("info", "بفحص جهازك... ⏳"))
            agent.installed_apps = load_or_scan_installed_apps(
                APPS_CACHE_PATH, CURRENT_OS, force_rescan=True
            )
            agent.games = scan_all_games()
            try:
                from launcher_discovery import scan_all_other_launchers
                agent.games.update(scan_all_other_launchers())
            except Exception:
                pass
            known_targets.clear()
            known_targets.extend(
                list(CONFIG["websites"].keys())
                + list(agent.local_apps.keys())
                + list(agent.installed_apps.keys())
                + list(agent.games.keys())
            )
            threading.Thread(target=_train_local, name="local-brain", daemon=True).start()   # the new apps too
            scan_msg = f"فحصت جهازك! لقيت {len(agent.games)} لعبة و {len(agent.installed_apps)} برنامج ✅"
            island.after(0, lambda m=scan_msg: island.set_state("success", m))
            play_success()
            speak(scan_msg)
            return

        # 3. Suggestions
        if is_suggestion_request(command):
            island.after(0, lambda: island.set_state("thinking", "بفكرلك في فكرة... 💡"))
            sug_msg = suggestions.get_interactive_suggestion(
                command,
                games_list=list(agent.games.keys()),
                apps_list=list(agent.installed_apps.keys()),
            )
            island.after(0, lambda m=sug_msg: island.set_state("info", m))
            play_success()
            speak(sug_msg)
            return

        # 3.9 The island's own pages and the prayer times (before media: "مواقيت الصلاة" isn't a search)
        island_cmd = match_island_command(command, island)
        if island_cmd:
            kind, value = island_cmd
            if kind == "page":
                msg = island_open_page(island, value)
                end_conversation["now"] = True
                speak(msg)
            else:
                island.after(0, lambda m=value: island.set_state("success", m))
                play_success()
                speak(value)
            return

        # 4. Media
        media_handled, media_msg = handle_media_or_search(command, agent)
        if media_handled:
            island.after(0, lambda m=media_msg: island.set_state("success", m))
            play_success()
            speak(media_msg)
            context.record("media", command, media_msg)
            chat_engine.set_last_action(media_msg)
            suggestions.record_usage(command)
            return

        # 5. Learn task
        if any(p in command for p in learn_task_phrases):
            if _needs_key():
                return
            island.after(0, lambda: island.set_state("info", "قول اسم المهمة"))
            with mic as source:
                name_audio = recognizer.listen(source, timeout=6, phrase_time_limit=5)
            task_name_spoken = transcribe_groq(name_audio, prompt_text="اسم مهمة")
            if not task_name_spoken:
                island.after(0, lambda: island.set_state("error", "معرفتش أسمع الاسم"))
                return
            task_key = task_name_spoken.lower().strip()
            island.after(0, lambda: island.set_state("info", "بسجل... دوس F9 لما تخلص"))
            frames = record_demo(
                stop_hotkey="f9", interval=2.0, max_frames=20,
                on_frame=lambda n: print_ar(f"📸 التقطت {n} صورة..."),
            )
            if not frames:
                island.after(0, lambda: island.set_state("error", "معرفتش أسجل حاجة"))
                return
            island.after(0, lambda: island.set_state("thinking", "بحلل اللي شفته..."))
            description = describe_demo(groq_client, frames)
            TASKS[task_key] = {"description": description}
            save_tasks(TASKS)
            island.after(0, lambda d=description: island.set_state("success", f"اتعلمت: {d[:60]}"))
            return

        # 6. Forget last learned
        if any(p in command for p in forget_phrases):
            # still waiting to be learned (the guard's delay): cancel it; else forget the last thing learned
            forgot = guard.veto_latest("قلت انسى ده")
            if not forgot and LAST_LEARNED_KEY:
                _forget_learning(LAST_LEARNED_KEY)        # both the learner and LEARNED_COMMANDS
                LAST_LEARNED_KEY = None
                forgot = True
            if forgot:
                island.after(0, lambda: island.set_state("success", "تم النسيان 🗑️"))
                play_success()
                speak("تم النسيان")
            else:
                island.after(0, lambda: island.set_state("error", "مفيش حاجة أنساها"))
            return

        # 7. Scheduled tasks / reminders
        if scheduler.has_scheduled_intent(command):
            ok, msg = scheduler.parse_and_schedule(command)
            if ok:
                island.after(0, lambda m=msg: island.set_state("success", m))
                return

        # 8. Save login credentials
        if any(p in command for p in save_login_phrases):
            launcher_key = launcher_for_game(command)
            account_key = resolve_account_key(launcher_key, command) if launcher_key else None
            if not account_key:
                for k in ("riot", "steam", "epic"):
                    if k in command:
                        account_key = k
                        break
            if not account_key:
                account_key = "riot"

            display = label_for_account_key(account_key)
            island.after(0, lambda l=display: island.set_state(
                "info", f"اكتب بيانات {l} في النافذة"))

            result_holder = [None]
            ev = threading.Event()

            def _show_and_wait():
                result_holder[0] = show_login_dialog(launcher_name=display)
                ev.set()

            island.after(0, _show_and_wait)
            ev.wait()

            result = result_holder[0]
            if not result:
                island.after(0, lambda: island.set_state("info", "تمام، اتلغى"))
                return

            username, password = result
            ok = save_credentials(account_key, username, password)
            if ok:
                island.after(0, lambda l=display: island.set_state(
                    "success", f"حفظت بيانات {l} ✅"))
                speak(f"حفظت بيانات {display}")
            else:
                island.after(0, lambda: island.set_state(
                    "error", "معرفتش أحفظ البيانات"))
            return

        # 9. Forget login credentials
        if any(p in command for p in forget_login_phrases):
            deleted = []
            if "لول" in command or "league" in command:
                delete_credentials("riot:league")
                deleted.append("League of Legends")
            if "فالو" in command or "valorant" in command:
                delete_credentials("riot:valorant")
                deleted.append("Valorant")
            if "لور" in command:
                delete_credentials("riot:lor")
                deleted.append("Legends of Runeterra")
            for k in ("riot", "steam", "epic"):
                if k in command:
                    delete_credentials(k)
                    if k not in deleted:
                        deleted.append(k)
            if not deleted:
                for k in ("riot", "riot:league", "riot:valorant", "riot:lor",
                          "steam", "epic"):
                    delete_credentials(k)
                deleted = ["كل البيانات المحفوظة"]
            msg = f"مسحت بيانات: {', '.join(deleted)}"
            island.after(0, lambda m=msg: island.set_state("success", m))
            speak(msg)
            return

        # 10. File & folder operations
        file_match = match_file_command(command)
        if file_match:
            action_fn, description, needs_confirm = file_match
            if needs_confirm and not _ask_confirm(description):
                return
            r = action_fn()
            island.after(0, lambda x=r: island.set_state("success", x))
            play_success()
            speak(r)
            return

        # 10.5 Device control
        dev_match = match_device_command(command)
        if dev_match:
            action_fn, description, needs_confirm = dev_match
            if needs_confirm and not _ask_confirm(description):
                return
            island.after(0, lambda: island.set_state("thinking", "بشتغل على ده..."))
            try:
                r = action_fn()
            except Exception as e:
                r = f"فشل: {e}"
            island.after(0, lambda x=r: island.set_state("success", x))
            play_success()
            speak(r)
            return

        # 11. System commands
        sys_match = match_system_command(command)
        if sys_match:
            action_fn, description, needs_confirm = sys_match
            if needs_confirm and not _ask_confirm(description):
                return
            r = action_fn()
            island.after(0, lambda x=r: island.set_state("success", x))
            play_success()
            speak(r)
            return

        # 12. Vision tasks
        mt = find_matching_task(command, TASKS)
        if mt:
            if _needs_key():
                return
            goal = TASKS[mt]["description"]
            island.after(0, lambda t=mt: island.set_state("thinking", f"بنفذ: {t}"))
            ok, reason = run_task_live(
                groq_client, goal, max_steps=15, on_step=lambda m: print_ar(m)
            )
            status = "تمت المهمة ✅" if ok else f"توقفت: {reason}"
            island.after(0, lambda s=status, o=ok: island.set_state("success" if o else "error", s))
            return

        # 13. Screen description
        screen_phrases = [
            "الشاشة", "الشاشه", "على الشاشه", "على الشاشة",
            "الايرور", "الإيرور", "الخطأ", "المشكلة", "المشكله",
            "شايف ايه", "شايف إيه", "بتشوف ايه", "بتشوف إيه",
            "what's on screen", "what is on screen", "screen",
            "describe screen", "read screen", "اقرا الشاشة",
        ]
        if is_question(command) and any(p in command.lower() for p in screen_phrases):
            if _needs_key():
                return
            island.after(0, lambda: island.set_state("thinking", "بشوف الشاشة... 👁️"))
            desc = describe_screen(groq_client)
            island.after(0, lambda d=desc: island.set_state("info", d))
            speak(desc)
            return

        # 14. Router v7 — Fast Path via Catalog Resolver & Learned Commands (<30ms, zero LLM)
        has_question_word = is_question(command)
        cmd_intent = detect_intent(command)
        has_cmd_intent = cmd_intent is not None
        cmd_l = command.lower().strip()

        if has_question_word:
            sa = try_system_answer(command)
            if sa:
                island.after(0, lambda a=sa: island.set_state("info", a))
                speak(sa)
                return

        # 14.1 — Direct Catalog Resolver Fast Path (~20ms on CPU, no LLM needed!)
        if has_cmd_intent and not has_question_word:
            res_cat = agent.resolve(command, utterance=command, stt_low=stt_state["low"])
            if res_cat.status == "ok" and res_cat.best is not None:
                best_disp = res_cat.best.display
                print_ar(f"⚡ مسار سريع (Resolver): {cmd_intent} → {best_disp} ({res_cat.score:.2f})")
                if cmd_intent == "close":
                    r = agent.kill_process(best_disp)
                    guard.on_close(best_disp)
                    context.record("close", best_disp, r)
                    chat_engine.set_last_action(r)
                    island.after(0, lambda r2=r: island.set_state("success", r2))
                    play_success()
                    speak(r)
                    return
                elif cmd_intent == "open":
                    r = smart_open(agent, best_disp, utterance=command,
                                   stt_low=stt_state["low"], choose=_ask_choice,
                                   guard=guard, learn_phrase=command)
                    if r.startswith("CANCELLED"):
                        island.after(0, lambda: island.say(
                            "تمام، مش هفتح حاجة. قولي تقصد إيه 👂", state="info", chime=False))
                        return
                    if not r.startswith(("NOT_FOUND", "ASK", "SEARCHED")):
                        _on_tool_opened(best_disp, r)
                        island.after(0, lambda r2=r: island.set_state("success", r2))
                        play_success()
                        speak(r)
                        return

        fast_target = _match_known_target_in_text(cmd_l, known_targets) if (has_cmd_intent and not has_question_word) else None
        known_phrase = cmd_l in LEARNED_COMMANDS

        # 14.5 — v7.2: موديل الأوامر
        if (intent_model is not None and not has_question_word and not fast_target
                and not known_phrase):
            try:
                pred = intent_model.predict(command)
            except Exception as e:
                pred = None
                print_ar(f"⚠️ موديل الأوامر: {e}")
            if pred is not None and pred.intent == "open":
                print_ar(f"⚡ موديل الأوامر: {pred}")
                res = smart_open(agent, pred.target, utterance=None,
                                 stt_low=stt_state["low"], choose=_ask_choice,
                                 guard=guard, learn_phrase=command)
                if res.startswith("CANCELLED"):
                    island.after(0, lambda: island.say(
                        "تمام، مش هفتح حاجة. قولي تقصد إيه 👂", state="info", chime=False))
                    return
                if not res.startswith(("NOT_FOUND", "ASK", "SEARCHED")):
                    _on_tool_opened(pred.target, res)
                    island.after(0, lambda r2=res: island.set_state("success", r2))
                    play_success()
                    speak(res)
                    return
            elif pred is not None and pred.intent == "close":
                print_ar(f"⚡ موديل الأوامر (قفل): {pred}")
                r = agent.kill_process(pred.target)
                guard.on_close(pred.target)
                context.record("close", pred.target, r)
                chat_engine.set_last_action(r)
                island.after(0, lambda r2=r: island.set_state("success", r2))
                play_success()
                speak(r)
                return

        if not fast_target and not known_phrase:
            actions = _do_chat(command)
            missed = [a for a in actions if a[0] == "open_app" and str(a[2]).startswith("NOT_FOUND")]
            if missed and cmd_audio is not None:
                command_en = transcribe_groq(cmd_audio, lang="en",
                                             prompt_text="Apps and games: " + ", ".join(
                                                 [str(t) for t in known_targets if isinstance(t, str)][:30]))
                en_target = re.sub(r"\b(open|close|start|launch|run)\b", "", command_en or "").strip(" .")
                if en_target:
                    res_en = smart_open(agent, en_target, utterance=None,
                                        stt_low=True, choose=_ask_choice, guard=guard,
                                        learn_phrase=command)
                    if not res_en.startswith(("NOT_FOUND", "CANCELLED", "ASK", "SEARCHED")):
                        _on_tool_opened(en_target, res_en)
                        island.after(0, lambda r2=res_en: island.set_state("success", r2))
                        speak("لقيتها، " + res_en)
            return

        # 15. Command execution
        island.after(0, lambda: island.set_state("thinking"))
        intent, target = parse_command(command, known_targets)

        if not intent and not target:
            _do_chat(command)
            return

        target_used = target
        learned = parse_command_source(command) == "learned"
        if intent == "close" and target:
            res = agent.kill_process(target)
            guard.on_close(target)
        else:
            if intent != "open" or not target:
                target_used = command.replace("افتح", "").replace("شغل", "").strip()
            if target_used:
                res = smart_open(agent, target_used,
                                 utterance=None if learned else command,
                                 stt_low=stt_state["low"] and not learned,
                                 choose=_ask_choice, guard=guard, learn_phrase=command)
                if res.startswith("CANCELLED"):
                    island.after(0, lambda: island.say(
                        "تمام، مش هفتح حاجة. قولي تقصد إيه 👂", state="info", chime=False))
                    return
                if res.startswith("SEARCHED"):
                    island.after(0, lambda: island.set_state("info", "مش متأكد من الموقع، بحثتلك عنه 🔎"))
                    speak("مش متأكد من الموقع، بحثتلك عنه")
                    return
                if res.startswith(("NOT_FOUND", "ASK")):
                    res = "مش لاقي البرنامج ده"
            else:
                res = "مش لاقي حاجة أفتحها"

        if not _is_not_found(res):
            context.record(intent or "open", target_used or command, res)
            chat_engine.set_last_action(res)
            island.after(0, lambda r2=res: island.set_state("success", r2))
            play_success()
            speak(res)

            if intent in ("open", None) and target_used:
                _maybe_auto_login(target_used)
            return

        # 16. English fallback
        island.after(0, lambda: island.set_state("info", "بجرب أسمعها إنجليزي... 🔁"))
        ah = ", ".join([str(t) for t in known_targets if isinstance(t, str)][:15])
        ht = (
            "Arabic and English commands. Games: Rocket League, Minecraft, "
            "Fortnite, Valorant, League of Legends, Counter-Strike, GTA V, "
            "Apex Legends, Overwatch. Apps: Spotify, Discord, Chrome, Steam. "
            + ah
        )
        command_en = transcribe_groq(cmd_audio, prompt_text=ht, lang="en")
        if command_en:
            en_target = command_en.replace("open", "").replace("close", "").strip()
            if en_target:
                res_en = smart_open(agent, en_target, utterance=None, stt_low=True,
                                    choose=_ask_choice, guard=guard, learn_phrase=command)
                if not res_en.startswith(("NOT_FOUND", "CANCELLED", "ASK", "SEARCHED")):
                    context.record("open", en_target, res_en)
                    chat_engine.set_last_action(res_en)
                    island.after(0, lambda r2=res_en: island.set_state("success", r2))
                    return

        # 17. Nothing worked — record failure for learning
        learner.record_failure(command)
        print_ar(f"❓ مفهمتش الأمر: '{command}'")

        if learner.needs_correction(command):
            island.after(0, lambda: island.set_state(
                "info", "مش فاهم الجملة دي — قوللي أقصد إيه؟ "
                        "(مثال: 'لأ، أقصد spotify')"
            ))
            speak("مش فاهم الجملة دي — قوللي أقصد إيه")
        else:
            island.after(0, lambda: island.set_state(
                "error", "معلش مفهمتش — جرب تقولها بطريقة تانية"
            ))
            play_error()
            speak("معلش مفهمتش")

    print_ar("\n[ Yobi is sleeping 💤. Say 'يا يوبي' to summon the Island! ]")

    def _strip_wake(text):
        t = _WAKE_RE.sub(" ", text) if _WAKE_RE else text
        return re.sub(r"^(?:[\s،,.!؟?]|يا(?=\s|$))+", "", t).strip(" ،,.!؟?")

    apps_hint = ", ".join([str(t) for t in known_targets if isinstance(t, str)][:20])
    hint_text = (
        "أوامر عربي/إنجليزي: افتح، اقفل، علي/وطي الصوت، "
        "اكتم الصوت، شغل فيلم/اغنية، ابحث عن، دور على، "
        "افتح موقع، اقترح لعبة/برنامج، افحص جهازي، فكرني، "
        "افتح فولدر التحميلات/المستندات/الديسكتوب، "
        "احفظ بيانات الدخول، افحص كل حاجة، فين موقع، "
        "ايه اللي شغال، برامج البدء، علم نفسك إن، اتعلم، "
        "امسح التعلم. " + apps_hint
    )

    _BASE_HINT = ("أوامر عربي/إنجليزي: افتح، اقفل، علي/وطي الصوت، شغل، "
                  "ابحث عن، اقترح، افحص جهازي، فكرني، علم نفسك إن.")

    def _hint():
        if vocab is not None:
            return vocab.prompt(base=_BASE_HINT)
        return hint_text

    def _process(command, cmd_audio, trusted=False):
        nonlocal chat_mode_active
        print_ar(f"🗣️ (قبل التصحيح): '{command}'")
        command = normalize_transcription(command, known_targets)
        print_ar(f"🗣️ (بعد التصحيح): '{command}'")

        if any(p in command for p in exit_phrases) and len(command.split()) <= 3:
            island.after(0, lambda: island.set_state("success", "تمام يا معلم! 👋"))
            play_hide()
            speak("تمام يا معلم")
            if chat_mode_active:
                brain.clear()
                chat_engine.clear()
            if yobi_latency is not None:
                yobi_latency.tracker.end_turn()
            return False

        for sub_cmd in split_compound_command(command):
            handle_command(sub_cmd.strip(), cmd_audio, trusted=trusted)
        if yobi_latency is not None:
            yobi_latency.tracker.end_turn()
        if end_conversation["now"]:
            end_conversation["now"] = False
            return False
        return True

    def _conversation(first_command=None, first_audio=None, by_key=False):
        """by_key: woken by the wake key, so Yobi records until the key is pressed again."""
        nonlocal chat_mode_active
        if time.time() - key_chime[0] > 2:      # the wake key already chimed
            play_wake()
        turn_gen[0] += 1
        context.in_conversation = True
        island.after(0, lambda: island.set_state("listening", KEY_HINT if by_key else ""))
        addressed.reset()
        chat_mode_active = False
        conv_round = 0

        if first_command:
            conv_round = 1
            if not _process(first_command, first_audio, trusted=not stt_state["low"]):
                context.in_conversation = False
                if wake_detector is not None:
                    wake_detector.reset()
                return

        retried_empty = False
        while listening_enabled.is_set():
            try:
                conv_round += 1
                if conv_round > 1:
                    island.after(0, lambda: island.show_listening_soft("سامعك... كمّل 🎤"))

                if by_key:
                    by_key = False
                    island.after(0, lambda: island.set_state("listening", KEY_HINT))
                    cmd_audio = recognizer.listen_until_key()
                    island.after(0, lambda: island.set_state("thinking"))
                else:
                    try:
                        with mic as source:
                            listen_timeout = 30 if chat_mode_active else 7
                            cmd_audio = recognizer.listen(
                                source, timeout=listen_timeout,
                                phrase_time_limit=15 if chat_mode_active else 8,
                                hotkey_wakes=True,
                            )
                    except HotkeyPressed:       # the key (or the Talk button) in the middle of a conversation
                        by_key = recognizer.take_key_press()
                        conv_round -= 1
                        if not by_key:
                            island.after(0, lambda: island.set_state("listening", "سامعك.. اتكلم 🎤"))
                        continue

                command = transcribe_groq(cmd_audio, prompt_text=_hint())
                stt_state["low"] = bool(_STT is not None and _STT.last_low)
                if not command:
                    if conv_round == 1 and not retried_empty:
                        retried_empty = True
                        conv_round = 0
                        island.after(0, lambda: island.set_state("listening", "سامعك.. اتكلم 🎤"))
                        continue
                    break
                if _has_wake(command):
                    command = _strip_wake(command)
                    if not command or len(command) < 2:
                        conv_round = 0
                        island.after(0, lambda: island.set_state("listening", "سامعك.. قولي أمرك 🎤"))
                        continue
                _record_heard(cmd_audio, command)

                if addressed.should_exit_conversation():
                    print_ar("🤫 كلام جانبي كتير — بقفل المحادثة.")
                    island.after(0, lambda: island.set_state(
                        "info", "مش سامع حد بيكلمني — تصبح على خير 👋"))
                    play_hide()
                    break

                is_trusted = (conv_round == 1 and not stt_state["low"])
                if not _process(command, cmd_audio, trusted=is_trusted):
                    break

            except sr.WaitTimeoutError:
                if chat_mode_active:
                    print_ar("💬 خلصت المحادثة — يوبي رجع للنوم.")
                break

        context.in_conversation = False
        if wake_detector is not None:
            wake_detector.reset()
        play_hide()

        gen = turn_gen[0]

        def _hide_when_quiet():
            if _reply_cfg().get("voice"):
                get_tts_engine().wait_until_done(60)
            # the wake key cuts Yobi's voice short: by now he may be listening again
            island.after(0, lambda: turn_gen[0] == gen and island.end_turn())

        threading.Thread(target=_hide_when_quiet, daemon=True).start()

    print_ar("\n[ Yobi is sleeping 💤. Say 'يا يوبي' (or press the hotkey) ]")

    while True:
        try:
            if not listening_enabled.is_set():
                time.sleep(0.2)
                continue

            key_only = _wake_by_key() and hasattr(recognizer, "wait_for_key")
            if wake_detector is not None and wake_detector._paused != key_only:
                wake_detector.pause(key_only)
                print_ar("⌨️ النداء بالزرار بس — مفيش موديل بيسمع" if key_only else "👂 النداء بالصوت رجع")
            if key_only:
                if recognizer.wait_for_key(timeout=1.0):
                    print_ar("⌨️ اتنده بالكيبورد")
                    _conversation(by_key=recognizer.take_key_press())
                continue

            if recognizer.has_wake_model:
                try:
                    woke = recognizer.wait_for_wake(hotkey_wakes=True, timeout=1.0)
                except HotkeyPressed:
                    print_ar("⌨️ اتنده بالكيبورد")
                    _conversation(by_key=recognizer.take_key_press())
                    continue
                if woke:
                    print_ar(f"👂 سمعت النداء (offline, {recognizer.wake.last_score:.2f})")
                    _conversation()
                    continue
                # Hybrid fallback: if the user spoke a short phrase (e.g. "يوبي" without "يا")
                # that didn't trigger the ONNX model, check it with Whisper/Groq
                cand_audio = recognizer.pop_wake_candidate() if hasattr(recognizer, "pop_wake_candidate") else None
                if cand_audio is None:
                    continue
                audio = cand_audio
            else:
                try:
                    with mic as source:
                        audio = recognizer.listen(source, timeout=None,
                                                  phrase_time_limit=8, hotkey_wakes=True)
                except HotkeyPressed:
                    print_ar("⌨️ اتنده بالكيبورد")
                    _conversation(by_key=recognizer.take_key_press())
                    continue

            # no prompt: with «يا يوبي» as a prompt Whisper small writes it for noise and any short phrase
            wake_text = transcribe_local(audio, "ar", wake_model)
            # the second opinion is the hearing engine; a local one trained on wake calls hears them in noise
            if not _has_wake(wake_text) and H["stt_engine"] != "local":
                # Quick Groq Turbo check in case local small/base model misheard "يوبي"
                wake_text_g = transcribe_groq(audio, prompt_text="يا يوبي، يوبي، افتح، شغل")
                if wake_text_g:
                    wake_text = wake_text_g
            if wake_text:
                print_ar(f"👂 سمعت: '{wake_text}'")

            if not _has_wake(wake_text):
                continue

            rest_local = _strip_wake(wake_text)
            first_command = None
            if len(rest_local.split()) >= 1 and len(rest_local) >= 3:
                full = transcribe_groq(audio, prompt_text="يا يوبي، " + _hint())
                stt_state["low"] = bool(_STT is not None and _STT.last_low) if full else True
                first_command = _strip_wake(full) if full else rest_local
                if len(first_command) < 2:
                    first_command = None
                else:
                    _record_heard(audio, first_command)

            if first_command is None and hasattr(recognizer, "keep_what_follows"):
                recognizer.keep_what_follows()      # "يا يوبي" ... a breath ... the command
            _conversation(first_command, audio if first_command else None)

        except sr.WaitTimeoutError:
            island.after(0, lambda: island.set_state("hide"))
        except Exception as e:
            print_ar(f"⚠️ خطأ غير متوقع في اللوب: {e}")
            traceback.print_exc()
            island.after(0, lambda: island.set_state("hide"))


if __name__ == "__main__":
    app_agent = DesktopAgent(CONFIG, INSTALLED_APPS, GAMES)
    app_agent.client = groq_client
    app_known_targets = (
        list(CONFIG["websites"].keys())
        + list(app_agent.local_apps.keys())
        + list(app_agent.installed_apps.keys())
        + list(app_agent.games.keys())
    )

    island_ui = None
    # config.json → "ui": {"engine": "tk"} runs the old tkinter island; anything else the Tauri one
    # ("electron" from older configs means Tauri now: the Electron island was removed)
    if (CONFIG.get("ui") or {}).get("engine", "tauri") != "tk":
        try:
            from electron_island import ElectronIsland
            island_ui = ElectronIsland(log=print_ar)
            print_ar("🏝️ الواجهة الجديدة شغالة")
        except Exception as e:
            print_ar(f"⚠️ الواجهة الجديدة مش شغالة ({e}) — هرجع للقديمة")
    if island_ui is None:
        island_ui = DynamicIsland()
    island_ui._agent = app_agent
    _REPLY_ISLAND = island_ui
    tts = get_tts_engine()

    # Reuse shared AudioEngine level for island waveform (avoids opening a 2nd mic stream)
    if hasattr(island_ui, "_mic") and get_audio_engine is not None:
        _orig_mic_start = island_ui._mic.start
        _orig_mic_level = island_ui._mic.level

        def _shared_mic_start():
            eng = get_audio_engine()
            if eng is None:
                _orig_mic_start()

        def _shared_mic_level():
            eng = get_audio_engine()
            if eng is not None:
                return min(1.0, float(eng.level) * 1.8)
            return _orig_mic_level()

        island_ui._mic.start = _shared_mic_start
        island_ui._mic.level = _shared_mic_level

    listening_enabled = threading.Event()
    listening_enabled.set()
    app_agent.listening_enabled = listening_enabled

    def _tray_toggle_listen():
        if listening_enabled.is_set():
            listening_enabled.clear()
            island_ui.after(0, lambda: island_ui.set_state("info", "الاستماع مقفول 🔇"))
            return False
        else:
            listening_enabled.set()
            island_ui.after(0, lambda: island_ui.set_state("info", "الاستماع شغال 🎤"))
            return True

    def _tray_toggle_tts():
        rc = CONFIG.setdefault("replies", {})
        new_state = not bool(rc.get("voice", False))
        rc["voice"] = new_state
        if new_state and not tts.is_enabled:
            tts.set_enabled(True)
        msg = "الرد الصوتي شغال 🔊" if new_state else "الرد بالكتابة بس ✍️"
        island_ui.after(0, lambda m=msg: island_ui.say(m, state="info"))
        return new_state

    def _tray_refresh():
        island_ui.after(0, lambda: island_ui.set_state("info", "بحدث البرامج... ⏳"))
        app_agent.installed_apps = load_or_scan_installed_apps(
            APPS_CACHE_PATH, CURRENT_OS, force_rescan=True
        )
        app_agent.games = scan_all_games()
        try:
            from launcher_discovery import scan_all_other_launchers
            app_agent.games.update(scan_all_other_launchers())
        except Exception:
            pass
        app_known_targets.clear()
        app_known_targets.extend(
            list(CONFIG["websites"].keys())
            + list(app_agent.local_apps.keys())
            + list(app_agent.installed_apps.keys())
            + list(app_agent.games.keys())
        )
        island_ui.after(0, lambda: island_ui.set_state("success", "تم التحديث ✅"))

    app_agent.toggle_listen = _tray_toggle_listen
    app_agent.toggle_voice_reply = _tray_toggle_tts
    app_agent.get_voice_reply = lambda: bool(CONFIG.get("replies", {}).get("voice", False))
    app_agent.refresh_apps = _tray_refresh

    def _tray_quit():
        try:
            if yobi_latency is not None and yobi_latency.tracker.stats():
                print_ar(yobi_latency.tracker.format_summary())
        except Exception:
            pass
        island_ui.after(0, lambda: island_ui.set_state("info", "بقفل يوبي... 👋"))
        try:
            stop_speaking()
        except Exception:
            pass
        os._exit(0)

    tray = YobiTray(
        on_toggle_listen=_tray_toggle_listen,
        on_toggle_tts=_tray_toggle_tts,
        on_refresh_apps=_tray_refresh,
        on_quit=_tray_quit,
    )
    tray.start()
    print_ar("🖥️ أيقونة يوبي ظهرت في شريط المهام.")

    # ── Game Companion ─────────────────────────────────────────
    game_companion = None
    if _HAS_GAME_COMPANION:
        try:
            def _companion_notify(msg):
                island_ui.after(0, lambda m=msg: island_ui.set_state("info", m))
                speak(msg)

            def _companion_overlay(perf_data):
                overlay = island_ui.get_overlay()
                if overlay:
                    overlay.show_perf_hud(**perf_data)

            game_companion = GameCompanion(
                on_notify=_companion_notify,
                on_overlay_update=_companion_overlay,
                llm_client=app_agent.client if hasattr(app_agent, "client") else None,
            )
            game_companion.start()
            _GAME_COMPANION = game_companion
            print_ar("🎮 Game Companion شغال.")
        except Exception as e:
            print_ar(f"⚠️ Game Companion فشل: {e}")

    # ── Chat Window Handler ────────────────────────────────────
    if _HAS_CHAT_WINDOW:
        def _chat_handler(text):
            try:
                if _COMPANION is not None:
                    rep_ = _COMPANION.handle_text(text)
                    if rep_:
                        return rep_

                if game_companion and _HAS_GAME_COMPANION:
                    game_resp = handle_game_query(text, game_companion)
                    if game_resp:
                        return game_resp

                if hasattr(app_agent, "chat_engine") and app_agent.chat_engine:
                    response = app_agent.chat_engine.ask(text)
                    return response
                return f"استلمت: {text}"
            except Exception as e:
                return f"❌ حصل خطأ: {e}"

        island_ui.set_chat_handler(_chat_handler)

    # ── Quick Action Handler ───────────────────────────────────
    def _quick_action_handler(action_id):
        if action_id == "listen":
            if getattr(app_agent, "recognizer", None) is not None:
                app_agent.recognizer.hotkey_event.set()
            else:
                island_ui.set_state("listening", "سامعك.. اتكلم 🎤")
        elif action_id == "games":
            if game_companion and game_companion.get_current_game():
                game = game_companion.get_current_game()
                session = game_companion.get_session_time()
                island_ui.set_state("info", f"🎮 بتلعب {game} من {session}")
            else:
                island_ui.set_state("info", "🎮 مفيش لعبة شغالة دلوقتي")
        elif action_id == "music":
            island_ui.set_state("info", "🎵 قول 'شغل مزيكا' أو 'افتح سبوتيفاي'")

    island_ui.set_quick_action_callback(_quick_action_handler)

    # ── Health Check Log ───────────────────────────────────────
    if _HAS_RETRY:
        if is_online():
            print_ar("🌐 متصل بالإنترنت ✅")
        else:
            print_ar("⚠️ مفيش اتصال — يوبي هيشتغل offline")

    # ── Session Summary on Exit ────────────────────────────────
    def _tray_quit_enhanced():
        try:
            if hasattr(app_agent, "context") and hasattr(app_agent.context, "save_session_summary"):
                app_agent.context.save_session_summary()
        except Exception:
            pass
        if game_companion:
            try:
                game_companion.stop()
            except Exception:
                pass
        _tray_quit()

    island_ui.bind("<<YobiQuit>>", lambda e: _tray_quit_enhanced())

    if _HAS_LOGGER:
        yobi_log.info("🚀 يوبي v2.0 جاهز — كل الموديولات الجديدة شغالة")

    try:
        import updater          # an installed Yobi offers a newer GitHub release once in a while
        threading.Thread(target=updater.watch, args=(island_ui, print_ar), name="updater", daemon=True).start()
    except Exception as e:
        print_ar(f"⚠️ التحديثات: {e}")

    threading.Thread(
        target=voice_loop,
        args=(island_ui, app_agent, app_known_targets, listening_enabled),
        daemon=True,
    ).start()
    island_ui.mainloop()