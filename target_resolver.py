# -*- coding: utf-8 -*-
"""
Target resolver: بيحوّل كلامك ("افتح يورو ترك") لبرنامج أو لعبة أو موقع موجود فعلًا.

القديم كان بيعمل fuzzy بـ cutoff 0.6 وبيقبل أي كلمة مشتركة ("of"، "the")،
فكان بيفتح حاجات غلط. هنا:
  • كل اسم بيتقارن بطريقتين: النص نفسه + "هيكل صوتي" (consonant skeleton)
    بيخلّي "يورو ترك" و"euro truck" يطلعوا نفس الحاجة.
  • القرار ليه 3 حالات: ok (افتح على طول)، ask (اسأل الأول)، none (مش لاقي).
  • لو الـ LLM اختار اسم مش موجود في كلامك أصلًا (grounding)، يوبي يسأل بدل ما ينفذ.

Pure Python، مفيش Windows ولا Groq، فيتجرب بسهولة (tests/test_resolver.py).
"""

import difflib
import re
import urllib.parse

try:
    from aliases import ARABIC_TO_CANONICAL, normalize_name
except Exception:  # pragma: no cover
    ARABIC_TO_CANONICAL = {}

    def normalize_name(s):
        return re.sub(r"\s+", " ", (s or "").lower()).strip()


# ── thresholds (ممكن تتغير من config.json → "resolver") ──────────────
DEFAULTS = {
    "accept": 0.86,        # أعلى من كده = افتح على طول
    "ask": 0.70,           # بين ask و accept = اسأل "قصدك X؟"
    "margin": 0.07,        # لو الأول والتاني قريبين من بعض = اسأل
    "grounding": 0.55,     # الاسم اللي الـ LLM اختاره لازم يشبه كلامك بالقدر ده
}

# حاجات متسطبة بس عمرك ما هتفتحها بصوتك
_JUNK_RE = re.compile(
    r"(runtime|redistributable|redist|\bsdk\b|driver|\bupdate\b|webview|"
    r"container|vanguard|hidhide|frameview|install application|uninstall|"
    r"helper|\bservice\b|steamworks common|artbook|adventure guide|soundtrack|"
    r"\bost\b|bonjour|vigem|\.net|visual c\+\+|java \d|python \d|"
    r"administrative tools|anti-virus|total security|nvidia)", re.I)

_VERSION_RE = re.compile(
    r"(\(?\b(x64|x86|64-bit|32-bit|64bit|32bit|user|machine)\b\)?|"
    r"\bversion\b|\bv?\d+(\.\d+){1,}\b|\(\s*\)|[™®©])", re.I)

# كلمات بنشيلها من الكلام قبل المقارنة
_FILLER = {
    "افتح", "افتحلي", "افتحي", "فتح", "وفتح", "يفتح", "افتحها", "افتحه",
    "شغل", "شغّل", "شغلي", "شغللي", "وشغل", "اشغل", "اقفل", "قفل", "اغلق",
    "لي", "ليا", "يا", "يوبي", "يايوبي", "لو", "سمحت", "ممكن", "عايز",
    "عاوز", "نفتح", "لعبة", "لعبه", "اللعبة", "اللعبه", "برنامج", "البرنامج",
    "موقع", "الموقع", "تطبيق", "التطبيق", "على", "علي", "من", "فضلك",
    "open", "start", "launch", "run", "play", "please", "close", "app",
    "game", "the", "yobi",
}
_REFERENCE_WORDS = ("تاني", "تانى", "نفس", "افتحها", "افتحه", "شغلها", "شغله",
                    "هي", "هو", "دي", "ده", "اللي قبل", "again", "it")

# أسماء شائعة مش موجودة في aliases.py (إنجليزي مختصر + نطق مصري)
EXTRA_ALIASES = {
    "lol": "league of legends", "ال او ال": "league of legends",
    "tft": "teamfight tactics", "valo": "valorant", "gta": "grand theft auto v",
    "gta 5": "grand theft auto v", "cs": "counter-strike", "ets": "euro truck simulator",
    "ets2": "euro truck simulator", "يورو": "euro truck simulator",
    "euro": "euro truck simulator", "juru": "euro truck simulator",
    "يورو ترك": "euro truck simulator", "يوروت روك": "euro truck simulator",
    "يورو تراك": "euro truck simulator", "يورو تراك سيميوليتور": "euro truck simulator",
    "اسيتو": "assetto corsa competizione", "اسيتو كورسا": "assetto corsa competizione",
    "فورزا": "forza horizon", "فورزا هورايزن": "forza horizon",
    "فورزا هورايزون": "forza horizon", "ويتشر": "the witcher",
    "ذا ويتشر": "the witcher", "الدن رينج": "elden ring", "ايلدن رينج": "elden ring",
    "امونج اس": "among us", "أمونج أس": "among us", "سيليست": "celeste",
    "تيم فايت": "teamfight tactics", "رايوت": "riot client", "رايت كلاينت": "riot client",
    "ستيم": "steam", "ايبك": "epic games launcher", "ابيك": "epic games launcher",
    "كروم": "google chrome", "بريف": "brave", "ايدج": "microsoft edge",
    "في اس كود": "visual studio code", "فيجوال ستوديو كود": "visual studio code",
    "واتساب": "whatsapp", "واتس": "whatsapp", "الواتس": "whatsapp",
    "تيليجرام": "telegram", "نتفليكس": "netflix",
    "ورد": "word", "وورد": "word", "اكسل": "excel", "اكسيل": "excel",
    "باوربوينت": "powerpoint", "باور بوينت": "powerpoint",
}

