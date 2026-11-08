# -*- coding: utf-8 -*-
"""
Natural Q&A — يجاوب على أسئلة عامة باستخدام معلومات النظام أو LLM.

مثال: "كام الساعة؟" / "ساعة كام؟" / "كام الرام فاضل؟" / "الجهاز شغال بقاله قد ايه؟"
"""
import datetime
import platform
import re
import socket
import time
import psutil


def is_question(command):
    """Detect whether a command is a question (vs. an action).
    Uses whole-word matching so words like 'كمبيوتر' ('كم'), 'وينرار' ('وين'),
    or 'تيرمينال' ('مين') are never misclassified as questions."""
    cmd = (command or "").lower().strip()
    if not cmd:
        return False

    action_starts = [
        "افتح", "افتحلي", "شغل", "شغلي", "اقفل", "انهي", "قفل", "نزل", "سطب",
        "عايز افتح", "عايز أفتح", "عايز اشغل", "ممكن تفتح", "ممكن تشغل",
        "خلي", "ظبط", "اعمل", "علي", "وطي", "ارفع", "اخفض", "اكتم",
        "open", "close", "install", "kill", "start", "launch",
        "حدث", "تعلم", "علمني", "انسى", "فكرني", "نبهني", "فعل", "روق", "نضف",
    ]
    if any(cmd.startswith(v) for v in action_starts):
        return False

    if "?" in cmd or "؟" in cmd:
        return True

    phrase_indicators = [
        "ما هو", "ما هي", "قول لي", "قولي", "tell me", "what time", "what date",
        "بقاله قد ايه", "بقاله قد إيه", "أخبار الرامات", "اخبار الرامات",
        "ساعة كام", "ساعه كام", "الساعة كام", "الساعه كام",
    ]
    if any(p in cmd for p in phrase_indicators):
        return True

    word_indicators = {
        "إيه", "ايه", "كام", "كم", "مين", "فين", "وين",
        "ازاي", "إزاي", "ليه", "ليش", "امتى", "متى", "هل",
        "what", "who", "where", "when", "how", "why", "which",
    }
    words = set(re.sub(r"[،,.!؟?\"'()\[\]]+", " ", cmd).split())
    return bool(words & word_indicators)


def try_system_answer(command):
    """Answer using local system info. Returns a string or None."""
    cmd = (command or "").lower().strip()

    # Time (handles both "الساعة كام" and "ساعة كام" / "ساعه كام")
    if any(w in cmd for w in [
        "الساعة", "الساعه", "ساعة كام", "ساعه كام", "ساعة كم", "ساعه كم",
        "كام الساعة", "كام الساعه", "الوقت كام", "الوقت دلوقتي", "what time",
    ]):
        now = datetime.datetime.now()
        period = (
            "الصبح" if now.hour < 12
            else ("بالليل" if now.hour >= 18 else "بعد الظهر")
        )
        h12 = now.hour % 12 or 12
        return f"الساعة {h12}:{now.minute:02d} {period} ⏰"

    # Date (only when asking about date/day, not general questions containing "النهارده")
    if any(w in cmd for w in [
        "التاريخ", "تاريخ النهاردة", "تاريخ النهارده", "تاريخ اليوم",
        "النهاردة ايه", "النهارده ايه", "النهاردة إيه", "النهارده إيه",
        "النهاردة كام", "النهارده كام", "اليوم ايه", "what date", "what day",
    ]):
        now = datetime.datetime.now()
        days = [
            "الاثنين", "الثلاثاء", "الأربعاء", "الخميس",
            "الجمعة", "السبت", "الأحد",
        ]
        return f"النهاردة {days[now.weekday()]} {now.day}/{now.month}/{now.year} 📅"

    # Uptime
    if any(w in cmd for w in ["uptime", "بقاله قد ايه", "بقاله قد إيه", "شغال من امتى", "مفتوح من امتى"]):
        boot = psutil.boot_time()
        elapsed = int(time.time() - boot)
        hours, rem = divmod(elapsed, 3600)
        mins = rem // 60
        if hours > 0:
            return f"الجهاز شغال بقاله {hours} ساعة و {mins} دقيقة ⏱️"
        return f"الجهاز شغال بقاله {mins} دقيقة ⏱️"

    # GPU
    if any(w in cmd for w in ["gpu", "كارت الشاشة", "كارت الشاشه", "الفيجا", "حرارة الكارت"]):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                g = gpus[0]
                return (
                    f"🎮 {g.name}: استخدام {g.load * 100:.0f}% | "
                    f"VRAM: {g.memoryUsed:.0f}MB / {g.memoryTotal:.0f}MB | "
                    f"الحرارة: {g.temperature:.0f}°C"
                )
        except Exception:
            pass
        return "مش قادر أقرا بيانات كارت الشاشة حالياً 🎮"

    # RAM
    if any(w in cmd for w in ["رام", "رامات", "ram", "الذاكرة", "memory", "الرام"]):
        mem = psutil.virtual_memory()
        return (
            f"الرام: {mem.used / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB "
            f"({mem.percent}% مستخدم، فاضي {mem.available / (1024**3):.1f}GB) 🧠"
        )

    # CPU
    if any(w in cmd for w in [
        "cpu", "بروسيسور", "المعالج", "processor", "سي بي يو",
    ]):
        return f"الـ CPU: {psutil.cpu_percent(interval=0.4)}% استخدام 💻"

    # Disk
    if any(w in cmd for w in [
        "مساحة", "disk", "هارد", "storage", "space", "الهارد", "بارتيشن",
    ]):
        parts = []
        for p in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(p.mountpoint)
                parts.append(
                    f"{p.device} {u.free / (1024**3):.0f}GB فاضي"
                    f" من {u.total / (1024**3):.0f}GB"
                )
            except (PermissionError, OSError):
                pass
        return "💾 " + " | ".join(parts) if parts else None

    # IP / Network
    if any(w in cmd for w in ["ip", "اي بي", "آي بي", "عنوان الشبكة"]):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return f"عنوان الـ IP المحلي: {ip} 🌐"
        except Exception:
            return "مش متصل بالشبكة حالياً 🌐"

    # Battery
    if any(w in cmd for w in [
        "بطارية", "battery", "الشحن", "charge", "البطارية",
    ]):
        bat = psutil.sensors_battery()
        if bat:
            status = "بيشحن 🔌" if bat.power_plugged else "على البطارية 🔋"
            return f"البطارية: {bat.percent}% — {status}"
        return "مفيش بطارية (ديسكتوب) 🖥️"

    return None


def answer_with_llm(groq_client, model, command):
    """Fall back to LLM for general knowledge questions."""
    try:
        resp = groq_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "أنت يوبي — مساعد ذكي بالعامية المصرية. "
                        "جاوب بإجابة قصيرة ومفيدة (جملة أو اتنين بالكتير). "
                        "لو السؤال محتاج إنترنت أو معلومات مش عندك، "
                        "قول كده بأمانة."
                    ),
                },
                {"role": "user", "content": command},
            ],
            temperature=0.5,
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"معرفتش أجاوب: {e}"