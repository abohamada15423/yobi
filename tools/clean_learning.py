# -*- coding: utf-8 -*-
"""
clean_learning.py — نضّف اللي يوبي اتعلمه غلط قبل v7. شغّله مرة واحدة:

    python tools/clean_learning.py            # يوريك هيمسح إيه بس (dry run)
    python tools/clean_learning.py --apply    # يمسح فعلًا (وبياخد backup الأول)
"""

import json
import os
import shutil
import sys
import time

import target_resolver as tr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Yobi's folder
sys.path.insert(0, HERE)


def _load(name, default):
    try:
        with open(os.path.join(HERE, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(name, data):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _sane(name):
    """'50% of the audience.' و'if the hell.' مش أسماء برامج."""
    n = (name or "").strip()
    if len(n) < 3 or n.endswith((".", "?", "!")) or "%" in n:
        return False
    return len(n.split()) <= 5


def build_catalog():
    cfg = _load("config.json", {})
    apps = _load("installed_apps_cache.json", {})
    scan = _load("smart_scan_cache.json", {})
    games = {g: f"game:{g}" for g in (scan.get("games") or []) if isinstance(g, str)}
    full = False
    try:
        from game_scanner import scan_all_games
        found = scan_all_games() or {}
        games.update(found)
        full = sys.platform.startswith("win") and len(found) > 0
        try:
            from launcher_discovery import scan_all_other_launchers
            games.update(scan_all_other_launchers() or {})
        except Exception:
            pass
    except Exception:
        pass
    local = (cfg.get("local_apps") or {}).get("windows", {})
    return tr.Catalog(cfg.get("websites") or {}, local, games, apps), full


def target_ok(cat, target, full=True, phrase=None):
    if not target or not isinstance(target, str) or not _sane(target):
        return False
    if tr.is_url(target):
        return tr.url_domain(target) in cat.site_domains
    r = tr.resolve(cat, target)
    if r.status == "ok" and r.score >= 0.9:
        return True
    t = target.lower().strip()
    if phrase and tr.strip_filler(phrase) == tr.strip_filler(t):
        return False
    if not any("a" <= ch <= "z" for ch in t):
        return False
    return not full


SEED_FIXES = {
    "يوروت روك": "يورو ترك",
    "سبوتيفويل": "سبوتيفاي",
    "زبوتيفويل": "سبوتيفاي",
    "سبوتي فورب": "سبوتيفاي",
    "السبوت فوي": "سبوتيفاي",
    "ليجو في اللجنس": "ليج اوف ليجندز",
    "فرزو رايزن": "فورزا هورايزن",
    "venerant": "valorant",
    "رايت كلين": "رايوت كلاينت",
    "الرايوت كلاين": "رايوت كلاينت",
    "júru": "يورو ترك",
    "juru": "يورو ترك",
    "lúl": "لول",
    "lúlí": "لول",
    "ديس كود": "ديسكورد",
}

SPOKEN = {
    "league of legends": "ليج اوف ليجندز",
    "valorant": "فالورانت",
    "rocket league": "روكيت ليج",
    "euro truck simulator 2": "يورو ترك",
    "forza horizon": "فورزا هورايزن",
    "assetto corsa competizione": "اسيتو كورسا",
    "grand theft auto v": "جراند",
    "the last of us": "ذا لاست اوف اس",
    "minecraft": "ماين كرافت",
    "overwatch": "اوفر واتش",
    "elden ring": "الدن رينج",
    "celeste": "سيليست",
    "discord": "ديسكورد",
    "spotify": "سبوتيفاي",
    "riot client": "رايوت كلاينت",
    "youtube": "يوتيوب",
    "netflix": "نتفليكس",
    "teamfight tactics": "تيم فايت تاكتيكس",
}


def main(apply):
    cat, full = build_catalog()
    if not full:
        print("ℹ️ مش قادر أعمل scan للألعاب هنا، فهسيب الأسماء الإنجليزي اللي مش متأكد منها.")
    report = []

    lc = _load("learned_commands.json", {})
    keep_lc = {k: v for k, v in lc.items()
               if target_ok(cat, (v or {}).get("target"), full, phrase=k)}
    report.append(("learned_commands.json", lc, keep_lc,
                   lambda k, v: f"{k} → {v.get('target')}"))

    ld = _load("learning_data.json", {"commands": {}, "corrections": {}, "pending": []})
    cmds = ld.get("commands", {})
    keep_cmds = {k: v for k, v in cmds.items()
                 if v.get("resolved_to") is None
                 or target_ok(cat, v.get("resolved_to"), full, phrase=k)}
    report.append(("learning_data.json", cmds, keep_cmds,
                   lambda k, v: f"{k} → {v.get('resolved_to')}"))

    up = _load("usage_patterns.json", {})
    keep_up = {k: v for k, v in up.items() if target_ok(cat, k, full) and _sane(k)}
    report.append(("usage_patterns.json", up, keep_up, lambda k, v: k))

    vocab = _load("vocab.json", {"friends": [], "extra": [], "fixes": {}, "usage": {}})
    usage = vocab.get("usage", {})
    keep_usage = {}
    for k, v in usage.items():
        if target_ok(cat, k, full) and _sane(k):
            kl = k.lower().strip()
            keep_usage[kl] = keep_usage.get(kl, 0) + int(v)
    report.append(("vocab.json usage", usage, keep_usage, lambda k, v: k))

    for name, before, after, fmt in report:
        gone = [k for k in before if k not in after and k.lower().strip() not in after]
        print(f"\n── {name}: هيتمسح {len(gone)} من {len(before)}")
        for k in gone:
            print("   ✗", fmt(k, before[k]))

    have = {e.display.lower() for e in cat.entries}
    extra = list(vocab.get("extra") or [])
    for en, ar in SPOKEN.items():
        if (any(h.startswith(en) for h in have) or en in ("euro truck simulator 2", "forza horizon")) and ar not in extra:
            extra.append(ar)
    fixes = dict(vocab.get("fixes") or {})
    for w, r in SEED_FIXES.items():
        fixes.setdefault(w, r)
    print(f"\n── vocab.json: هضيف {len(extra) - len(vocab.get('extra') or [])} اسم بالنطق المصري "
          f"و{len(fixes) - len(vocab.get('fixes') or {})} تصحيح سمع")

    if not apply:
        print("\n(ده dry run. شغّل `python tools/clean_learning.py --apply` عشان يتنفذ)")
        return

    bdir = os.path.join(HERE, "backups", time.strftime("pre_v7_%Y%m%d_%H%M%S"))
    os.makedirs(bdir, exist_ok=True)
    for f in ("learned_commands.json", "learning_data.json", "usage_patterns.json", "vocab.json"):
        if os.path.exists(os.path.join(HERE, f)):
            shutil.copy2(os.path.join(HERE, f), bdir)
    _save("learned_commands.json", keep_lc)
    ld["commands"] = keep_cmds
    _save("learning_data.json", ld)
    _save("usage_patterns.json", keep_up)
    vocab.update(usage=keep_usage, extra=extra, fixes=fixes)
    _save("vocab.json", vocab)
    print(f"\n✅ اتنضف. الـ backup في {bdir}")


if __name__ == "__main__":
    main("--apply" in sys.argv)