# -*- coding: utf-8 -*-
"""
Local brain — understands Yobi's everyday commands on the PC itself, with no API key and no
internet, and answers in the same tool language Gemini uses (open_app, close_app,
system_control, play_media, web_search, set_reminder, schedule_command, system_info,
pc_command, activate_mode), so the same YobiTools run them.

How: a small text classifier (char n-grams, scikit-learn, <10 ms) picks the intent, then plain
rules pull out the details (the app's name, the song, the number, the time). It's trained on
this PC at startup from built-in Egyptian/English phrasings plus this PC's own app names, with
speech-to-text slips mixed in ("السوط" for "الصوت"), so a friend's copy knows *their* apps.
When it isn't sure it says so (returns None) instead of guessing: chatter around the mic must
never open anything.

    lb = LocalBrain.train(app_names=["discord", "valorant"], is_app=lambda name: ...)
    lb.understand("علي الصوت شوية")   # → Decision('system_control', {'action': 'volume_up'}, ...)
    lb.understand("صباح الفل")        # → None (chat: needs the Gemini key)
"""
import random
import re
import time

from intent_model import normalize

# ── what each intent becomes ─────────────────────────────────────────────────
SYSTEM = {   # intent → system_control action
    "volume_up": "volume_up", "volume_down": "volume_down", "volume_max": "volume_max",
    "volume_min": "volume_min", "mute": "mute", "unmute": "unmute",
    "media_play_pause": "media_play_pause", "media_next": "media_next", "media_previous": "media_previous",
    "brightness_up": "brightness_up", "brightness_down": "brightness_down", "lock_screen": "lock_screen",
    "screenshot": "screenshot", "free_ram": "free_ram", "sleep": "sleep", "shutdown": "shutdown",
    "restart": "restart", "log_off": "log_off", "cancel_shutdown": "cancel_shutdown",
}
NONE = "none"
MAX_NAME_WORDS = 5          # "league of legends", "euro truck simulator 2" fit; a sentence doesn't

