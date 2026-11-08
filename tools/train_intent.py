# -*- coding: utf-8 -*-
"""
train_intent.py — درّب موديل الأوامر على استخدامك الحقيقي.

    python tools/train_intent.py                 درّب واحفظ لو النتيجة كويسة
    python tools/train_intent.py --force         درّب حتى لو الداتا قليلة
    python tools/train_intent.py --try "افتح يوروت روك"   جرّب الموديل المتدرب
    python tools/train_intent.py --min-precision 0.98     أشد (بيسأل الـ LLM أكتر)
"""

import argparse
import json
import os
import random
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import intent_model as im                                   # noqa: E402
from dataset_recorder import DEFAULT_ROOT, load_records     # noqa: E402

MIN_POSITIVES = 150
THRESHOLD_FLOOR = 0.6     # حتى لو الاختبار سهل، منقررش لوحدنا تحت 60%
_OPEN_TEMPLATES = ["افتح {}", "شغل {}", "افتحلي {}", "{}", "عايز افتح {}", "يفتح {}",
                   "open {}", "شغللي {}"]
_CLOSE_TEMPLATES = ["اقفل {}", "قفل {}", "close {}"]
_NONE_SEED = ["علي الصوت", "وطي الصوت", "الساعة كام", "عامل ايه", "شكرا", "خلاص",
              "اسكت", "الجو عامل ايه", "فكرني كمان ساعة", "اعمل سكرين شوت",
              "ايه اللي على الشاشة", "شغل اغنية لعمرو دياب", "دور على ملف", "تمام",
              "لا", "ايوه", "مين انت", "الرام فاضي كام", "اقفل الجهاز", "نام"]


def _canonical_targets(catalog):
    """target بتاع الداتا → display بتاع الـ catalog (عشان "valorant" و"Valorant" يبقوا واحد)."""
    if catalog is None:
        return lambda t: (t or "").strip().lower()
    import target_resolver as tr

    def canon(t):
        r = tr.resolve(catalog, t)
        if r.status == "ok" and r.best is not None:
            return r.best.display.strip().lower()
        return (t or "").strip().lower()
    return canon


def load_catalog():
    try:
        from clean_learning import build_catalog
        cat, _ = build_catalog()
        return cat
    except Exception as e:
        print(f"ℹ️ مش قادر أبني قايمة البرامج ({e}) — من غير أمثلة صناعية")
        return None


def _load_legacy_learned(canon):
    """يقرأ الأوامر المتعلمة من learned_commands.json و learning_data.json."""
    out = []
    lc_path = os.path.join(HERE, "learned_commands.json")
    if os.path.exists(lc_path):
        try:
            with open(lc_path, "r", encoding="utf-8") as f:
                lc = json.load(f)
            for phrase, info in lc.items():
                if isinstance(info, dict) and info.get("target"):
                    out.append((phrase, canon(info["target"]), 1.0))
        except Exception:
            pass

    ld_path = os.path.join(HERE, "learning_data.json")
    if os.path.exists(ld_path):
        try:
            with open(ld_path, "r", encoding="utf-8") as f:
                ld = json.load(f)
            for phrase, info in (ld.get("commands") or {}).items():
                if isinstance(info, dict) and info.get("resolved_to") and info.get("success", 0) >= 1:
                    out.append((phrase, canon(info["resolved_to"]), float(info.get("last_used") or 2.0)))
        except Exception:
            pass
    return out


def build_dataset(recs, catalog, augment=True):
    canon = _canonical_targets(catalog)
    real = _load_legacy_learned(canon)
    for r in sorted(recs.values(), key=lambda r: r.get("ts") or 0):
        text = (r.get("phrases") or [r.get("text")])[0]
        if not text:
            continue
        lab = r.get("label")
        if lab in ("correct", "corrected") and r.get("target"):
            real.append((text, canon(r["target"]), r.get("ts") or 0))
        elif lab is None:
            real.append((text, im.NONE_LABEL, r.get("ts") or 0))
    synth = []
    if augment:
        seen_targets = {y for _, y, _ in real if y != im.NONE_LABEL}
        if catalog is not None:
            for e in catalog.entries:
                d = e.display.strip().lower()
                if d not in seen_targets:
                    continue
                for a in e.aliases:
                    for tpl in random.sample(_OPEN_TEMPLATES, min(3, len(_OPEN_TEMPLATES))):
                        synth.append((tpl.format(a), d))
                    synth.append((random.choice(_CLOSE_TEMPLATES).format(a), d))
        synth += [(t, im.NONE_LABEL) for t in _NONE_SEED]
    return real, synth


