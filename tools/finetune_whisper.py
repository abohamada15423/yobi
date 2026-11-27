# -*- coding: utf-8 -*-
"""
درّب Whisper على أوامر يوبي وصوتك، وطلّع موديل يوبي يشغّله بدل الموديل العادي.

    pip install torch transformers ctranslate2
    python tools/make_voice_data.py --n 3000 --noise              داتا متولّدة
    python tools/export_dataset.py --export                       صوتك اللي يوبي سجّله (صحّح true_text)
    python tools/label_recordings.py my_recordings                تسجيلات عندك من غير نصوص (راجع النص)
    python tools/finetune_whisper.py --data voice_data --real my_recordings data/export/whisper_review.csv

This is fine-tuning: it starts from a Whisper that already knows Arabic (--base) and teaches
it Yobi's sentences, the names of your apps and games, and - with your own clips - your voice.
A model trained from nothing on generated voices would only know those voices.

--data and --real take folders with a metadata.csv (file,text: tools/make_voice_data.py,
record_clips.py bench) and whisper_review.csv files from export_dataset.py (rows with an empty
true_text are skipped). Clips can be wav, mp3, m4a, ogg... at any sample rate.

--real is for clips of real people (you, your friends). They are the ones that count:
generated voices teach the names, not how people say them. So with --real, the clips held
back for testing are real ones only (one in five, never trained on), and each real clip left
for training is used --real-weight times (3) so a few hundred aren't lost among thousands of
generated ones. Without --real, one clip in ten of --data is held back. The error on the
held-back clips is printed before training and after each round, and the best round is kept.

--noise is for clips where nobody speaks (the room, a fan): their text is nothing. Without them
a model that was shown many wake calls writes the wake call for anything unclear. A fifth is held
back with made noise, and "noise heard as words" is printed next to the error and counted in it.

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


def load_rows(sources, empty=False):
    """(path, text) of every clip that has a text; empty=True is for noise, whose text is nothing."""
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
                if (text or empty) and os.path.isfile(path):
                    rows.append((path, "" if empty else text))
    return rows


def made_noise(n, seed):
    """n clips of nothing said: silence, hiss and hum at many levels, 1 to 5 seconds."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        x = rng.standard_normal(int(rng.uniform(1, 5) * 16000)).astype(np.float32)
        if rng.random() < 0.6:                                   # duller than white: fans, a PC
            x = np.convolve(x, np.ones(int(rng.integers(2, 40))) / 8, mode="same")
        x *= 10 ** rng.uniform(-4, -1) / (float(np.abs(x).max()) or 1.0) * float(rng.random() > 0.1)
        out.append((x.astype(np.float32), ""))
    return out


def read_wav(path):
    """Any audio file as 16 kHz mono float32 (the generated clips are read directly)."""
    if not isinstance(path, str):
        return path
    try:
        with wave.open(path) as w:
            if w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2:
                return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    except (wave.Error, EOFError):
        pass
    from faster_whisper.audio import decode_audio
    return decode_audio(path, sampling_rate=16000)


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
    ap.add_argument("--data", nargs="+", default=[], help="مقاطع متولّدة")
    ap.add_argument("--real", nargs="+", default=[], help="تسجيلات ناس حقيقية: الاختبار منها هي بس")
    ap.add_argument("--real-weight", type=int, default=3)
    ap.add_argument("--noise", nargs="+", default=[], help="مقاطع مفيهاش كلام (دوشة الأوضة): نصها فاضي")
    ap.add_argument("--wake-text", default="يا يوبي", help="التسجيل الحقيقي اللي نصه كده بيتستخدم مرة واحدة")
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

    rows, real = load_rows(args.data), load_rows(args.real)
    random.Random(args.seed).shuffle(rows)
    random.Random(args.seed).shuffle(real)
    if args.max_clips:
        rows, real = rows[:args.max_clips], real[:args.max_clips]
    if len(rows) + len(real) < 20:
        sys.exit(f"{len(rows) + len(real)} مقطع بس — محتاج داتا أكتر")
    if real:
        n_val = max(5, len(real) // 5)
        # the wake call once: hundreds of copies of one short phrase teach the model to write it for anything unclear
        val, train = real[:n_val], rows + [r for r in real[n_val:] for _ in range(
            1 if norm(r[1]) == norm(args.wake_text) else max(1, args.real_weight))]
        print(f"🎙️ {len(real)} تسجيل حقيقي: {n_val} للاختبار، والباقي في التدريب ×{args.real_weight} («{args.wake_text}» مرة واحدة)")
    else:
        n_val = max(5, len(rows) // 10)
        val, train = rows[:n_val], rows[n_val:]
    # nothing said → nothing written. Held back: a fifth of the room clips and made noise of another seed
    room = load_rows(args.noise, empty=True)
    random.Random(args.seed).shuffle(room)
    quiet_val = room[:len(room) // 5] + made_noise(30, args.seed + 1000) if room else []
    if room:
        train += room[len(room) // 5:] * 10 + made_noise(len(train) // 10, args.seed)
        print(f"🤫 {len(room)} مقطع دوشة حقيقي ({len(room) // 5} للاختبار) + دوشة متولّدة")
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
        heard = wake = 0                       # noise that came out as words, and as the wake call
        for i in range(0, len(quiet_val), args.batch):
            ids = model.generate(batch_of(quiet_val[i:i + args.batch])[0], max_new_tokens=64, num_beams=1)
            for got in proc.batch_decode(ids, skip_special_tokens=True):
                heard += bool(norm(got))
                wake += norm(args.wake_text) in norm(got)
        err = 100 * float(np.mean(errs))
        if quiet_val:
            shown.append(f"      دوشة اتسمعت كلام: {heard}/{len(quiet_val)} ({wake} «{args.wake_text}»)")
            # one number to pick the best round by: letters wrong on speech + noise heard as speech
            return err + 100 * heard / len(quiet_val), shown
        return err, shown

    def save():
        model.save_pretrained(args.out + "-hf")
        proc.save_pretrained(args.out + "-hf")

    best, shown = evaluate()
    what = "حروف غلط" + (" + دوشة اتسمعت كلام" if quiet_val else "")
    print(f"قبل التدريب: {what} {best:.1f}%")
    print("\n".join(shown[-1:] if quiet_val else []))
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
        print(f"جولة {epoch}: {what} {err:.1f}% على مقاطع الاختبار")
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
