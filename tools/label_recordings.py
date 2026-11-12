# -*- coding: utf-8 -*-
"""
اكتب نص كل تسجيل في فولدر، عشان التدريب يعرف يستخدمه.

    python tools/label_recordings.py my_recordings
    (افتح my_recordings/metadata.csv في Excel وصحّح عمود text، وامسح سطر أي مقطع بايظ)
    python tools/finetune_whisper.py --data voice_data --real my_recordings

Training needs the words said in every clip. This walks a folder of recordings (wav, mp3, m4a,
ogg... in any subfolders), writes a first guess for each one with Whisper, and saves
metadata.csv (file,text,sure) inside the folder. The guess is a draft: a model trained on wrong
text learns the mistakes, so read the text column and fix it. Rows are sorted least sure first,
so the ones most likely to be wrong are at the top.

Clips whose file or folder name says they are the wake call (--wake-names: positive, wake,
yobi, نداء) get «يا يوبي» without listening. Running again keeps the rows already written
(and your corrections) and only adds new clips.
"""
import argparse
import csv
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

AUDIO = (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma", ".mp4", ".webm", ".amr", ".3gp")
HINT = ("أوامر عربي/إنجليزي: افتح، اقفل، علي/وطي الصوت، شغل، "
        "Chrome, Spotify, Discord, YouTube, WhatsApp, Steam, يا يوبي")


def find_clips(folder):
    out = []
    for base, _, files in os.walk(folder):
        for name in sorted(files):
            if name.lower().endswith(AUDIO):
                out.append(os.path.relpath(os.path.join(base, name), folder).replace("\\", "/"))
    return sorted(out)


def load_model(name, device):
    from faster_whisper import WhisperModel
    import numpy as np
    if device != "cpu":
        try:
            m = WhisperModel(name, device="cuda", compute_type="float16")
            list(m.transcribe(np.zeros(8000, dtype=np.float32), language="ar", beam_size=1)[0])
            return m, name
        except Exception as e:
            if device == "cuda":
                sys.exit(f"كارت الشاشة مش شغال: {str(e)[:120]}")
            print(f"⚠️ كارت الشاشة مش متاح ({str(e)[:80]}) — هشتغل على الـ CPU بموديل small (أبطأ وأقل دقة)")
            name = "small" if "large" in name else name
    return WhisperModel(name, device="cpu", compute_type="int8"), name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="فولدر التسجيلات")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--wake-names", nargs="*", default=["positive", "wake", "yobi", "نداء"],
                    help="مقطع اسمه أو اسم فولدره فيه كلمة من دول = «يا يوبي»")
    ap.add_argument("--wake-text", default="يا يوبي")
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        sys.exit(f"مفيش فولدر {args.folder}")
    meta = os.path.join(args.folder, "metadata.csv")
    rows = {}
    if os.path.exists(meta):
        with open(meta, encoding="utf-8-sig", newline="") as f:
            rows = {r["file"]: r for r in csv.DictReader(f) if r.get("file")}
    clips = find_clips(args.folder)
    todo = [c for c in clips if c not in rows]
    if not clips:
        sys.exit(f"مفيش ملفات صوت في {args.folder}")
    print(f"🎧 {len(clips)} تسجيل، {len(todo)} محتاجين نص")

    def write():
        ordered = sorted(rows.values(), key=lambda r: float(r.get("sure") or 1))
        with open(meta, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["file", "text", "sure"], extrasaction="ignore")
            w.writeheader()
            w.writerows(ordered)

    listen = []
    for c in todo:
        if any(k and k.lower() in c.lower() for k in args.wake_names):
            rows[c] = {"file": c, "text": args.wake_text, "sure": "1.00"}
        else:
            listen.append(c)
    if listen:
        try:
            from vocab import PersonalVocab
            vocab = PersonalVocab()
            prompt, hot = vocab.prompt(base=HINT), vocab.hotwords()
        except Exception:
            prompt, hot = HINT, ""
        model, name = load_model(args.model, args.device)
        print(f"   بسمع {len(listen)} مقطع بـ {name}...")
        empty = 0
        for i, c in enumerate(listen, 1):
            try:
                segs, _ = model.transcribe(os.path.join(args.folder, c), language="ar", beam_size=5,
                                           vad_filter=True, initial_prompt=prompt,
                                           hotwords=hot or None, condition_on_previous_text=False)
                segs = list(segs)
            except Exception as e:
                print(f"   ⚠️ {c}: {str(e)[:80]}")
                continue
            text = " ".join(s.text.strip() for s in segs).strip()
            sure = min((2.718281828 ** s.avg_logprob for s in segs), default=0.0)
            empty += not text
            rows[c] = {"file": c, "text": text, "sure": f"{sure:.2f}"}
            if i % 20 == 0 or i == len(listen):
                print(f"   {i}/{len(listen)}", flush=True)
                write()
        if empty:
            print(f"   {empty} مقطع ماطلعش فيه كلام (نصه فاضي): اكتب نصه بإيدك أو سيبه فاضي وهيتساب في التدريب")
    write()
    wake = sum(r["text"] == args.wake_text for r in rows.values())
    print(f"✅ {meta}: {len(rows)} سطر ({wake} «{args.wake_text}»)")
    print("   راجع عمود text وصحّحه (الأقل ثقة فوق)، وبعدين:")
    print(f"   python tools/finetune_whisper.py --data voice_data --real {args.folder}")


if __name__ == "__main__":
    main()
