# -*- coding: utf-8 -*-
"""
Brain — عقل يوبي الجديد (Gemini Flash + Tool Calling + Streaming + Fast Confirmation).

Replaces the "[CMD:verb:target]" marker trick in chat_engine.py with real
function calling, streams replies after the first sentence, and skips the
second LLM round-trip when action tools return a ready Arabic confirmation
(saving ~1.5s per tool turn).
"""

import json
import re
import threading
import time

from chat_memory import ChatMemory

_SYSTEM_PROMPT = """أنت يوبي — مساعد صوتي ذكي على كمبيوتر المستخدم، بتتكلم معاه بالعامية المصرية الطبيعية.

شخصيتك:
• صاحب ذكي وودود، مش روبوت ومش خدمة عملاء. عندك آراء وبتتفاعل.
• اتكلم بنفس لغة اللي قدامك: مصري عامي سليم (قول "مش فاهم" وماتقولش أبداً "مفيش فاهم")، أو إنجليزي لو هو بيتكلم إنجليزي.
• متبدأش بـ "بالطبع" أو "سؤال ممتاز". متقولش إنك AI. متقولش اسمك "يوبي" في الرد.
• لو مش متأكد قول "مش متأكد" أو اسأل، متألفش.

الرد بيتنطق بصوت أو بيتكتب على الجزيرة:
• جملة أو اتنين في العادي. مفيش markdown ولا نجوم ولا لينكات ولا قوايم.
• لو عملت حاجة، أكد في كلمتين ("تمام، فتحت سبوتيفاي") من غير شرح.

الأدوات:
• استخدم الأدوات عشان تنفذ أي حاجة على الجهاز. متقولش إنك عملت حاجة من غير ما تنادي الأداة.
• تقدر تنادي أكتر من أداة في نفس الرد لو الطلب مركب ("علي الصوت وافتح ديسكورد").
• أسماء البرامج والألعاب ابعتها بالإنجليزي لو تعرفها (فالو → valorant، لول → league of legends، يورو → euro truck simulator 2، اسيتو → assetto corsa competizione، كروم → chrome).
• الكلام جاي من مايك وممكن يكون متلخبط. لو مش فاهم المستخدم عايز يفتح إيه، اسأله بدل ما تخمن. متفتحش حاجة من سياق الكلام اللي فات إلا لو قال "افتحها تاني" أو حاجة زي كده.
• open_app: ابعت الاسم زي ما هو مكتوب في قايمة البرامج اللي في السياق. متألفش مواقع.
• system_control: لو المستخدم حدد نسبة مئوية للصوت أو السطوع (مثلاً 50% أو للنص)، استخدم set_volume أو set_brightness وابعت level بالرقم، ولو طلب تنظيف الرامات استخدم free_ram.
• activate_mode: لو طلب مود المذاكرة/الكودينج ('study')، أو الجيمينج ('gaming')، أو السينما/الروقان ('cinema').
• لو الأداة رجعت NOT_FOUND، قول إنك مش لاقيه واقترح اسم قريب من قايمة البرامج لو فيه.
• لو رجعت ASK، اسأل المستخدم السؤال ده بالظبط ومتقولش إنك فتحت حاجة.
• لو رجعت SEARCHED، قول إنك مش متأكد من الموقع فبحثتله عنه.
• لو رجعت CANCELLED، قول "تمام" واسأله يقصد إيه، من غير ما تنادي أي أداة تاني.
• أسئلة المعرفة العامة جاوبها من دماغك من غير أدوات.
• أسئلة عن الجهاز نفسه (الرام، البطارية، كارت الشاشة، الوقت، المساحة، وقت التشغيل) استخدم system_info."""

_DIRECT_ACTION_TOOLS = {
    "open_app", "close_app", "system_control", "activate_mode",
    "play_media", "web_search", "set_reminder", "schedule_command", "pc_command",
}

NEEDS_KEY = "ده محتاج مفتاح Gemini المجاني. ضيفه من قايمة ابدأ ← Yobi - API keys"
NOT_READY = "ثانية واحدة، لسه بجهّز نفسي. قولها تاني كمان شوية"


def _plain(result):
    """A tool's result as something to say: "ASK: تقصد X؟" → "تقصد X؟", "CANCELLED: …" → "تمام، لغيت"."""
    r = str(result or "").strip()
    if r.startswith("CANCELLED"):
        return "تمام، لغيت"
    if r.startswith("UNKNOWN_COMMAND"):
        return "مش عارف أعمل ده"
    for pre in ("ASK:", "NOT_FOUND:", "SEARCHED:", "FAILED:"):
        if r.startswith(pre):
            return r[len(pre):].strip()
    return r