# ── phrasings ({app} app/game/site, {song} something to play, {q} a search, {n} a number,
#    {dur} a duration, {todo} a reminder text) ─────────────────────────────────
TEMPLATES = {
    "open_app": ["افتح {app}", "افتحلي {app}", "افتح لي {app}", "افتحي {app}", "شغل {app}", "شغلي {app}",
                 "شغللي {app}", "عايز افتح {app}", "عاوز افتح {app}", "ممكن تفتح {app}", "ممكن تفتحلي {app}",
                 "يلا افتح {app}", "دخلني على {app}", "ادخل على {app}", "روح على {app}", "هاتلي {app}",
                 "عايز العب {app}", "يلا نلعب {app}", "افتح برنامج {app}", "افتح لعبة {app}", "افتح موقع {app}",
                 "تشغيل {app}", "فتح {app}", "open {app}", "launch {app}", "start {app}", "run {app}",
                 "open up {app}", "افتح ال {app}", "{app} لو سمحت", "افتح {app} بسرعة", "افتح {app} يا يوبي"],
    "close_app": ["اقفل {app}", "قفل {app}", "اقفلي {app}", "اقفللي {app}", "اقفل لي {app}", "سكر {app}",
                  "اغلق {app}", "اقفل برنامج {app}", "اقفل لعبة {app}", "طلعني من {app}", "اخرج من {app}",
                  "اقفل ال {app}", "عايز اقفل {app}", "ممكن تقفل {app}", "close {app}", "kill {app}",
                  "exit {app}", "اقتل {app}", "انهي {app}", "اقفل {app} خالص"],
    "volume_up": ["علي الصوت", "علي الصوت شوية", "علي الصوت شويه", "ارفع الصوت", "زود الصوت", "علي الصوت حبة",
                  "الصوت واطي", "الصوت واطي اوي", "مش سامع حاجة", "مش سامع", "عليه شوية", "صوت اعلى",
                  "volume up", "louder", "turn it up", "turn up the volume", "علي الصوت كمان"],
    "volume_down": ["وطي الصوت", "وطي الصوت شوية", "نزل الصوت", "قلل الصوت", "الصوت عالي", "الصوت عالي اوي",
                    "وطي شوية", "اهدى الصوت", "صوت اوطى", "volume down", "quieter", "turn it down",
                    "lower the volume", "الصوت جامد اوي"],
    "volume_max": ["الصوت على الاخر", "علي الصوت على الاخر", "اعلى صوت", "الصوت مية في المية", "max volume",
                   "full volume", "الصوت فول"],
    "volume_min": ["اقل صوت", "وطي الصوت خالص", "الصوت على الاقل", "min volume", "lowest volume"],
    "set_volume": ["خلي الصوت {n}", "الصوت على {n}", "خلي الصوت {n} في المية", "اظبط الصوت على {n}",
                   "الصوت {n} في المية", "set volume to {n}", "volume {n}", "volume to {n} percent",
                   "خلي الصوت على {n}"],
    "mute": ["اكتم الصوت", "ميوت", "اعمل ميوت", "اقفل الصوت", "اقفل الصوت خالص", "mute", "mute the sound",
             "كتم الصوت", "شيل الصوت"],
    "unmute": ["رجع الصوت", "فك الميوت", "شيل الميوت", "شغل الصوت تاني", "unmute", "رجعلي الصوت"],
    "media_play_pause": ["وقف الاغنية", "وقف الاغنيه", "وقف الفيديو", "كمل الاغنية", "كمل الفيديو", "بوز",
                         "pause", "play", "resume", "استوب", "وقف المزيكا", "شغل المزيكا تاني", "وقفها",
                         "كملها", "pause the music", "resume the video"],
    "media_next": ["الاغنية اللي بعدها", "اللي بعدها", "اللي بعده", "next", "next song", "سكيب", "skip",
                   "عدي الاغنية", "غير الاغنية", "الاغنية الجاية", "الفيديو اللي بعده"],
    "media_previous": ["الاغنية اللي فاتت", "اللي قبلها", "اللي فات", "previous", "previous song", "رجع الاغنية",
                       "الاغنية اللي قبلها", "back", "go back a song"],
    "brightness_up": ["علي الاضاءة", "علي الاضاءه", "زود الاضاءة", "نور الشاشة", "زود السطوع", "الشاشة ضلمة",
                      "الشاشة غامقة", "brightness up", "brighter", "علي النور"],
    "brightness_down": ["وطي الاضاءة", "قلل الاضاءة", "وطي السطوع", "الشاشة منورة اوي", "الاضاءة عالية",
                        "brightness down", "dimmer", "دمي الشاشة", "وطي النور"],
    "set_brightness": ["خلي الاضاءة {n}", "الاضاءة على {n}", "خلي السطوع {n}", "set brightness to {n}",
                       "brightness {n}", "الاضاءة {n} في المية"],
    "lock_screen": ["اقفل الشاشة", "اقفل الشاشه", "اعمل لوك", "لوك", "lock", "lock the screen", "lock my pc",
                    "قفل الشاشة"],
    "screenshot": ["خد سكرين شوت", "اسكرين شوت", "سكرين شوت", "صور الشاشة", "صورلي الشاشة", "screenshot",
                   "take a screenshot", "خد صورة للشاشة", "اسكرينة"],
    "free_ram": ["فضي الرامات", "فضي الرام", "نضف الرام", "الجهاز تقيل", "الجهاز بطيء", "free ram",
                 "clean the ram", "فضيلي الرامات", "خفف الجهاز"],
    "sleep": ["نيم الجهاز", "اعمل سليب", "sleep", "خلي الجهاز ينام", "سليب"],
    "shutdown": ["اقفل الجهاز", "اطفي الجهاز", "اقفل الكمبيوتر", "اطفي الكمبيوتر", "shutdown", "shut down",
                 "turn off the pc", "اعمل شت داون", "قفل الجهاز"],
    "restart": ["ريستارت", "اعمل ريستارت", "اعمل ريستارت للجهاز", "restart", "reboot", "عيد تشغيل الجهاز"],
    "log_off": ["سجل خروج", "اعمل ساين اوت", "log off", "sign out"],
    "cancel_shutdown": ["الغي الاطفاء", "متقفلش الجهاز", "cancel shutdown", "الغي القفل", "بلاش تقفل الجهاز"],
    "play_media": ["شغل اغنية {song}", "شغلي اغنية {song}", "شغل {song} على يوتيوب", "عايز اسمع {song}",
                   "عاوز اسمع {song}", "سمعني {song}", "شغل اغاني {song}", "شغل سورة {song}", "شغلي سورة {song}",
                   "شغل فيديو {song}", "شغل حاجة ل{song}", "play {song}", "play {song} on youtube",
                   "حطلي اغنية {song}", "شغل الاغنية بتاعة {song}"],
    "web_search": ["ابحث عن {q}", "دور على {q}", "دورلي على {q}", "ابحث في جوجل عن {q}", "دور على {q} في جوجل",
                   "جوجل {q}", "search {q}", "search for {q}", "google {q}", "ابحث على يوتيوب عن {q}",
                   "دور على {q} في يوتيوب", "عايز اعرف عن {q}"],
    "set_reminder": ["فكرني {todo} بعد {dur}", "فكرني بعد {dur} {todo}", "فكرني ا{todo} بعد {dur}",
                     "نبهني بعد {dur} {todo}", "ذكرني بعد {dur} {todo}", "remind me in {dur} to {todo}",
                     "فكرني كمان {dur} {todo}", "بعد {dur} فكرني {todo}"],
    "schedule_command": ["اقفل {app} بعد {dur}", "اقفلي {app} بعد {dur}", "افتح {app} بعد {dur}",
                         "بعد {dur} اقفل {app}", "اطفي الجهاز بعد {dur}", "اقفل الجهاز بعد {dur}",
                         "close {app} in {dur}"],
    "system_info": ["الساعة كام", "الساعه كام", "كام الساعة", "النهاردة ايه", "النهارده كام في الشهر",
                    "التاريخ ايه", "البطارية كام", "الشحن كام", "الرام فاضي كام", "الرامات كام",
                    "الجهاز سخن", "حرارة الجهاز", "المعالج شغال كام", "الهارد فاضي كام", "المساحة الفاضية",
                    "الاي بي بتاعي", "الجهاز شغال من امتى", "what time is it", "battery level",
                    "how much ram", "النت شغال", "سرعة النت"],
    "pc_command": ["افحص جهازي", "افحص الجهاز", "اعمل فحص للجهاز", "ايه اللي شغال", "البرامج المفتوحة",
                   "افتح فولدر التحميلات", "افتح التحميلات", "افتح الديسكتوب", "افتح المستندات",
                   "اعمل فولدر اسمه {q}", "دور على ملف {q}", "فين ملف {q}", "برامج البدء",
                   "عطل {app} من البدء", "scan my pc", "open downloads folder"],
    "activate_mode": ["وضع المذاكرة", "وضع المذاكره", "يلا نذاكر", "وضع الجيمنج", "وضع الالعاب", "يلا نلعب",
                      "وضع السينما", "يلا نتفرج على فيلم", "study mode", "gaming mode", "cinema mode"],
    NONE: ["صباح الفل", "صباح الخير", "مساء الخير", "ازيك", "عامل ايه", "انت مين", "انت عامل ايه",
           "شكرا", "شكرا يا يوبي", "تسلم", "حبيبي", "يا حبيبي", "خلاص", "خلاص خلاص", "تمام", "ماشي",
           "ايوه", "لا", "اه", "طب", "وبعدين", "انا اسمي احمد", "اسمي محمد", "احكيلي نكتة", "قولي نكتة",
           "ايه رأيك في الماتش", "مين كسب امبارح", "انا زهقان", "انا جعان", "عايز اكل", "اعمل ايه النهاردة",
           "ازاي اعمل كيكة", "اشرح لي الفيزيا", "ترجم كلمة apple", "اكتبلي ايميل", "يلا يا جدعان",
           "حد معايا", "روح هناك", "خش من الشمال", "خلي بالك وراك", "اقلب العربية", "ارمي الكورة",
           "جول جول", "يا عم ركز", "انت فين", "استنى استنى", "انا جاي", "هات الفلوس", "كام فلوس معاك",
           "اشتري السلاح ده", "ادخل البيت", "هو فيه ايه", "ايه ده", "مش فاهم حاجة", "يا ساتر",
           "الله", "ههههه", "يا نهار ابيض", "بجد", "طيب يلا", "انا تعبان", "هنام", "تصبح على خير",
           "how are you", "hello", "thanks", "good morning", "what's up", "who are you", "lol", "ok",
           "go go go", "nice shot", "come here", "watch out", "let's go", "gg", "i'm hungry"],
}

