# -*- coding: utf-8 -*-
"""
smart_open — الطريقة الوحيدة اللي يوبي بيفتح بيها حاجة من كلامك.

    res = smart_open(agent, name="euro truck simulator 2",
                     utterance="شارف مش عارف اقوله ايه", stt_low=False,
                     choose=ask_buttons, guard=learning_guard)

بيرجّع نص للـ brain/الـ UI:
    "تم تشغيل اللعبة 🎮"            → اتفتحت
    "CANCELLED: ..."                → سألناك وقلت لا
    "ASK: قصدك X ولا Y؟"            → مفيش أزرار (مثلًا شات مكتوب)، الـ LLM يسأل
    "SEARCHED: ..."                 → موقع مش معروف، بحثنا عنه بدل ما نخمّن
    "NOT_FOUND: ..."                → مش لاقي
"""

import difflib
import os
import re
import urllib.parse
import webbrowser

import target_resolver as tr


def _question(opts):
    if len(opts) >= 2:
        return f"قصدك {opts[0].display} ولا {opts[1].display}؟"
    return f"قصدك {opts[0].display}؟"


def _ask_options(res, cfg):
    floor = dict(tr.DEFAULTS, **(cfg or {}))["ask"]
    opts = [e for e, s in res.options if s >= floor][:2]
    if res.best is not None and res.best not in opts:
        opts.insert(0, res.best)
    return opts[:2]


def smart_open(agent, name, utterance=None, stt_low=False, choose=None,
               guard=None, on_opened=None, cfg=None, learn_phrase=None):
    phrase = learn_phrase or utterance or name
    res = agent.resolve(name, utterance=utterance, stt_low=stt_low)

    def _launch(entry, confirmed):
        r = agent.launch(entry)
        if on_opened:
            on_opened(entry.display, r)
        if guard is not None and phrase:
            if confirmed:
                guard.confirm_now(phrase, entry.display, "open")
            else:
                guard.propose(phrase, entry.display, "open", launch=entry.launch)
        return r

    if res.status == "ok":
        return _launch(res.best, confirmed=False)

    if res.status == "ask":
        opts = _ask_options(res, cfg)
        if not opts:
            return f"NOT_FOUND: مش لاقي '{name}' على الجهاز"
        q = _question(opts)
        if choose is None:
            return "ASK: " + q
        buttons = [(e.display, e.id) for e in opts] + [("لا، ولا حاجة", "none")]
        picked = choose(q, buttons)
        entry = next((e for e in opts if e.id == picked), None)
        if entry is None:
            return "CANCELLED: المستخدم قال مش ده، متفتحش حاجة واسأله يقصد إيه"
        return _launch(entry, confirmed=True)

    if res.status == "url":
        q = tr.strip_filler(utterance or "") or tr.url_domain(res.url).split(".")[0]
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(q))
        return (f"SEARCHED: مش متأكد من عنوان الموقع، فبحثتلك عن '{q}' في جوجل. "
                f"لو عايزه يتفتح على طول ضيفه في websites في config.json")

    found = agent.find_on_disk(name) if hasattr(agent, "find_on_disk") else None
    if found and choose is not None:
        label = os.path.splitext(os.path.basename(found))[0]
        picked = choose(f"لقيت {label} على الجهاز، أفتحه؟",
                        [("أيوه افتحه", "yes"), ("لا", "no")])
        if picked == "yes":
            os.startfile(found)   # noqa  (Windows)
            if guard is not None and phrase:
                guard.confirm_now(phrase, found, "open")
            return "لقيتها وفتحتها! 🚀"
        return "CANCELLED: المستخدم قال لا"
    return f"NOT_FOUND: مش لاقي '{name}' على الجهاز"


def exe_matches(name, exe_path, cutoff=0.85):
    """Verify that a discovered .exe genuinely matches `name` (handles both
    full stems and multi-word games like 'euro truck simulator 2' → 'eurotrucks2.exe'
    while rejecting false positives like 'ساكه' → 'SACKE.exe')."""
    stem = re.sub(r"[^a-z0-9]", "", os.path.splitext(os.path.basename(exe_path))[0].lower())
    n = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if len(n) < 4 or not stem:
        return False
    if stem == n or difflib.SequenceMatcher(None, stem, n).ratio() >= cutoff:
        return True
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower())
             if len(w) >= 4 and w not in ("simulator", "edition", "game", "part")]
    if len(words) >= 2 and all(w in stem for w in words[:2]):
        return True
    return False