def choose_threshold(probs, preds, y_true, min_precision):
    """أصغر threshold يخلّي الدقة ≥ min_precision في المرات اللي الموديل بيقرر فيها."""
    import numpy as np
    best = None
    for th in np.arange(0.30, 0.99, 0.01):
        fire = [(p, y) for pr, p, y in zip(probs, preds, y_true)
                if pr >= th and p != im.NONE_LABEL]
        if len(fire) < 5:
            continue
        prec = sum(p == y for p, y in fire) / len(fire)
        if prec >= min_precision:
            best = (float(th), prec, len(fire))
            break
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-augment", action="store_true")
    ap.add_argument("--min-precision", type=float, default=0.97)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--try", dest="try_text")
    a = ap.parse_args()

    if a.try_text:
        m = im.IntentModel.load()
        if m is None:
            print("مفيش موديل متدرب لسه.")
            return 1
        print(m.predict(a.try_text) or "مش واثق → هيروح للـ LLM", "|", m.top(a.try_text))
        return 0

    try:
        import joblib  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError:
        print("محتاج: pip install scikit-learn joblib")
        return 1

    random.seed(7)
    recs = load_records(a.root)
    catalog = load_catalog()
    real, synth = build_dataset(recs, catalog, augment=not a.no_augment)
    pos = [x for x in real if x[1] != im.NONE_LABEL]
    print(f"داتا حقيقية: {len(pos)} أمر فتح/قفل + {len(real) - len(pos)} أمر تاني"
          f" | صناعية: {len(synth)}")
    if len(pos) < MIN_POSITIVES and not a.force:
        print(f"⏳ محتاج {MIN_POSITIVES} أمر على الأقل عليهم لابل (عندك {len(pos)}). "
              f"كمّل استخدام، أو جرب --force.")
        return 1

    # split بالوقت: الأحدث 20% للاختبار
    cut = int(len(real) * 0.8)
    train_real, test = real[:cut], real[cut:]
    X = [im.normalize(t) for t, _, _ in train_real] + [im.normalize(t) for t, _ in synth]
    y = [l for _, l, _ in train_real] + [l for _, l in synth]
    w = [1.0] * len(train_real) + [0.3] * len(synth)

    t0 = time.time()
    pipe = im.build_pipeline()
    pipe.fit(X, y, clf__sample_weight=w)
    print(f"اتدرب في {time.time() - t0:.1f} ثانية على {len(X)} مثال، {len(set(y))} class")

    threshold, report = 0.8, {}
    if len(test) >= 10:
        Xt = [im.normalize(t) for t, _, _ in test]
        yt = [l for _, l, _ in test]
        P = pipe.predict_proba(Xt)
        preds = [pipe.classes_[i] for i in P.argmax(1)]
        probs = P.max(1)
        acc = sum(p == t for p, t in zip(preds, yt)) / len(yt)
        ch = choose_threshold(probs, preds, yt, a.min_precision)
        test_pos = sum(1 for t in yt if t != im.NONE_LABEL)
        print(f"\n📊 على أحدث {len(test)} أمر: accuracy {acc:.0%}")
        if ch:
            threshold, prec, fired = ch
            if threshold < THRESHOLD_FLOOR:
                threshold = THRESHOLD_FLOOR
                fire = [(p, t) for p, t, pr in zip(preds, yt, probs)
                        if pr >= threshold and p != im.NONE_LABEL]
                fired = len(fire)
                prec = sum(p == t for p, t in fire) / max(1, fired)
            print(f"   threshold {threshold:.2f} → بيقرر لوحده في {fired} من {test_pos} أمر فتح "
                  f"({fired / max(1, test_pos):.0%}) بدقة {prec:.0%}، والباقي للـ LLM")
        else:
            threshold = 0.85
            print(f"   threshold {threshold:.2f}")
        report = {"test_n": len(test), "accuracy": acc}
        Xa = [im.normalize(t) for t, _, _ in real] + [im.normalize(t) for t, _ in synth]
        ya = [l for _, l, _ in real] + [l for _, l in synth]
        wa = [1.0] * len(real) + [0.3] * len(synth)
        pipe = im.build_pipeline()
        pipe.fit(Xa, ya, clf__sample_weight=wa)

    import joblib
    os.makedirs(os.path.dirname(im.MODEL_PATH), exist_ok=True)
    joblib.dump(pipe, im.MODEL_PATH)
    meta = {"threshold": threshold, "trained_at": time.strftime("%Y-%m-%d %H:%M"),
            "n_train": len(real) + len(synth), "n_real_positive": len(pos),
            "classes": [c for c in pipe.classes_ if c != im.NONE_LABEL],
            "min_precision": a.min_precision, **report}
    with open(im.META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"\n✅ اتحفظ في models/intent_model.joblib. شغّل يوبي من الأول عشان يستخدمه.")
    return 0


if __name__ == "__main__":
    sys.exit(main())