# أجزاء من أسماء الألعاب ممكن تتشال ونطلع alias أقصر
_DROPPABLE_TAIL = {"simulator", "launcher", "client", "game", "edition",
                   "remastered", "online", "definitive", "deluxe", "part", "i",
                   "ii", "iii", "2", "3", "4", "5", "6"}


# ── phonetic skeleton ─────────────────────────────────────────────────
_AR_MAP = {
    "ب": "b", "ت": "t", "ث": "s", "ج": "k", "ح": "h", "خ": "k", "د": "d",
    "ذ": "s", "ر": "r", "ز": "s", "س": "s", "ش": "x", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "s", "غ": "k", "ف": "f", "ق": "k", "ك": "k", "ل": "l",
    "م": "m", "ن": "n", "ه": "h", "ة": "", "پ": "b", "ڤ": "f", "گ": "k",
}
_LAT_MULTI = [("tch", "x"), ("sch", "x"), ("sh", "x"), ("ch", "x"),
              ("th", "s"), ("ph", "f"), ("ck", "k"), ("qu", "k"), ("x", "ks"),
              ("ce", "se"), ("ci", "si"), ("cy", "sy")]
_LAT_MAP = {"b": "b", "p": "b", "c": "k", "d": "d", "f": "f", "v": "f",
            "g": "k", "j": "k", "k": "k", "q": "k", "h": "h", "l": "l",
            "m": "m", "n": "n", "r": "r", "s": "s", "z": "s", "t": "t"}


def skeleton(text):
    """'يورو ترك' → 'rtrk' ، 'Euro Truck' → 'rtrk'. حروف العلة بتتشال."""
    t = (text or "").lower()
    for a, b in _LAT_MULTI:
        t = t.replace(a, b)
    out = []
    for ch in t:
        if ch in _AR_MAP:
            out.append(_AR_MAP[ch])
        elif ch in _LAT_MAP:
            out.append(_LAT_MAP[ch])
        elif ch == "x":
            out.append("x")
        elif ch.isdigit():
            out.append(ch)
    s = "".join(out)
    s = re.sub(r"(.)\1+", r"\1", s)          # ll → l
    s = re.sub(r"^h", "", s)                  # h في الأول غالبًا صامتة
    return s


def _ratio(a, b, floor=0.6):
    """SequenceMatcher.ratio مع تخطي سريع لما النتيجة أكيد أقل من floor."""
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    if 2.0 * min(la, lb) / (la + lb) < floor:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b)
    if sm.quick_ratio() < floor:
        return 0.0
    return sm.ratio()


