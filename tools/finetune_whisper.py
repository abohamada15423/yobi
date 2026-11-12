# -*- coding: utf-8 -*-
"""
درّب Whisper على أوامر يوبي وصوتك، وطلّع موديل يوبي يشغّله بدل الموديل العادي.

    pip install torch transformers ctranslate2
    python tools/make_voice_data.py --n 3000 --noise              داتا متولّدة
    python tools/export_dataset.py --export                       صوتك اللي يوبي سجّله (صحّح true_text)
    python tools/finetune_whisper.py --data voice_data data/export/whisper_review.csv

This is fine-tuning: it starts from a Whisper that already knows Arabic (--base) and teaches
it Yobi's sentences, the names of your apps and games, and - with your own clips - your voice.
A model trained from nothing on generated voices would only know those voices.

--data takes folders with a metadata.csv (file,text: tools/make_voice_data.py, record_clips.py
bench) and whisper_review.csv files from export_dataset.py (rows with an empty true_text are
skipped). Your own clips are the ones that count: generated voices alone teach the names, not
how you say them. One clip in ten is held back and never trained on; the error on those is
printed before and after each round, and the best round is kept.

Needs a graphics card for a small or larger base (minutes per round); on a CPU only --base
openai/whisper-tiny or whisper-base is practical.

Output: models/yobi-whisper/ in the format Yobi runs. Then in config.json:
    "hearing": {"stt_local_model": "models/yobi-whisper", "stt_engine": "local"}
"""
import argparse
import csv
import os
import random
import re
import sys
import wave

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_rows(sources):
    rows = []
    for src in sources:
        if os.path.isdir(src):
            src = os.path.join(src, "metadata.csv")
        if not os.path.exists(src):
            sys.exit(f"مفيش {src}")
        folder = os.path.dirname(src)
        with open(src, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                path = r.get("wav") or os.path.join(folder, r.get("file") or "")
                text = (r.get("true_text") if "true_text" in r else r.get("text") or "").strip()
                if text and os.path.isfile(path):
                    rows.append((path, text))
    return rows


def read_wav(path):
    with wave.open(path) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("not 16 kHz mono 16-bit")
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def norm(t):
    t = re.sub(r"[ً-ْـ،.,!؟?]", "", t.lower())
    t = re.sub("[أإآ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return " ".join(t.split())


def cer(a, b):
    a, b = norm(a), norm(b)
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (ca != cb))
    return d[-1] / max(1, len(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--base", default="openai/whisper-small", help="الموديل اللي نبدأ منه (اسم على Hugging Face أو فولدر)")
    ap.add_argument("--out", default=os.path.join(_ROOT, "models", "yobi-whisper"))
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--max-clips", type=int, default=0, help="جرّب على عدد صغير الأول")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--quantization", default="int8_float16", help="int8 لو هيشتغل على CPU")
    args = ap.parse_args()

    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    rows = load_rows(args.data)
    random.Random(args.seed).shuffle(rows)
    if args.max_clips:
        rows = rows[:args.max_clips]
    if len(rows) < 20:
        sys.exit(f"{len(rows)} مقطع بس — محتاج داتا أكتر")
    n_val = max(5, len(rows) // 10)
    val, train = rows[:n_val], rows[n_val:]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🎧 {len(train)} مقطع تدريب، {len(val)} للاختبار | {args.base} على {device}")

    proc = WhisperProcessor.from_pretrained(args.base, language="arabic", task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(args.base).to(device)
    model.generation_config.language, model.generation_config.task = "arabic", "transcribe"
    model.generation_config.forced_decoder_ids = None
    model.config.forced_decoder_ids = None

    def batch_of(items):
        feats = proc.feature_extractor([read_wav(p) for p, _ in items], sampling_rate=16000, return_tensors="pt")
        lab = proc.tokenizer([t for _, t in items], return_tensors="pt", padding=True)
        labels = lab.input_ids.masked_fill(lab.attention_mask.ne(1), -100)
        if (labels[:, 0] == model.config.decoder_start_token_id).all():
            labels = labels[:, 1:]          # the model adds the start token itself
        return feats.input_features.to(device), labels.to(device)

    @torch.no_grad()
    def evaluate():
        model.eval()
        errs, shown = [], []
        for i in range(0, len(val), args.batch):
            items = val[i:i + args.batch]
            x, _ = batch_of(items)
            ids = model.generate(x, max_new_tokens=64, num_beams=1)
            for (_, want), got in zip(items, proc.batch_decode(ids, skip_special_tokens=True)):
                errs.append(cer(want, got))
                if errs[-1] and len(shown) < 5:
                    shown.append(f"      «{want}» ← «{got.strip()}»")
        return 100 * float(np.mean(errs)), shown

    def save():
        model.save_pretrained(args.out + "-hf")
        proc.save_pretrained(args.out + "-hf")

    best, shown = evaluate()
    print(f"قبل التدريب: حروف غلط {best:.1f}%")
    base_err = best
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * ((len(train) + args.batch - 1) // args.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=0.1, anneal_strategy="linear")
    scaler = torch.amp.GradScaler(enabled=device == "cuda")
    saved, step = False, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        random.Random(args.seed + epoch).shuffle(train)
        total = 0.0
        for i in range(0, len(train), args.batch):
            x, y = batch_of(train[i:i + args.batch])
            with torch.autocast(device_type=device, dtype=torch.float16, enabled=device == "cuda"):
                loss = model(input_features=x, labels=y).loss
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update(); sched.step()
            total += float(loss); step += 1
            if step % 20 == 0:
                print(f"   خطوة {step}/{steps}  loss {total / (i // args.batch + 1):.3f}", flush=True)
        err, shown = evaluate()
        print(f"جولة {epoch}: حروف غلط {err:.1f}% على مقاطع الاختبار")
        print("\n".join(shown))
        if err < best:
            best, saved = err, True
            save()
    if not saved:
        sys.exit(f"التدريب ما حسّنش ({base_err:.1f}% قبل) — مفيش موديل اتحفظ. جرّب داتا أكتر أو --lr أقل")

    import ctranslate2
    has_tok = os.path.isfile(os.path.join(args.out + "-hf", "tokenizer.json"))
    conv = ctranslate2.converters.TransformersConverter(args.out + "-hf", copy_files=["tokenizer.json"] if has_tok else [])
    conv.convert(args.out, quantization=args.quantization, force=True)
    # faster-whisper reads the audio settings (80 or 128 mel bands) from this file
    proc.feature_extractor.to_json_file(os.path.join(args.out, "preprocessor_config.json"))
    print(f"✅ {base_err:.1f}% → {best:.1f}%  |  الموديل في {args.out}")
    print('   config.json →  "hearing": {"stt_local_model": "models/yobi-whisper", "stt_engine": "local"}')


if __name__ == "__main__":
    main()