APPS = ["discord", "ديسكورد", "spotify", "سبوتيفاي", "youtube", "يوتيوب", "chrome", "كروم", "فايرفوكس",
        "steam", "ستيم", "valorant", "فالورانت", "minecraft", "ماين كرافت", "netflix", "نتفليكس",
        "whatsapp", "واتساب", "telegram", "تليجرام", "facebook", "فيسبوك", "instagram", "انستجرام",
        "word", "وورد", "excel", "اكسل", "vs code", "فيجوال ستوديو", "notepad", "المفكرة", "الحاسبة",
        "calculator", "paint", "الرسام", "zoom", "زوم", "teams", "تيمز", "fifa", "فيفا", "pubg", "ببجي",
        "fortnite", "فورتنايت", "gta", "جي تي ايه", "league of legends", "ليج اوف ليجندز", "rocket league",
        "روكيت ليج", "obs", "photoshop", "فوتوشوب", "tiktok", "تيك توك", "gmail", "جيميل", "الاعدادات",
        "settings", "الملفات", "file explorer", "task manager", "مدير المهام", "cmd", "التيرمينال"]
SONGS = ["عمرو دياب", "تملي معاك", "ويجز", "مروان بابلو", "ام كلثوم", "انت عمري", "محمد منير", "عبد الحليم",
         "تامر حسني", "حمو بيكا", "شيرين", "الكهف", "الرحمن", "يس", "الملك", "مشاري العفاسي", "عبد الباسط",
         "the weeknd", "eminem", "lofi", "مزيكا هادية", "اغاني رمضان", "drake", "adele", "فيروز", "الرقية الشرعية"]
