# -*- coding: utf-8 -*-
"""
AEC check — هل يوبي فعلًا مش سامع نفسه؟

  python tools/aec_check.py              # 8 ثواني اختبار
  python tools/aec_check.py --sweep      # جرّب delays مختلفة واختار الأحسن

Plays a speech-like test signal through the AudioEngine (exactly how Yobi
talks) and measures how much of it reaches the mic before and after echo
cancellation (ERLE, dB). Keep the room quiet and the speaker volume where
you normally use it. Don't talk during the test.

    ≥ 25 dB  ممتاز — full-duplex (تقاطعه بالكلام العادي) هيشتغل كويس
    15–25    كويس
    < 15     ضعيف — جرّب --sweep، وطّي الصوت، أو بعّد المايك عن السماعة
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio_io  # noqa: E402


def speech_like(seconds=6.0, sr=48000, seed=1):
    """Syllable-rate modulated harmonic noise — close enough to a voice."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    f0 = 140 + 30 * np.sin(2 * np.pi * 0.7 * t)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    voiced = sum(np.sin(k * phase) / k for k in range(1, 14))
    noise = rng.standard_normal(n) * 0.25
    env = (0.5 + 0.5 * np.sin(2 * np.pi * 4.2 * t)) ** 2 * (rng.random(n // 4800 + 1).repeat(4800)[:n] > 0.25)
    y = (voiced * 0.6 + noise) * env
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.5
    return (y * 32767).astype(np.int16), sr


def measure(eng, seconds):
    raw, clean = [], []
    eng.subscribe(lambda f, t: raw.append(f.copy()), raw=True)
    eng.subscribe(lambda f, t: clean.append(f.copy()))
    time.sleep(1.0)
    raw.clear()
    clean.clear()
    pcm, sr = speech_like(seconds)
    eng.play(pcm, sr)
    time.sleep(0.3)
    r = np.concatenate(raw).astype(np.float32) if raw else np.zeros(1)
    c = np.concatenate(clean).astype(np.float32) if clean else np.zeros(1)
    skip = int(1.5 * 16000)                    # give AEC time to converge
    n = min(len(r), len(c))
    r, c = r[skip:n], c[skip:n]
    er = float(np.mean(r * r)) + 1.0
    ec = float(np.mean(c * c)) + 1.0
    return 10 * np.log10(er / ec), 10 * np.log10(er)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--input-device", default=None)
    ap.add_argument("--output-device", default=None)
    args = ap.parse_args()
    dev = lambda d: int(d) if d is not None and str(d).isdigit() else d

    if not audio_io._HAS_APM:
        sys.exit("❌ مفيش WebRTC APM — اعمل: pip install livekit")

    delays = [0, 40, 80, 120, 180, 250] if args.sweep else [0]
    best = None
    for d in delays:
        eng = audio_io.AudioEngine(aec=True, noise_suppression=False,
                                   input_device=dev(args.input_device),
                                   output_device=dev(args.output_device), extra_delay_ms=d)
        try:
            erle, level = measure(eng, args.seconds)
        finally:
            eng.close()
        print(f"extra_delay {d:>3} ms → إلغاء الصدى {erle:5.1f} dB  (مستوى الصدى الخام {level:.0f} dB)")
        if level < 35:
            print("   ⚠️ المايك مش سامع السماعة تقريبًا — ارفع الصوت أو ده معناه إنك على سماعة رأس (ممتاز)")
        if best is None or erle > best[1]:
            best = (d, erle)
        time.sleep(0.5)
    d, erle = best
    verdict = "ممتاز ✅" if erle >= 25 else "كويس 👍" if erle >= 15 else "ضعيف ⚠️"
    print(f"\nالنتيجة: {erle:.1f} dB — {verdict}")
    if args.sweep and d:
        print(f'حط في config.json →  "hearing": {{"aec_extra_delay_ms": {d}}}')
    if erle < 15:
        print('لو فضل ضعيف: خليه "barge_in": "wake" (المقاطعة بالنداء بس).')


if __name__ == "__main__":
    main()
