# -*- coding: utf-8 -*-
"""
export_dataset.py — حوّل الأوامر اللي يوبي سجلها لداتا تدريب.

    python tools/export_dataset.py            إحصائيات بس
    python tools/export_dataset.py --export   يطلّع الملفات في data/export/

بيطلّع:
  intent.jsonl       {"text", "intent", "target"}  للأوامر اللي اتأكد إنها صح
                     (correct + corrected) ← لموديل الـ intent الصغير
  whisper_review.csv  wav + اللي Whisper سمعه + اقتراح للنص الصح + عمود فاضي
                     "true_text". افتحه في Excel وصحّح عمود true_text،
                     وبعدها يبقى جاهز لـ fine-tune Whisper.
"""

import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from dataset_recorder import DEFAULT_ROOT, load_records   # noqa: E402

_VERBS = ("اقفل", "قفل", "اغلق", "close", "kill")


def _intent(text):
    t = (text or "").strip().lower()
    return "close" if t.startswith(_VERBS) else "open"


def stats(recs):
    n = len(recs)
    labels = Counter(r.get("label") or "unlabeled" for r in recs.values())
    with_audio = sum(1 for r in recs.values() if r.get("wav"))
    low = sum(1 for r in recs.values() if r.get("low"))
    judged = labels["correct"] + labels["wrong"] + labels["corrected"]
    print(f"أوامر متسجلة: {n}  (بصوت: {with_audio})")
    print(f"  ✅ صح: {labels['correct']}   ❌ غلط: {labels['wrong']}   "
          f"✏️ اتصلحت: {labels['corrected']}   ⬜ من غير لابل: {labels['unlabeled']}")
    if judged:
        print(f"  دقة يوبي الحقيقية في الفتح: {labels['correct'] / judged:.0%} من {judged} أمر")
    print(f"  Whisper مكانش واثق في: {low}")
    bad = Counter(r.get("text") for r in recs.values() if r.get("label") in ("wrong", "corrected"))
    if bad:
        print("  أكتر حاجات بيغلط فيها:")
        for t, c in bad.most_common(8):
            print(f"    {c}× {t}")
    need = max(0, 500 - judged)
    if need:
        print(f"\nمحتاج حوالي {need} أمر كمان عليهم لابل قبل ما تدرب موديل intent.")
    else:
        print("\n🎯 عندك داتا كفاية تبدأ تدرب موديل intent.")


def export(recs, root):
    out = os.path.join(os.path.dirname(root), "export")
    os.makedirs(out, exist_ok=True)
    good = [r for r in recs.values() if r.get("label") in ("correct", "corrected") and r.get("target")]
    with open(os.path.join(out, "intent.jsonl"), "w", encoding="utf-8") as f:
        for r in good:
            text = (r.get("phrases") or [r.get("text")])[0]
            f.write(json.dumps({"text": text, "intent": _intent(text),
                                "target": r["target"]}, ensure_ascii=False) + "\n")
    rows = [r for r in recs.values() if r.get("wav")]
    with open(os.path.join(out, "whisper_review.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wav", "heard", "label", "target", "true_text"])
        for r in sorted(rows, key=lambda r: r.get("ts") or 0):
            w.writerow([os.path.join(root, r["wav"]), r.get("text"), r.get("label") or "",
                        r.get("target") or "", ""])
    print(f"\n📦 intent.jsonl: {len(good)} مثال")
    print(f"📦 whisper_review.csv: {len(rows)} تسجيل → صحّح عمود true_text")
    print(f"   في: {out}")


if __name__ == "__main__":
    root = DEFAULT_ROOT
    recs = load_records(root)
    if not recs:
        print("لسه مفيش أوامر متسجلة. استخدم يوبي شوية وارجع.")
        sys.exit(0)
    stats(recs)
    if "--export" in sys.argv:
        export(recs, root)