QUERIES = ["سعر الدولار", "مواعيد الماتش", "وصفة كشري", "اخبار الاهلي", "ازاي اعمل سي في", "افضل لابتوب",
           "طقس بكرة", "شرح بايثون", "ترجمة جوجل", "اسعار الدهب", "how to install python", "best games 2026"]
TODOS = ["اشرب مية", "اصلي العصر", "اكلم ماما", "اخد الدوا", "اقوم من على الكمبيوتر", "اطفي الفرن",
         "المذاكرة", "الاجتماع", "drink water", "call mom"]
NUMS = ["10", "20", "30", "40", "50", "60", "70", "80", "90", "100", "عشرة", "عشرين", "تلاتين", "اربعين",
        "خمسين", "ستين", "سبعين", "تمانين", "تسعين", "مية", "النص", "٥٠", "٣٠"]
DURS = ["5 دقايق", "خمس دقايق", "عشر دقايق", "ربع ساعة", "نص ساعة", "ساعة", "ساعتين", "ساعة ونص", "دقيقة",
        "دقيقتين", "تلات ساعات", "20 دقيقة", "10 minutes", "an hour", "half an hour", "تلت ساعة"]

# ── speech-to-text slips, so the model expects them ─────────────────────────
_SWAPS = [("ص", "س"), ("س", "ص"), ("ط", "ت"), ("ت", "ط"), ("ض", "د"), ("ظ", "ز"), ("ذ", "ز"), ("ث", "س"),
          ("ق", "ا"), ("ق", "ك"), ("ه", "ة"), ("ي", "ى"), ("ا", ""), ("و", ""), ("ك", "ج")]
