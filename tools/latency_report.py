# -*- coding: utf-8 -*-
"""
Latency report — قراءة latency_log.csv اللي يوبي بيكتبه.

  python tools/latency_report.py               # كل الأدوار
  python tools/latency_report.py --last 50
"""

import argparse
import csv
import os
import statistics
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGES = [("stt_ms", "STT"), ("llm_first_ms", "LLM أول جملة"), ("tts_ms", "TTS أول صوت"),
          ("total_ms", "الإجمالي (سكوتك → صوته)")]


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def fmt(ms):
    return f"{ms/1000:.2f}s" if ms >= 1000 else f"{ms:.0f}ms"


def table(rows, title):
    print(f"\n{title} ({len(rows)} دور)")
    print("| المرحلة | n | p50 | p90 | أسوأ |")
    print("|---|---|---|---|---|")
    for key, name in STAGES:
        vals = [float(r[key]) for r in rows if r.get(key) not in (None, "", "None")]
        if vals:
            print(f"| {name} | {len(vals)} | {fmt(statistics.median(vals))} | "
                  f"{fmt(pct(vals, .9))} | {fmt(max(vals))} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(_ROOT, "latency_log.csv"))
    ap.add_argument("--last", type=int, default=0)
    args = ap.parse_args()
    if not os.path.exists(args.csv):
        sys.exit(f"مفيش {args.csv} لسه — اتكلم مع يوبي شوية الأول")
    with open(args.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.last:
        rows = rows[-args.last:]
    table(rows, "📊 كل الأدوار")
    for eng in sorted({r["stt_engine"] for r in rows if r["stt_engine"]}):
        table([r for r in rows if r["stt_engine"] == eng], f"🎧 STT = {eng}")
    tot = [float(r["total_ms"]) for r in rows if r.get("total_ms") not in (None, "", "None")]
    if tot:
        ok = sum(1 for v in tot if v <= 1200) / len(tot)
        print(f"\n🎯 هدف الخطة (< 1.2s): {ok*100:.0f}% من الأدوار")


if __name__ == "__main__":
    main()
