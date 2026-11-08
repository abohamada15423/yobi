# -*- coding: utf-8 -*-
"""
Chat Engine — عقل المحادثة الطبيعي ليوبي.

Uses conversation memory + a warm, capable system prompt. The LLM can also
emit a [CMD:verb:target] marker to trigger a PC action mid-conversation,
which the caller parses and executes.

(Recovered from bytecode. In v3 this is only the FALLBACK used by brain.py
when the model doesn't support tool calling.)
"""

import re

from chat_memory import ChatMemory

_SYSTEM_PROMPT = 'أنت يوبي (Yobi) — مساعد ذكي على كمبيوتر المستخدم، بتتكلم معاه بالعامية المصرية.\n\nشخصيتك:\n• صاحب ذكي وودود — مش روبوت، مش خدمة عملاء.\n• عندك آراء، بتسأل، بتعلّق على الموضوع. بتتفاعل، مش بس بتجاوب.\n• لو حد بيهزر، اضحك معاه. لو الموضوع جدّي، خليك جدّي.\n• اتكلم بنفس لغة اللي قدامك: كاجوال / مصري عامي / إنجليزي لو هو إنجليزي.\n• متبدأش ردودك بـ "بالطبع" أو "سؤال ممتاز" أو "بكل تأكيد" — ابدأ طبيعي زي صاحبك.\n• متقولش إنك AI أو chatbot.\n• لو مش متأكد، قول "مش متأكد" أو اسأل — متألّفش.\n\nطول الرد:\n• 1-3 جمل في العادي.\n• لو الموضوع محتاج تفصيل، اكتب براحتك، بس من غير حشو.\n• مفيش markdown، مفيش نجوم، مفيش رموز — ده بيتنطق بصوت.\n\nقدراتك الحقيقية:\nتقدر تتحكم في كمبيوتر المستخدم. لما يطلب حاجة، أو لما الرد لازم يشمل فعل،\nاكتب في آخر الرد سطر بالظبط بالشكل ده:\n\n[CMD:verb:target]\n\nالأفعال المتاحة:\n  open   → افتح برنامج/لعبة/موقع (target = الاسم)\n  close  → اقفل برنامج (target = الاسم)\n  volume → علي/وطي/اكتم الصوت (target = up/down/mute)\n  media  → تحكم في الأغاني (target = play/pause/next/prev)\n  search → ابحث على جوجل (target = الاستعلام)\n  youtube → ابحث على يوتيوب (target = الاستعلام)\n\nأمثلة:\n  "تمام، فتحتلك سبوتيفاي. [CMD:open:spotify]"\n  "هشغلك أغنية عمرو دياب على يوتيوب. [CMD:youtube:عمرو دياب]"\n  "رفعت الصوت شوية. [CMD:volume:up]"\n\nمهم: اكتب الـ marker مرة واحدة بالكتظ في آخر الرد. لو مفيش فعل مطلوب،\nمتكتبش marker خالص — رد طبيعي بس.\n\nلو المستخدم سأل سؤال معرفة عامة (تاريخ، علوم، رأي، ...)، جاوب من\nالمعرفة العادية بتاعتك — بذكاء وبإيجاز.'

_CMD_RE = re.compile(r"\[CMD:(\w+):([^\]]*)\]", re.IGNORECASE)


class ChatEngine:
    """Conversational brain with memory + optional action markers."""

    def __init__(self, client, model, memory=None):
        self._client = client
        self._model = model
        self._memory = memory or ChatMemory()
        self._last_action = None

    def set_last_action(self, description):
        """Called by the agent after executing an action, so the LLM knows
        what Yobi just did."""
        self._last_action = description

    def chat(self, user_text, extra_context=None):
        """Send the message to the LLM with full history.

        Returns (reply_text_clean, action_or_None).
        action = {"verb": "open", "target": "spotify"} if the model emitted
        a [CMD:...] marker, else None.
        """
        if not user_text or not user_text.strip():
            return "", None

        self._memory.add_user(user_text)

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

        ctx_lines = []
        if extra_context:
            ctx_lines.append(extra_context)
        if self._last_action:
            ctx_lines.append(f"آخر حاجة عملتها: {self._last_action}")
        if ctx_lines:
            messages.append({
                "role": "system",
                "content": "سياق لحظي: " + " | ".join(ctx_lines),
            })

        messages.extend(self._memory.get_messages())

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.75,
                max_tokens=400,
            )
            raw = response.choices[0].message.content.strip()
        except Exception as e:
            return f"معلش، حصلت مشكلة في الاتصال: {e}", None

        action = None
        m = _CMD_RE.search(raw)
        if m:
            verb = m.group(1).lower().strip()
            target = m.group(2).strip()
            action = {"verb": verb, "target": target}

        clean = _CMD_RE.sub("", raw).strip()
        clean = re.sub(r"\s+", " ", clean).strip()

        if clean:
            self._memory.add_assistant(clean)

        return clean, action

    def clear(self):
        self._memory.clear()
        self._last_action = None

    def is_empty(self):
        return self._memory.is_empty()

    def turn_count(self):
        return self._memory.turn_count()

    @staticmethod
    def build_context(agent, scheduler=None):
        """Short context string: time, running apps, pending reminders."""
        import datetime as _dt

        parts = []
        now = _dt.datetime.now()
        parts.append(f"الوقت {now.strftime('%H:%M')} {now.strftime('%A')}")

        try:
            import psutil
            known = set()
            for proc in psutil.process_iter(["name"]):
                n = (proc.info.get("name") or "").lower().replace(".exe", "")
                if n:
                    known.add(n)
            interesting = [
                a for a in ("spotify", "chrome", "firefox", "discord",
                            "steam", "vscode", "code", "notepad")
                if a in known
            ]
            if interesting:
                parts.append("مفتوح دلوقتي: " + ", ".join(interesting))
        except Exception:
            pass

        if scheduler is not None:
            try:
                tasks = scheduler.list_tasks()
                if tasks:
                    parts.append(f"{len(tasks)} مهمة مجدولة")
            except Exception:
                pass

        return " | ".join(parts)