_FILLERS = ["يوبي ", "يا يوبي ", "لو سمحت ", "ممكن ", "بقولك ", "", "", ""]
_TAILS = [" لو سمحت", " بقى", " دلوقتي", " يا يوبي", " بسرعة", "", "", "", ""]


def _slip(text, rnd):
    t = text
    for _ in range(rnd.choice((0, 0, 1, 1, 2))):
        a, b = rnd.choice(_SWAPS)
        idx = [i for i, ch in enumerate(t) if ch == a]
        if idx:
            i = rnd.choice(idx)
            t = t[:i] + b + t[i + 1:]
    if rnd.random() < 0.15:
        t = t.replace("ال", "", 1)
    if rnd.random() < 0.1 and " " in t:
        i = rnd.choice([i for i, ch in enumerate(t) if ch == " "])
        t = t[:i] + t[i + 1:]
    return t


def _fill(tpl, rnd, apps):
    return (tpl.replace("{app}", rnd.choice(apps)).replace("{song}", rnd.choice(SONGS))
            .replace("{q}", rnd.choice(QUERIES)).replace("{n}", rnd.choice(NUMS))
            .replace("{dur}", rnd.choice(DURS)).replace("{todo}", rnd.choice(TODOS)))


def make_dataset(app_names=(), per_intent=260, seed=7, extra=()):
    """Generated (text, intent) pairs: every phrasing with apps/songs/numbers filled in, fillers
    around it and STT slips in about half of them. `extra`: real (text, intent) pairs to add."""
    rnd = random.Random(seed)
    apps = list(dict.fromkeys([a for a in APPS] + [str(a).lower() for a in app_names if a]))
    out = []
    for intent, tpls in TEMPLATES.items():
        n = per_intent * (3 if intent == NONE else 1)
        for i in range(n):
            t = _fill(tpls[i % len(tpls)], rnd, apps)
            t = rnd.choice(_FILLERS) + t + rnd.choice(_TAILS) if intent != NONE else t
            if rnd.random() < 0.5:
                t = _slip(t, rnd)
            out.append((normalize(t), intent))
    # bare names ("سبوتيفاي", "يوتيوب") mean "open it"
    for a in apps:
        out.append((normalize(a), "open_app"))
    out += [(normalize(t), y) for t, y in extra]
    return out


# ── details ──────────────────────────────────────────────────────────────────
_NUM_WORDS = {"واحد": 1, "اتنين": 2, "تلاته": 3, "تلات": 3, "اربعه": 4, "اربع": 4, "خمسه": 5, "خمس": 5,
              "سته": 6, "ست": 6, "سبعه": 7, "سبع": 7, "تمانيه": 8, "تمن": 8, "تسعه": 9, "تسع": 9, "عشره": 10,
              "عشر": 10, "خمستاشر": 15, "عشرين": 20, "تلاتين": 30, "اربعين": 40, "خمسين": 50, "ستين": 60,
              "سبعين": 70, "تمانين": 80, "تسعين": 90, "ميه": 100, "النص": 50, "نص": 50,
              "one": 1, "two": 2, "three": 3, "five": 5, "ten": 10, "twenty": 20, "thirty": 30, "fifty": 50}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def parse_number(text):
    t = normalize(text).translate(_DIGITS)
    m = re.search(r"\d+(?:\.\d+)?", t)
    if m:
        return float(m.group())
    for w in t.split():
        if w in _NUM_WORDS:
            return float(_NUM_WORDS[w])
    return None