def clean_name(name):
    s = normalize_name(name)
    s = _VERSION_RE.sub(" ", s)
    s = re.sub(r"[^\w\s\u0600-\u06FF+]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_filler(text):
    t = normalize_name(text)
    t = re.sub(r"[،,.!؟?\"'«»:;()\[\]]+", " ", t)
    words = []
    for w in t.split():
        if w in _FILLER:
            continue
        # "وفيسبوك" → "فيسبوك"، "والديسكورد" → "ديسكورد"
        if len(w) > 3 and w[0] == "و" and w[1:] not in _FILLER:
            w2 = w[1:]
            if w2.startswith("ال") and len(w2) > 4:
                w2 = w2[2:]
            words.append(w2)
            continue
        if w.startswith("ال") and len(w) > 4:
            words.append(w[2:])
            continue
        words.append(w)
    return " ".join(words)


def is_url(s):
    return bool(re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", (s or "").strip()))


def url_domain(s):
    s = s.strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    host = urllib.parse.urlparse(s).netloc.lower()
    return host[4:] if host.startswith("www.") else host


# ── catalog ────────────────────────────────────────────────────────────
class Entry:
    __slots__ = ("id", "kind", "key", "display", "aliases", "launch")

    def __init__(self, kind, key, launch):
        self.kind = kind            # site | app | game | installed
        self.key = key              # original dict key (for launching)
        self.launch = launch
        self.display = key
        self.aliases = set()
        self.id = f"{kind}:{key}"

    def __repr__(self):
        return f"<{self.kind} {self.display}>"


class Catalog:
    _KIND_ORDER = {"game": 0, "app": 1, "installed": 2, "site": 3}

    def __init__(self, websites=None, local_apps=None, games=None, installed=None):
        self.entries = []
        self._by_launch = {}
        self.site_domains = set()
        for kind, d in (("game", games), ("app", local_apps),
                        ("installed", installed), ("site", websites)):
            for key, launch in (d or {}).items():
                self._add(kind, key, launch)
        self._add_arabic_aliases()
        self._add_short_aliases()
        self._index()

    def _add(self, kind, key, launch):
        if not key or not isinstance(key, str) or key.startswith("__"):
            return
        if kind in ("installed", "game") and _JUNK_RE.search(key):
            return
        if kind == "site" and isinstance(launch, str):
            dom = url_domain(launch)
            if dom and "." in dom:
                self.site_domains.add(dom)
        sig = (kind if kind == "site" else "local", repr(launch).lower())
        e = self._by_launch.get(sig)
        if e is None:
            e = Entry(kind, key, launch)
            self._by_launch[sig] = e
            self.entries.append(e)
        cn = clean_name(key)
        if cn:
            e.aliases.add(cn)
            # "الحاسبة" ↔ "حاسبة" (strip_filler بيشيل "ال" من الكلام)
            if cn.startswith("ال") and len(cn) > 4:
                e.aliases.add(cn[2:])
        # الاسم اللي يتعرض: أول اسم إنجليزي
        if re.search(r"[a-z]", key.lower()) and not re.search(r"[a-z]", e.display.lower()):
            e.display = key

    def _add_arabic_aliases(self):
        merged = dict(ARABIC_TO_CANONICAL)
        merged.update(EXTRA_ALIASES)
        for ar, canon in merged.items():
            c = clean_name(canon)
            for e in self.entries:
                if any(a == c or (len(c) >= 4 and a.startswith(c)) for a in e.aliases):
                    e.aliases.add(clean_name(ar))

    def _add_short_aliases(self):
        for e in self.entries:
            for a in list(e.aliases):
                words = a.split()
                while len(words) > 1 and words[-1] in _DROPPABLE_TAIL:
                    words = words[:-1]
                    e.aliases.add(" ".join(words))
                if len(words) >= 3:
                    e.aliases.add(" ".join(words[:2]))

    def _index(self):
        self._alias_rows = []
        for e in self.entries:
            for a in e.aliases:
                self._alias_rows.append((a, skeleton(a), e))

    def display_names(self, limit=150, prefer=None):
        prefer = [p.lower() for p in (prefer or [])]
        rank = {p: i for i, p in enumerate(prefer)}
        es = sorted(self.entries, key=lambda e: (rank.get(e.display.lower(), 999),
                                                  self._KIND_ORDER.get(e.kind, 9)))
        out, seen = [], set()
        for e in es:
            if e.display.lower() not in seen:
                seen.add(e.display.lower())
                out.append(e.display)
        return out[:limit]

    # ── scoring ──
    @staticmethod
    def _score_pair(span, span_sk, alias, alias_sk):
        if span == alias:
            return 1.0
        raw = _ratio(span, alias)
        if len(span_sk) >= 3 and len(alias_sk) >= 3:
            sk = _ratio(span_sk, alias_sk)
            if span_sk == alias_sk:
                sk = 0.97 if len(alias_sk) >= 4 else 0.9
        else:
            # هيكل قصير (حرفين) ضعيف كدليل: "اكاري" و"kooora" الاتنين "kr"
            sk = 0.6 if (span_sk and span_sk == alias_sk) else 0.0
        return max(raw, sk * 0.97)

    def score_all(self, text, max_window=5):
        """{entry: best score} لكل entry ضد أحسن جزء من الكلام."""
        q = strip_filler(text)
        words = q.split()
        if not words:
            return {}
        spans = []
        for n in range(1, min(max_window, len(words)) + 1):
            for i in range(len(words) - n + 1):
                sp = " ".join(words[i:i + n])
                spans.append((sp, skeleton(sp), n))
        best = {}
        for alias, alias_sk, e in self._alias_rows:
            for sp, sp_sk, n in spans:
                # كلمة واحدة قصيرة ميصحش تطابق اسم طويل
                if n == 1 and len(sp) <= 2:
                    continue
                s = self._score_pair(sp, sp_sk, alias, alias_sk)
                if s >= 0.9 and n > 1:
                    s += 0.08 * (n - 1)   # "يوتيوب ميوزك" تكسب على "يوتيوب"
                if s > best.get(e, 0.0):
                    best[e] = s
        return best

    def rank(self, text, top=3):
        best = self.score_all(text)
        ranked = sorted(best.items(), key=lambda kv: (-round(kv[1], 3),
                                                      self._KIND_ORDER.get(kv[0].kind, 9)))
        # نفس الحاجة متسجلة كذا مرة (لعبة + برنامج متسطب + موقع) → واحدة بس،
        # والأولوية للحاجة اللي على الجهاز
        kept = []
        for e, sc in ranked:
            if any(e.aliases & k.aliases for k, _ in kept):
                continue
            kept.append((e, sc))
            if len(kept) >= top:
                break
        return kept


# ── decision ───────────────────────────────────────────────────────────
class Resolution:
    def __init__(self, status, best=None, score=0.0, options=None, reason="", url=None):
        self.status = status          # ok | ask | none | url
        self.best = best
        self.score = score
        self.options = options or []  # [(entry, score)]
        self.reason = reason
        self.url = url

    def __repr__(self):
        return f"<Resolution {self.status} {self.best} {self.score:.2f} {self.reason}>"


def _has_reference(utt):
    u = normalize_name(utt)
    return any(re.search(rf"(?:^|\s){re.escape(w)}(?:\s|$)", u) for w in _REFERENCE_WORDS)


def resolve(catalog, name, utterance=None, stt_low=False, cfg=None):
    """name: اللي الـ LLM (أو الـ parser) اختاره. utterance: كلامك الأصلي.

    الحالات:
      ok   → افتح best على طول
      ask  → اسأل "قصدك options[0] ولا options[1]؟"
      url  → موقع مش معروف: الأأمن نبحث عنه بدل ما نخمّن الدومين
      none → مش لاقي
    """
    c = dict(DEFAULTS)
    c.update(cfg or {})
    name = (name or "").strip()
    utterance = (utterance or "").strip()
    if not name and not utterance:
        return Resolution("none", reason="empty")

    # 1. URL
    if name and is_url(name):
        dom = url_domain(name)
        for e in catalog.entries:
            if e.kind == "site" and isinstance(e.launch, str) and url_domain(e.launch) == dom:
                return _ground(catalog, e, 1.0, [(e, 1.0)], utterance, stt_low, c)
        # الـ LLM ألّف دومين (playvalorant.com بدل لعبة Valorant). جرّب كلامك نفسه الأول
        if utterance:
            r2 = resolve(catalog, utterance, utterance=utterance, stt_low=stt_low, cfg=cfg)
            if r2.status in ("ok", "ask"):
                return r2
        return Resolution("url", url=name, reason="unknown domain")

    ranked = catalog.rank(name or utterance)
    if not ranked:
        return Resolution("none", reason="no candidates")
    best, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0

    if score < c["ask"]:
        return Resolution("none", score=score, options=ranked, reason="low score")
    if score < c["accept"] or (score - second) < c["margin"] and second >= c["ask"]:
        return Resolution("ask", best, score, ranked, reason="unsure/ambiguous")
    return _ground(catalog, best, score, ranked, utterance, stt_low, c)


def _ground(catalog, best, score, ranked, utterance, stt_low, c):
    if stt_low:
        return Resolution("ask", best, score, ranked, reason="low stt confidence")
    if utterance and not _has_reference(utterance):
        u_scores = catalog.score_all(utterance)
        u = u_scores.get(best, 0.0)
        if u < c["grounding"]:
            # الـ LLM اختار حاجة مش موجودة في كلامك (زي "شارف مش عارف" → Euro Truck)
            return Resolution("ask", best, score, ranked, reason=f"not grounded ({u:.2f})")
    return Resolution("ok", best, score, ranked)


# ── STT text sanity ────────────────────────────────────────────────────
_CYRILLIC_ETC = re.compile(r"[\u0400-\u04FF\u0590-\u05FF\u0900-\u097F\u3040-\u30FF\u4E00-\u9FFF]")
_ACCENTED = re.compile(r"[à-ÿĀ-ž]", re.I)


def text_looks_garbled(text):
    """'шагал инстаграм' ، 'ufta hlúl' ، 'mmm, ahí está' → True."""
    t = text or ""
    if _CYRILLIC_ETC.search(t):
        return True
    if _ACCENTED.search(t):
        return True
    return False