_NEEDS_LLM_PREFIXES = (
    "NOT_FOUND", "ASK:", "SEARCHED:", "CANCELLED:",
    "UNKNOWN_COMMAND", "FAILED", "arguments غلط", "فشل:", "tool ",
)


class Brain:
    def __init__(self, client, model="gemini-3.5-flash", tools=None, memory=None,
                 fallback_engine=None, temperature=0.6, max_tokens=500, max_tool_rounds=4, local=None):
        self._client = client
        # local_brain.LocalBrain (or a function returning it once it's trained): runs the
        # everyday commands with no key (client None) or when Gemini can't be reached
        self._local = local
        self._local_wait = 15          # seconds to wait for it when a command comes while it still trains
        self.model = model or "gemini-3.5-flash"
        self._tools = tools
        self._memory = memory or ChatMemory()
        self._fallback = fallback_engine
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_rounds = max_tool_rounds
        self._lock = threading.Lock()
        self._tools_supported = True
        self.last_actions = []

    # ── public ──────────────────────────────────────────────────

    def clear(self):
        self._memory.clear()

    def ask(self, text):
        """Text-only (chat window) — no speech."""
        return self.run(text)

    def run(self, user_text, on_sentence=None, extra_context="", known_targets=None,
            on_tool=None, stt_low=False):
        """Answer + act. Streams sentences to on_sentence as they arrive.
        Returns the full reply text."""
        if not user_text or not user_text.strip():
            return ""
        with self._lock:
            self.last_actions = []
            if hasattr(self._tools, "current_utterance"):
                self._tools.current_utterance = user_text
                self._tools.current_stt_low = bool(stt_low)
            if self._client is None:
                return self._run_local(user_text, on_sentence, NEEDS_KEY)
            if not self._tools_supported and self._fallback:
                return self._run_fallback(user_text, on_sentence, extra_context)
            try:
                return self._run_tools(user_text, on_sentence, extra_context,
                                       known_targets, on_tool)
            except _ToolsUnsupported:
                self._tools_supported = False
                print("⚠️ الموديل مش بيدعم tool calling — رجعت للعقل القديم")
                if self._fallback:
                    return self._run_fallback(user_text, on_sentence, extra_context)
                raise
            except Exception as e:
                print(f"⚠️ Brain error: {e}")
                if not self.last_actions:          # nothing ran yet: the local model can still do it
                    return self._run_local(user_text, on_sentence, "معلش، حصلت مشكلة في الاتصال")
                msg = "معلش، حصلت مشكلة في الاتصال"
                if on_sentence:
                    on_sentence(msg)
                return msg

    def _run_local(self, user_text, on_sentence, otherwise):
        """The local model picks the tool; the same YobiTools run it. `otherwise` is said when it
        isn't a command it knows (chat, questions) or it isn't sure."""
        lb = self._local() if callable(self._local) else self._local
        # None from the function = still training (the first seconds after start); False = it failed
        end = time.time() + self._local_wait
        while lb is None and callable(self._local) and time.time() < end:
            time.sleep(0.1)
            lb = self._local()
        if lb is None and callable(self._local) and self._client is None:
            otherwise = NOT_READY      # "needs a key" would be wrong for "علي الصوت"
        d = None
        if lb and self._tools is not None:
            try:
                d = lb.understand(user_text)
            except Exception as e:
                print(f"⚠️ local brain: {e}")
        if d is None:
            reply = otherwise
        else:
            print(f"⚡ الموديل المحلي: {d}")
            args = json.dumps(d.args, ensure_ascii=False)
            result = self._tools.execute(d.tool, args)
            self.last_actions.append((d.tool, args, result))
            reply = _plain(result) or "تمام"
        if on_sentence and reply:
            on_sentence(reply)
        return reply

    # ── internals ───────────────────────────────────────────────

    def _build_messages(self, user_text, extra_context, known_targets):
        system = _SYSTEM_PROMPT
        ctx = []
        if extra_context:
            ctx.append(extra_context)
        if known_targets:
            names = [str(t) for t in known_targets if isinstance(t, str) and not str(t).startswith("__")][:120]
            ctx.append("برامج وألعاب على الجهاز: " + ", ".join(names))
        if ctx:
            system += "\n\nسياق لحظي: " + " | ".join(ctx)
        msgs = [{"role": "system", "content": system}]
        msgs.extend(self._memory.get_messages())
        msgs.append({"role": "user", "content": user_text.strip()})
        return msgs

    def _create(self, messages, stream=True):
        kwargs = dict(
            model=self.model,
            messages=messages,
            tools=self._tools.schemas,
            tool_choice="auto",
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            stream=stream,
        )
        if str(self.model).startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = "low"
        try:
            return self._client.chat.completions.create(**kwargs)
        except Exception as e:
            err = str(e).lower()
            if "reasoning_effort" in err:
                kwargs.pop("reasoning_effort", None)
                return self._client.chat.completions.create(**kwargs)
            if "tool" in err and ("not supported" in err or "does not support" in err):
                raise _ToolsUnsupported() from e
            raise

    def _run_tools(self, user_text, on_sentence, extra_context, known_targets, on_tool):
        from tts_engine import SentenceStreamer

        messages = self._build_messages(user_text, extra_context, known_targets)
        spoken_parts = []

        def _emit(sentence):
            spoken_parts.append(sentence)
            if on_sentence:
                on_sentence(sentence)

        for _round in range(self._max_rounds + 1):
            streamer = SentenceStreamer(_emit)
            content, tool_calls = self._stream_once(messages, streamer)
            streamer.flush()

            if not tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": content or "",
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": tc["arguments"] or "{}"}}
                    for tc in tool_calls
                ],
            })
            round_results = []
            for tc in tool_calls:
                if on_tool:
                    on_tool(tc["name"], tc["arguments"])
                print(f"🛠️ {tc['name']}({tc['arguments']})")
                result = self._tools.execute(tc["name"], tc["arguments"])
                self.last_actions.append((tc["name"], tc["arguments"], result))
                round_results.append((tc["name"], str(result or "")))
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "name": tc["name"],
                                 "content": str(result or "")[:1500]})

            # Fast exit: if a tool returned "ASK: ...", emit the question directly
            ask_hits = [r[4:].strip() for _, r in round_results if r.startswith("ASK:")]
            if ask_hits and not spoken_parts:
                _emit(" ".join(ask_hits))
                break

            # Fast exit: if all called tools are direct actions and succeeded cleanly,
            # use their Arabic status message directly without a 2nd LLM round-trip (~1.5s saved)
            if (not spoken_parts
                    and all(name in _DIRECT_ACTION_TOOLS for name, _ in round_results)
                    and all(r and not r.startswith(_NEEDS_LLM_PREFIXES) for _, r in round_results)):
                _emit(" — ".join(r for _, r in round_results))
                break

        reply = " ".join(spoken_parts).strip()
        if not reply and self.last_actions:
            reply = self.last_actions[-1][2]
            if on_sentence and reply:
                on_sentence(reply)
        self._memory.add_user(user_text)
        if reply:
            self._memory.add_assistant(reply)
        return reply

    def _stream_once(self, messages, streamer):
        stream = self._create(messages, stream=True)
        content = ""
        calls = {}
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                content += text
                streamer.feed(text)
            for idx_fallback, tc in enumerate(getattr(delta, "tool_calls", None) or []):
                tc_idx = getattr(tc, "index", None)
                if tc_idx is None:
                    tc_idx = idx_fallback
                slot = calls.setdefault(tc_idx, {"id": None, "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        slot["arguments"] += fn.arguments
        tool_calls = []
        for i in sorted(calls):
            c = calls[i]
            if not c["name"]:
                continue
            c["id"] = c["id"] or f"call_{i}"
            tool_calls.append(c)
        return content, tool_calls

    def _run_fallback(self, user_text, on_sentence, extra_context):
        reply, action = self._fallback.chat(user_text, extra_context=extra_context)
        if action:
            verb, target = action["verb"], action["target"]
            mapping = {
                "open": ("open_app", {"name": target}),
                "close": ("close_app", {"name": target}),
                "search": ("web_search", {"query": target}),
                "youtube": ("web_search", {"query": target, "where": "youtube"}),
                "volume": ("system_control", {"action": {"up": "volume_up", "down": "volume_down",
                                                         "mute": "mute"}.get(target, "volume_up")}),
                "media": ("system_control", {"action": {"next": "media_next", "prev": "media_previous"}
                                             .get(target, "media_play_pause")}),
            }
            if verb in mapping:
                name, args = mapping[verb]
                res = self._tools.execute(name, json.dumps(args))
                self.last_actions.append((name, args, res))
        if on_sentence and reply:
            for s in re.split(r"(?<=[.!?؟])\s+", reply):
                if s.strip():
                    on_sentence(s.strip())
        return reply


class _ToolsUnsupported(Exception):
    pass