# -*- coding: utf-8 -*-
"""
Merge your real recordings into openWakeWord's training folders.

Run AFTER `train.py --generate_clips` and BEFORE `--augment_clips`:

  python merge_real_voice.py --data wake_data --out my_custom_model/ya_yobi

Positives are copied 3× into positive_train (real voice matters most) and
15% go to positive_test; negatives go to negative_train/negative_test.
Clips are resampled to 16 kHz mono if needed.
"""

import argparse
import glob
import os
import random
import shutil
import wave

import numpy as np


def ensure_16k(src, dst):
    with wave.open(src, "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = w.readframes(w.getnframes())
    if (sr, ch, sw) == (16000, 1, 2):
        shutil.copy(src, dst)
        return
    x = np.frombuffer(data, dtype=np.int16 if sw == 2 else np.int32).astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    n = int(len(x) * 16000 / sr)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    with wave.open(dst, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.clip(y, -32768, 32767).astype(np.int16).tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="wake_data")
    ap.add_argument("--out", default="my_custom_model/ya_yobi")
    ap.add_argument("--dup", type=int, default=3)
    ap.add_argument("--test", type=float, default=0.15)
    args = ap.parse_args()
    random.seed(7)
    for kind in ("positive", "negative"):
        files = sorted(glob.glob(os.path.join(args.data, kind, "*.wav")))
        random.shuffle(files)
        n_test = int(len(files) * args.test)
        tr_dir = os.path.join(args.out, f"{kind}_train")
        te_dir = os.path.join(args.out, f"{kind}_test")
        os.makedirs(tr_dir, exist_ok=True)
        os.makedirs(te_dir, exist_ok=True)
        for i, f in enumerate(files):
            base = os.path.splitext(os.path.basename(f))[0]
            if i < n_test:
                ensure_16k(f, os.path.join(te_dir, f"real_{base}.wav"))
            else:
                for k in range(args.dup if kind == "positive" else 1):
                    ensure_16k(f, os.path.join(tr_dir, f"real_{base}_{k}.wav"))
        print(f"{kind}: {len(files) - n_test} train (×{args.dup if kind == 'positive' else 1}), {n_test} test")


if __name__ == "__main__":
    main()