def parse_minutes(text):
    """'بعد نص ساعة' → 30, 'ساعتين' → 120, '5 دقايق' → 5, 'an hour' → 60. None if no duration."""
    t = " " + normalize(text).translate(_DIGITS) + " "
    if re.search(r"\bساعه ونص\b|\bhour and a half\b", t):
        return 90.0
    if re.search(r"\bنص ساعه\b|\bhalf an hour\b", t):
        return 30.0
    if re.search(r"\bربع ساعه\b|\bquarter of an hour\b", t):
        return 15.0
    if re.search(r"\bتلت ساعه\b", t):
        return 20.0
    if re.search(r"\bساعتين\b", t):
        return 120.0
    if re.search(r"\bدقيقتين\b", t):
        return 2.0
    m = re.search(r"(\d+|\w+)\s+(ساعات|ساعه|hours?)\b", t)
    if m:
        n = parse_number(m.group(1))
        return 60.0 * (n or 1)
    m = re.search(r"(\d+|\w+)\s+(دقايق|دقيقه|دقائق|minutes?|mins?)\b", t)
    if m:
        n = parse_number(m.group(1))
        return n if n else None
    if re.search(r"\b(ساعه|an hour|one hour)\b", t):
        return 60.0
    if re.search(r"\bدقيقه\b|\ba minute\b", t):
        return 1.0
    return None


_LEAD = r"^(?:(?:يا )?يوبي|لو سمحت|ممكن|بقولك|يلا|please|hey yobi|yobi)\s+"
_TAIL = r"\s+(?:لو سمحت|بقي|دلوقتي|يا يوبي|بسرعه|please|now)$"
_OPEN_VERBS = (r"^(?:عايز|عاوز|ممكن)?\s*(?:افتح(?:لي|ي| لي)?|شغل(?:لي|ي| لي)?|تشغيل|فتح|تفتح(?:لي)?|ادخل على|"
               r"دخلني على|روح على|هاتلي|العب|نلعب|open up|open|launch|start|run)\s+"
               r"(?:برنامج|لعبه|موقع|ال(?=\s))?\s*")
_CLOSE_VERBS = (r"^(?:عايز|عاوز|ممكن)?\s*(?:اقفل(?:لي|ي| لي)?|قفل(?:لي|ي)?|تقفل|سكر|اغلق|اقتل|انهي|طلعني من|اخرج من|"
                r"close|kill|exit)\s+(?:برنامج|لعبه|ال(?=\s))?\s*")
_PLAY_VERBS = (r"^(?:شغل(?:لي|ي| لي)?|حطلي|سمعني|عايز اسمع|عاوز اسمع|play)\s+"
               r"(?:اغنيه|اغاني|الاغنيه بتاعه|فيديو|حاجه ل|سوره)?\s*")
_SEARCH_VERBS = r"^(?:ابحث|دور(?:لي)?|search(?: for)?|google|جوجل|عايز اعرف)\s*(?:في جوجل|على يوتيوب|في يوتيوب)?\s*(?:عن|على|for)?\s*"


_DUR = (r"(?:بعد|كمان|in)\s+(?:\S+\s+)?(?:ساعات|ساعه|ساعتين|دقايق|دقيقه|دقائق|دقيقتين|minutes?|mins?|hours?)(?:\s+ونص)?|(?:بعد|كمان)\s+(?:نص|ربع|تلت)\s+ساعه|in half an hour|in an hour")
_MEDIA_WORDS = r"(?:ال)?(?:اغني|اغنيه|اغاني|مزيكا|موسيقي|مقطع|فيديو|فيلم|قران|سوره|بودكاست|song|songs|music|video)"
_LATER_VERBS = r"(?:^|\s)(?:افتح|اقفل|قفل|شغل|سكر|اطفي|open|close|launch|shut ?down|restart|ريستارت)(?:\s|$)"


def _strip(text):
    t = normalize(text)
    for _ in range(2):
        t = re.sub(_LEAD, "", t)
        t = re.sub(_TAIL, "", t)
    return t.strip()


def _after(pattern, text):
    t = _strip(text)
    rest = re.sub(pattern, "", t, count=1).strip()
    return rest if rest != t else ""


def _minus_first_word(text):
    """'افطح ديسكورد' → 'ديسكورد' (a misheard verb), 'عايز ادخل يوتيوب' → 'يوتيوب'."""
    words = re.sub(r"^(?:عايز|عاوز|ممكن)\s+", "", _strip(text)).split()
    return " ".join(words[1:]) if len(words) > 1 else ""


