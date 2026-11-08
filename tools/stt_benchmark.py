# -*- coding: utf-8 -*-
"""
STT benchmark — مين أسرع وأدق في المصري: Groq ولا الـ GPU بتاعك؟

  python tools/record_clips.py bench --n 40          # سجّل جمل بنصها
  python tools/stt_benchmark.py --clips bench        # قارن

Engines (any subset with --engines):
  groq-turbo   Groq whisper-large-v3-turbo
  groq-v3      Groq whisper-large-v3
  local        faster-whisper (default large-v3-turbo on cuda float16)

Metrics per engine: WER, CER (after Arabic normalisation: hamza/alef/ya/
ta-marbuta/diacritics), latency p50/p90 and real-time factor. The local
model is warmed up on the first clip (not counted). With --vocab the same
personal prompt Yobi uses is sent, so you measure the real setup.

Writes <clips>/stt_results.json and prints the config line to use.
"""

import argparse
import csv
import io
import json
import os
import statistics
import sys
import time
import wave

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabic_text import cer, normalize_ar, wer  # noqa: E402

GROQ = {"groq-turbo": "whisper-large-v3-turbo", "groq-v3": "whisper-large-v3"}


def load_clips(folder):
    meta = os.path.join(folder, "metadata.csv")
    if not os.path.exists(meta):
        sys.exit(f"مفيش {meta} — سجّل الأول: python tools/record_clips.py bench")
    out = []
    with open(meta, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            p = os.path.join(folder, row["file"])
            if os.path.exists(p):
                with open(p, "rb") as w:
                    data = w.read()
                with wave.open(io.BytesIO(data)) as wf:
                    dur = wf.getnframes() / wf.getframerate()
                out.append({"file": row["file"], "text": row["text"], "wav": data, "dur": dur})
    return out


def build_prompt(use_vocab):
    base = ("أوامر عربي/إنجليزي: افتح، اقفل، علي/وطي الصوت، شغل، "
            "ابحث عن، اقترح، افحص جهازي، فكرني، علم نفسك إن.")
    if not use_vocab:
        return base
    try:
        from vocab import PersonalVocab
        targets = []
        cache = os.path.join(_ROOT, "installed_apps_cache.json")
        if os.path.exists(cache):
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
            targets = list(data.keys()) if isinstance(data, dict) else []
        v = PersonalVocab(targets_source=lambda: targets)
        return v.prompt(base=base)
    except Exception as e:
        print(f"⚠️ vocab: {e}")
        return base


def make_engine(name, args):
    if name in GROQ:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(_ROOT, ".env"))
        except Exception:
            pass
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

        def run(wav, prompt):
            r = client.audio.transcriptions.create(
                file=("clip.wav", wav), model=GROQ[name], prompt=prompt,
                language="ar", temperature=0.0)
            return r.text
        return run
    if name == "local":
        from faster_whisper import WhisperModel
        model = WhisperModel(args.local_model, device=args.device, compute_type=args.compute)

        def run(wav, prompt):
            kw = dict(language="ar", beam_size=args.beam, vad_filter=True,
                      initial_prompt=prompt or None, condition_on_previous_text=False)
            if args.hotwords:
                kw["hotwords"] = args.hotwords
            segs, _ = model.transcribe(io.BytesIO(wav), **kw)
            return "".join(s.text for s in segs)
        return run
    raise SystemExit(f"engine غير معروف: {name}")


def pctl(vals, p):
    v = sorted(vals)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))] if v else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default="bench")
    ap.add_argument("--engines", nargs="+", default=["groq-turbo", "groq-v3", "local"])
    ap.add_argument("--local-model", default="large-v3-turbo")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute", default="float16")
    ap.add_argument("--beam", type=int, default=1)
    ap.add_argument("--vocab", action="store_true", help="استخدم نفس prompt يوبي الشخصي")
    ap.add_argument("--hotwords", default=None)
    ap.add_argument("--show", action="store_true", help="اطبع كل جملة")
    args = ap.parse_args()

    clips = load_clips(args.clips)
    if not clips:
        sys.exit("مفيش مقاطع")
    prompt = build_prompt(args.vocab)
    print(f"🎧 {len(clips)} مقطع | prompt {len(prompt)} حرف\n")

    results = {}
    for name in args.engines:
        try:
            run = make_engine(name, args)
        except Exception as e:
            print(f"⚠️ {name}: مش متاح ({str(e)[:100]})")
            continue
        if name == "local":
            try:
                run(clips[0]["wav"], prompt)   # warm-up
            except Exception as e:
                print(f"⚠️ local warm-up: {e}")
        lat, w_, c_, rtf, errs = [], [], [], [], 0
        rows = []
        for c in clips:
            t0 = time.perf_counter()
            try:
                hyp = run(c["wav"], prompt)
            except Exception as e:
                errs += 1
                hyp = ""
                print(f"  ⚠️ {name} {c['file']}: {str(e)[:80]}")
            dt = time.perf_counter() - t0
            lat.append(dt * 1000)
            rtf.append(dt / max(0.1, c["dur"]))
            w_.append(wer(c["text"], hyp))
            c_.append(cer(c["text"], hyp))
            rows.append({"file": c["file"], "ref": c["text"], "hyp": hyp, "ms": round(dt * 1000)})
            if args.show:
                mark = "✅" if normalize_ar(hyp) == normalize_ar(c["text"]) else "❌"
                print(f"  {mark} [{name}] {c['text']}  →  {hyp.strip()}")
        results[name] = {
            "wer": statistics.mean(w_), "cer": statistics.mean(c_),
            "exact": sum(1 for r in rows if normalize_ar(r["hyp"]) == normalize_ar(r["ref"])) / len(rows),
            "p50_ms": statistics.median(lat), "p90_ms": pctl(lat, 0.9),
            "rtf": statistics.mean(rtf), "errors": errs, "rows": rows,
        }

    if not results:
        sys.exit("ولا محرك اشتغل")
    print("\n| المحرك | WER | CER | مطابق 100% | p50 | p90 | RTF |")
    print("|---|---|---|---|---|---|---|")
    for n, r in results.items():
        print(f"| {n} | {r['wer']*100:.1f}% | {r['cer']*100:.1f}% | {r['exact']*100:.0f}% | "
              f"{r['p50_ms']:.0f}ms | {r['p90_ms']:.0f}ms | {r['rtf']:.2f} |")

    # pick: lowest CER; if within 1.5 points, the faster one wins
    ranked = sorted(results.items(), key=lambda kv: kv[1]["cer"])
    best_name, best = ranked[0]
    for n, r in ranked[1:]:
        if r["cer"] - best["cer"] <= 0.015 and r["p50_ms"] < best["p50_ms"] * 0.8:
            best_name, best = n, r
    order = [best_name] + [n for n, _ in ranked if n != best_name]
    if "local" not in order:
        order.append("local")
    print(f"\n🏆 الأنسب ليك: {best_name} (CER {best['cer']*100:.1f}%, p50 {best['p50_ms']:.0f}ms)")
    print('   حطه في config.json →  "hearing": {"stt_engine": "auto", "stt_order": '
          + json.dumps(order) + "}")
    out = os.path.join(args.clips, "stt_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"prompt": prompt, "results": results, "recommended_order": order},
                  f, ensure_ascii=False, indent=2)
    print(f"   التفاصيل: {out}")


if __name__ == "__main__":
    main()
