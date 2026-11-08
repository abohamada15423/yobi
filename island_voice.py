# -*- coding: utf-8 -*-
"""Voice commands for the island's own things (agent.py asks this before the media/YouTube step):

  • the prayer times — "الصلاة الجاية امتى؟", "فاضل قد إيه على المغرب؟", "العصر الساعة كام؟"
  • the island's pages — "افتح الرف"، "الحافظة"، "التطبيقات"، "اللي فات"، "مواقيت الصلاة"،
    "إعدادات يوبي"

match_island_command(text, island) returns None (not ours), ("say", reply) or ("page", page).
"""
import re
import time

_PRAYERS = {"fajr": "الفجر", "dhuhr": "الظهر", "asr": "العصر", "maghrib": "المغرب", "isha": "العشاء"}
_ORDER = ("fajr", "dhuhr", "asr", "maghrib", "isha")
# how people say each prayer, spelt the ways speech-to-text writes them
_SAY = {
    "fajr": r"ال?فجر", "dhuhr": r"ال?ظ[هح]ر|ال?ضهر|ال?دهر", "asr": r"ال?عصر",
    "maghrib": r"ال?مغرب", "isha": r"ال?عشا[ءئ]?",
}
_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

_OPEN = r"(?:افتح(?:لي)?|افتحلي|وريني|اعرض(?:لي)?|هات(?:لي)?|ورّيني)\s+"
_PAGES = [  # (pattern, page) — checked in order
    (rf"^(?:{_OPEN})?مواقيت\s+ال?صلا[ةه]$", "prayer"),
    (rf"^{_OPEN}(?:ال)?رف(?:\s+بتاعي)?$", "shelf"),
    (rf"^(?:{_OPEN})?(?:ال)?حافظ[ةه](?:\s+بتاعت?ي)?$", "clips"),
    (rf"^{_OPEN}(?:ال)?تطبيقات(?:\s+(?:بتاعتي|المثبت[ةه]))?$|^تطبيقاتي$", "apps"),
    (rf"^{_OPEN}(?:اللي\s+فات|ال?سجل)$|^سجل\s+يوبي$", "history"),
    (rf"^(?:{_OPEN})?إعدادات\s+(?:يوبي|ال?جزير[ةه])$|^(?:{_OPEN})?اعدادات\s+(?:يوبي|ال?جزير[ةه])$", "settings"),
]
_PAGE_NAMES = {"prayer": "مواقيت الصلاة", "shelf": "الرف", "clips": "الحافظة", "apps": "التطبيقات",
               "history": "اللي فات", "settings": "إعدادات يوبي"}


def _clean(text):
    t = re.sub(r"[؟?!.،,]+", " ", str(text or "")).strip()
    t = re.sub(r"^(?:يا\s+)?يوبي\s+", "", t)
    return re.sub(r"\s+", " ", t)


def _clock(ms):
    tm = time.localtime(ms / 1000)
    h = tm.tm_hour % 12 or 12
    return f"{h}:{tm.tm_min:02d} {'ص' if tm.tm_hour < 12 else 'م'}".translate(_DIGITS)


def _span(ms):
    m = max(0, round(ms / 60000))
    if m < 1:
        return "دلوقتي"
    h, r = divmod(m, 60)
    parts = ([_count(h, "ساعة", "ساعتين", "ساعات")] if h else []) + ([_count(r, "دقيقة", "دقيقتين", "دقايق")] if r else [])
    return " و".join(parts)


def _count(n, one, two, few):
    """Arabic counting: ساعة، ساعتين، ٣ ساعات، ١١ ساعة"""
    if n == 1:
        return one
    if n == 2:
        return two
    return f"{n} {few if 3 <= n <= 10 else one}".translate(_DIGITS)


def prayer_reply(text, times, now_ms=None):
    """The answer to a question about the prayer times, or None if it isn't one."""
    t = _clean(text)
    now = now_ms if now_ms is not None else time.time() * 1000
    asks_next = re.search(r"ال?صلا[ةه]\s+(?:ال)?(?:جاي[ةه]|الجاي[ةه]|اللي\s+جاي[ةه])|(?:امتى|إمتى|امته)\s+ال?صلا[ةه]", t)
    which = next((k for k, p in _SAY.items()
                  if re.search(rf"(?:^|\s)(?:{p})(?:\s|$)", t)
                  and re.search(r"امتى|إمتى|امته|الساعة\s+كام|الساعه\s+كام|فاضل|باقي|قد\s+[إا]يه|كام\s+دقيق", t)), None)
    if not asks_next and not which:
        return None
    if not times:
        return "لسه مش عارف مواقيت الصلاة، اتأكد من المدينة في إعدادات يوبي"
    if asks_next or which is None:
        key = next((k for k in _ORDER if times.get(k, 0) > now), "fajr")
        at = times[key] if times.get(key, 0) > now else times.get("next_fajr", times["fajr"])
        return f"{_PRAYERS[key]} الساعة {_clock(at)}، فاضل {_span(at - now)}"
    at = times[which]
    if at <= now and which == "fajr" and times.get("next_fajr"):
        at = times["next_fajr"]
    if at <= now:
        return f"{_PRAYERS[which]} النهارده كان الساعة {_clock(at)}، وعدّى من {_span(now - at)}"
    return f"{_PRAYERS[which]} الساعة {_clock(at)}، فاضل {_span(at - now)}"


def page_for(text):
    t = _clean(text)
    for pattern, page in _PAGES:
        if re.search(pattern, t):
            return page
    return None


def match_island_command(text, island):
    """("say", reply) for a prayer question, ("page", page) to open one of the island's pages, else None."""
    if not hasattr(island, "_send"):                 # the old tk island has none of this
        return None
    page = page_for(text)
    if page:
        return ("page", page)
    daily = getattr(island, "_daily", None)
    reply = prayer_reply(text, getattr(daily, "_times", None) if daily is not None else None)
    return ("say", reply) if reply else None


def open_page(island, page):
    """End Yobi's turn quietly, then open the page on the island (it closes by itself if left alone)."""
    island.end_turn()
    island._send({"t": "open", "page": page})
    return f"فتحتلك {_PAGE_NAMES.get(page, page)}"