class Decision:
    __slots__ = ("tool", "args", "intent", "prob", "ms")

    def __init__(self, tool, args, intent, prob, ms):
        self.tool, self.args, self.intent, self.prob, self.ms = tool, args, intent, prob, ms

    def __repr__(self):
        return f"<Decision {self.tool} {self.args} ({self.intent} {self.prob:.2f}, {self.ms:.1f}ms)>"


class LocalBrain:
    def __init__(self, pipe, threshold=0.6, app_score=None):
        self.pipe = pipe
        self.threshold = threshold
        self.app_score = app_score or (lambda name: 0.0)    # 0..1: how surely `name` is an app on this PC

    def is_app(self, name, sure=0.8):
        return bool(name) and len(name.split()) <= MAX_NAME_WORDS and self.app_score(name) >= sure

    @classmethod
    def train(cls, app_names=(), app_score=None, extra=(), threshold=0.6, seed=7):
        from intent_model import build_pipeline
        data = make_dataset(app_names, seed=seed, extra=extra)
        pipe = build_pipeline()
        pipe.fit([x for x, _ in data], [y for _, y in data])
        return cls(pipe, threshold, app_score)

    def top(self, text, k=3):
        probs = self.pipe.predict_proba([normalize(text)])[0]
        order = probs.argsort()[::-1][:k]
        return [(self.pipe.classes_[i], float(probs[i])) for i in order]

    def understand(self, text):
        """A Decision for YobiTools.execute(tool, args), or None when unsure / not a command."""
        t0 = time.perf_counter()
        x = _strip(text)
        if not x:
            return None
        (intent, p), = self.top(x, 1)
        if intent == NONE or p < self.threshold:
            return None
        made = self._details(intent, x, text)
        if made is None:
            return None
        tool, args = made
        return Decision(tool, args, intent, p, (time.perf_counter() - t0) * 1000)

    def _details(self, intent, x, raw):
        if intent in SYSTEM:
            return "system_control", {"action": SYSTEM[intent]}
        if intent in ("set_volume", "set_brightness"):
            n = parse_number(x)
            if n is None:
                return None
            return "system_control", {"action": intent, "level": max(0, min(100, int(n)))}
        if intent in ("open_app", "play_media"):
            name = _after(_OPEN_VERBS, x)
            song = _after(_PLAY_VERBS, x)
            if intent == "open_app" and not name:
                rest = _minus_first_word(x)
                name = x if self.is_app(x) else rest if self.is_app(rest) else ""   # only apps on this PC
            if len(name.split()) > MAX_NAME_WORDS:
                return None                                   # a whole sentence isn't an app's name
            if re.fullmatch(_MEDIA_WORDS, name) or re.match(_MEDIA_WORDS + r"\s", name):
                return "play_media", {"query": name}          # "شغل اغنيه" / "شغل مزيكا هاديه": play, not an app
            # "شغل X" / "عايز اسمع X": close to an app on this PC → open it, otherwise play it
            if name and (intent == "open_app" or self.is_app(name, sure=0.6)):
                return "open_app", {"name": name}
            if song and self.is_app(song, sure=0.6):
                return "open_app", {"name": song}
            return ("play_media", {"query": song or name}) if (song or name) else None
        if intent == "close_app":
            name = _after(_CLOSE_VERBS, x)
            if not name and self.is_app(_minus_first_word(x)):
                name = _minus_first_word(x)
            if re.fullmatch(r"(?:ال)?(?:جهاز|اجهاز|كمبيوتر|لابتوب|بي سي|pc|computer)", name):
                return "system_control", {"action": "shutdown"}       # asks before doing it
            if len(name.split()) > MAX_NAME_WORDS:
                return None
            return ("close_app", {"name": name}) if name else None
        if intent == "web_search":
            q = _after(_SEARCH_VERBS, x)
            q = re.sub(r"\s*(?:في|على|on)\s*(?:جوجل|يوتيوب|google|youtube)\s*$", "", q).strip()
            if not q:
                return None
            return "web_search", {"query": q, "where": "youtube" if re.search(r"يوتيوب|youtube", x) else "google"}
        if intent == "set_reminder":
            m = parse_minutes(x)
            if m is None or not re.search(r"فكرني|نبهني|ذكرني|remind", x):
                return None
            todo = re.sub(r"\s+", " ", re.sub(_DUR, "", x)).strip()
            todo = re.sub(r"^(?:فكرني|نبهني|ذكرني|remind me)\s*(?:to\s+)?", "", todo).strip() or "تذكير"
            return "set_reminder", {"minutes": m, "text": todo}
        if intent == "schedule_command":
            m = parse_minutes(x)
            # "اقفل X بعد ساعة": a real command verb and a "بعد/in" time, not any sentence with "ساعة"
            if m is None or not re.search(r"(?:^|\s)(?:بعد|in)\s", x) or not re.search(_LATER_VERBS, x):
                return None
            cmd = re.sub(r"\s+", " ", re.sub(_DUR, "", x)).strip()
            return ("schedule_command", {"minutes": m, "command": cmd}) if cmd else None
        if intent == "system_info":
            return "system_info", {"question": raw}
        if intent == "pc_command":
            return "pc_command", {"command": raw}
        if intent == "activate_mode":
            mode = ("study" if re.search(r"مذاكر|study|نذاكر", x) else "gaming" if re.search(r"جيمنج|العاب|gaming|نلعب", x)
                    else "cinema" if re.search(r"سينما|فيلم|cinema", x) else None)
            return ("activate_mode", {"mode": mode}) if mode else None
        return None


