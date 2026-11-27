# -*- coding: utf-8 -*-
"""
Pack the real recordings for train_wake.py: a train/test split as FLAC, zipped in parts small enough
to upload to Colab by hand or from a browser tool (under 9 MB each).

  python tools/wake_training/make_bundle.py            ->  data/colab/wake/real/  +  real_1.zip, real_2.zip, ...

These are private voices: the output folder is under data/, which git ignores. Never commit or publish it.
"""
import argparse
import csv
import glob
import json
import os
import random
import shutil
import zipfile

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def wake_split():
    """Hold out 15% of the wake clips for testing: the same ones on every run (seed 7)."""
    random.seed(7)
    out = {}
    for kind in ("positive", "negative"):
        fs = sorted(glob.glob(os.path.join(ROOT, "wake_data", kind, "*.wav")))
        random.shuffle(fs)
        n = int(len(fs) * 0.15)
        out[kind] = (fs[n:], fs[:n])
    return out


def commands(fires):
    """Speech Yobi recorded after a wake, without the wake word. `fires(path)` is the current model's peak
    score: a short clip it fires on may be a call the transcript missed, and as a negative that would
    teach the model to ignore real calls, so those are left out."""
    base = os.path.join(ROOT, "data", "commands")
    text = {}
    for line in open(os.path.join(base, "log.jsonl"), encoding="utf-8"):
        e = json.loads(line)
        if e.get("ev") == "heard" and e.get("wav"):
            text[e["wav"].replace("\\", "/")] = e.get("text", "")
    meta = os.path.join(base, "metadata.csv")
    if os.path.exists(meta):                                    # hand-checked text wins
        for row in csv.DictReader(open(meta, encoding="utf-8-sig")):
            text[row["file"].replace("\\", "/")] = row["text"]
    keep, dropped = [], 0
    for rel, t in sorted(text.items()):
        p = os.path.join(base, rel)
        if not os.path.exists(p):
            continue
        if "يوب" in t or "yob" in t.lower() or (sf.info(p).duration < 2.5 and fires(p) >= 0.35):
            dropped += 1
            continue
        keep.append(p)
    return keep, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "colab", "wake"))
    ap.add_argument("--wake-model", default=os.path.join(ROOT, "models", "ya_yobi.onnx"))
    ap.add_argument("--part-mb", type=float, default=8.5)
    a = ap.parse_args()

    from openwakeword.model import Model
    m = Model(wakeword_models=[a.wake_model], inference_framework="onnx")

    def fires(path):
        x, _ = sf.read(path, dtype="int16")
        x = np.concatenate([np.zeros(16000, np.int16), x, np.zeros(24000, np.int16)])
        m.reset()
        return max(max(m.predict(x[i:i + 1280]).values()) for i in range(0, len(x) - 1279, 1280))

    wake = wake_split()
    cmds, dropped = commands(fires)
    room = sorted(glob.glob(os.path.join(ROOT, "data", "room_noise", "*.wav")))
    sets = {                                   # folder -> (train files, test files); every 5th file is test
        "positive": wake["positive"],
        "speech": (wake["negative"][0] + [f for i, f in enumerate(cmds) if i % 5], wake["negative"][1] + cmds[::5]),
        "room": ([f for i, f in enumerate(room) if i % 5], room[::5]),
    }
    real = os.path.join(a.out, "real")
    shutil.rmtree(real, ignore_errors=True)
    for name, parts in sets.items():
        for split, fs in zip(("train", "test"), parts):
            d = os.path.join(real, split, name)
            os.makedirs(d)
            for f in fs:
                x, sr = sf.read(f, dtype="int16")
                assert sr == 16000 and x.ndim == 1, f
                sf.write(os.path.join(d, os.path.splitext(os.path.basename(f))[0] + ".flac"), x, sr)
            print(f"{split}/{name}: {len(fs)} clips")
    print(f"commands left out (wake word in them, or short and the model fires): {dropped}")

    for old in glob.glob(os.path.join(a.out, "real_*.zip")):
        os.remove(old)
    part, size, z = 0, 0, None
    for f in sorted(glob.glob(os.path.join(real, "**", "*.flac"), recursive=True)):
        n = os.path.getsize(f)
        if z is None or size + n > a.part_mb * 1e6:
            if z:
                z.close()
            part, size = part + 1, 0
            z = zipfile.ZipFile(os.path.join(a.out, f"real_{part}.zip"), "w", zipfile.ZIP_STORED)
        z.write(f, os.path.relpath(f, a.out))
        size += n
    z.close()
    for p in sorted(glob.glob(os.path.join(a.out, "real_*.zip"))):
        print(os.path.basename(p), f"{os.path.getsize(p) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