# ── this PC: its apps, games and sites, trained once and cached ─────────────
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402

VERSION = 1                  # bump when TEMPLATES or the features change (retrains every cache)
_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "models", "local_brain.joblib")      # this PC's names: not shipped


def catalog_names(catalog):
    """Every way this PC's programs, games and sites can be called: names + Arabic/short aliases."""
    names = []
    for e in getattr(catalog, "entries", []):
        for n in [e.display, *sorted(e.aliases)]:
            n = str(n or "").strip().lower()
            if 1 < len(n) <= 40 and not n.startswith(("http", "__")):
                names.append(n)
    return list(dict.fromkeys(names))


def learned_phrases(path=os.path.join(_HERE, "learned_commands.json")):
    """What already worked on this PC ("افتح ليجو في اللجنس" → league of legends): more open_app examples."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [(p, "open_app") for p, v in data.items() if isinstance(v, dict) and v.get("target")]
    except (OSError, ValueError):
        return []


def for_catalog(catalog, extra=None, cache=CACHE_PATH, log=print):
    """The LocalBrain for this PC: loads the cache when the catalog didn't change, else trains (~10 s)."""
    import target_resolver as tr

    def app_score(name):
        r = tr.resolve(catalog, name)
        return float(r.score or 0) if r.status in ("ok", "ask") and r.best is not None else 0.0

    names = catalog_names(catalog)
    extra = learned_phrases() if extra is None else list(extra)
    key = hashlib.sha1(json.dumps([VERSION, TEMPLATES, names, extra], ensure_ascii=False).encode()).hexdigest()
    try:
        import joblib
        if os.path.exists(cache):
            saved = joblib.load(cache)
            if saved.get("key") == key:
                return LocalBrain(saved["pipe"], app_score=app_score)
    except Exception as e:
        log(f"ℹ️ local brain cache: {str(e)[:80]}")
    t = time.time()
    brain = LocalBrain.train(app_names=names, app_score=app_score, extra=extra)
    log(f"🧠 الموديل المحلي اتدرّب على {len(names)} اسم لبرامج وألعاب ومواقع الجهاز ({time.time() - t:.0f} ث)")
    try:
        import joblib
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        joblib.dump({"key": key, "pipe": brain.pipe}, cache)
    except Exception as e:
        log(f"ℹ️ local brain cache: {str(e)[:80]}")
    return brain
