# -*- coding: utf-8 -*-
"""
سجّل عينات صوتك — للنداء وللـ benchmark.

  # 1) ~200 مرة "يا يوبي" + ~120 جملة عادية (negatives) لتدريب النداء
  python tools/record_clips.py wake --positives 200 --negatives 120

  # 2) 40 جملة أوامر بنصها لمقارنة محركات الـ STT
  python tools/record_clips.py bench --n 40

Hands-free: the script listens continuously, cuts every utterance with a
simple energy VAD, saves it as 16 kHz mono WAV and shows the next prompt.
Say "يا يوبي" each time the counter moves. Vary it: near/far, loud/soft,
fast/slow, tired/happy, with music or a fan on — variety is what makes
the wake word robust.

Output:
  wake_data/positive/*.wav   wake_data/negative/*.wav
  bench/*.wav + bench/metadata.csv  (file,text)
"""

import argparse
import csv
import os
import queue
import random
import sys
import time
import wave

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sys.exit("pip install sounddevice")

SR = 16000
FRAME = 480  # 30 ms

WAKE_HINTS = [
    "عادي", "بسرعة", "ببطء", "بصوت واطي", "بصوت عالي", "وإنت بعيد ٢ متر",
    "وإنت بتبتسم", "كأنك تعبان", "وإنت مدّي في «يااا»", "وفي موسيقى شغالة",
    "وإنت ماشي في الأوضة", "بلهجة مستعجلة",
]

NEGATIVE_SENTENCES = [
    "يا يوسف تعالى هنا", "يا بيبي عامل إيه", "اليوبيل الفضي", "يا حبيبي يا جميل",
    "يوجا الصبح حلوة", "يا أبو علي", "هات الريموت", "إنت فين دلوقتي",
    "النهارده الجو حر أوي", "أنا جعان قوي", "افتح الشباك", "يا ولاد بطّلوا دوشة",
    "يوم بيوم", "يا بني آدم", "يو تيوب", "يوبيكا", "يا بوب", "يا روبي",
    "يا هوبا", "بيبو وبشير", "جيبي الشاي", "مين اللي على الباب", "بكرة الجمعة",
    "خلّصت الماتش؟", "الواي فاي فاصل", "هو في إيه", "اسكت شوية", "ماشي يا عم",
]

BENCH_SENTENCES = [
    "افتح سبوتيفاي", "شغل فالورانت", "افتح ديسكورد", "اقفل كروم",
    "علي الصوت شوية", "وطي الصوت", "اكتم الصوت", "شغل أغنية لعمرو دياب",
    "ابحث عن سعر الدولار النهارده", "افتح فولدر التحميلات", "خد سكرين شوت",
    "فكرني أشرب مية بعد ساعة", "افحص جهازي", "ايه اللي شغال دلوقتي",
    "افتح ستيم", "شغل روكت ليج", "افتح يوتيوب", "اقترح لعبة نلعبها",
    "شغل فيلم على نتفليكس", "افتح الإعدادات", "قفل الكمبيوتر بعد نص ساعة",
    "افتح فيجوال ستوديو كود", "ابعت لكريم على ديسكورد", "افتح ماينكرافت",
    "الساعة كام", "إيه الأخبار النهارده", "افتح المستندات", "شغل مزيكا هادية",
    "افتح كاونتر سترايك", "اقفل كل الألعاب", "افتح جوجل كروم على الإيميل",
    "علي السطوع", "افتح الآلة الحاسبة", "افتح أوبس", "شغل البودكاست",
    "اقفل ديسكورد", "افتح ليج أوف ليجندز", "شغل بلاي ليست الصبح",
    "افتح الواتساب", "خلاص شكرا",
]


def save_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.astype(np.int16).tobytes())


class Recorder:
    def __init__(self, device=None):
        self.q = queue.Queue()
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16",
                                     blocksize=FRAME, device=device,
                                     callback=lambda d, f, t, s: self.q.put(d[:, 0].copy()))
        self.stream.start()
        self.floor = self._calibrate()

    def _calibrate(self):
        print("🤫 اسكت ثانيتين عشان أقيس الدوشة...")
        lv = []
        t0 = time.time()
        while time.time() - t0 < 2:
            lv.append(self._rms(self.q.get()))
        floor = float(np.percentile(lv, 30)) if lv else 200.0   # robust if you talk during it
        print(f"   مستوى الدوشة: {floor:.0f}")
        return floor

    @staticmethod
    def _rms(x):
        x = x.astype(np.float32)
        return float(np.sqrt(np.mean(x * x))) if x.size else 0.0

    def utterance(self, max_s=4.0, end_ms=450, pre_ms=240):
        """Wait for one utterance and return it (int16), trimmed + padded."""
        thr = max(350.0, self.floor * 2.6)
        pre = []
        voiced, silent, started = [], 0, False
        while True:
            fr = self.q.get()
            loud = self._rms(fr) > thr
            if not started:
                pre.append(fr)
                pre = pre[-int(pre_ms / 30):]
                if loud:
                    started = True
                    voiced = list(pre)
                continue
            voiced.append(fr)
            silent = 0 if loud else silent + 1
            if silent * 30 >= end_ms or len(voiced) * 30 >= max_s * 1000:
                break
        pcm = np.concatenate(voiced)
        if len(pcm) < SR * 0.25:
            return None
        return np.concatenate([pcm, np.zeros(int(SR * 0.15), np.int16)])


def run_wake(args):
    pos_dir = os.path.join(args.out, "positive")
    neg_dir = os.path.join(args.out, "negative")
    os.makedirs(pos_dir, exist_ok=True)
    os.makedirs(neg_dir, exist_ok=True)
    rec = Recorder(args.device)
    have = len([f for f in os.listdir(pos_dir) if f.endswith(".wav")])
    print(f"\n🎙️ هنسجل «يا يوبي» {args.positives} مرة (عندك {have}). Ctrl+C للإيقاف في أي وقت.\n")
    i = have
    try:
        while i < args.positives:
            hint = WAKE_HINTS[(i // 15) % len(WAKE_HINTS)]
            print(f"[{i + 1}/{args.positives}] قول: «يا يوبي» — {hint}", flush=True)
            pcm = rec.utterance(max_s=2.5)
            if pcm is None:
                print("   قصيرة أوي، تاني")
                continue
            save_wav(os.path.join(pos_dir, f"ya_yobi_{i + 1:04d}.wav"), pcm)
            i += 1
        have_n = len([f for f in os.listdir(neg_dir) if f.endswith(".wav")])
        print(f"\n🙅 دلوقتي {args.negatives} جملة عادية (من غير «يوبي»). اقرا الجملة اللي تظهر.\n")
        j = have_n
        sents = NEGATIVE_SENTENCES[:]
        while j < args.negatives:
            s = random.choice(sents)
            print(f"[{j + 1}/{args.negatives}] اقرا: {s}", flush=True)
            pcm = rec.utterance(max_s=5)
            if pcm is None:
                continue
            save_wav(os.path.join(neg_dir, f"neg_{j + 1:04d}.wav"), pcm)
            j += 1
    except KeyboardInterrupt:
        print("\n⏸️ وقفنا. شغّل نفس الأمر تاني وهيكمل من مكانك.")
    print(f"\n✅ اتسجل: {i} نداء في {pos_dir}")


def run_bench(args):
    os.makedirs(args.out, exist_ok=True)
    meta = os.path.join(args.out, "metadata.csv")
    sents = BENCH_SENTENCES
    if args.sentences:
        with open(args.sentences, encoding="utf-8") as f:
            sents = [l.strip() for l in f if l.strip()]
    sents = sents[:args.n]
    rows = []
    rec = Recorder(args.device)
    print("\n🎙️ اقرا كل جملة زي ما بتكلم يوبي عادي.\n")
    try:
        for k, s in enumerate(sents, 1):
            while True:
                print(f"[{k}/{len(sents)}] {s}", flush=True)
                pcm = rec.utterance(max_s=7)
                if pcm is not None:
                    break
            name = f"clip_{k:03d}.wav"
            save_wav(os.path.join(args.out, name), pcm)
            rows.append((name, s))
    except KeyboardInterrupt:
        print("\n⏸️ وقفنا.")
    new = not os.path.exists(meta)
    with open(meta, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["file", "text"])
        w.writerows(rows)
    print(f"\n✅ {len(rows)} مقطع في {args.out} — شغّل: python tools/stt_benchmark.py --clips {args.out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    w = sub.add_parser("wake")
    w.add_argument("--out", default="wake_data")
    w.add_argument("--positives", type=int, default=200)
    w.add_argument("--negatives", type=int, default=120)
    w.add_argument("--device", default=None)
    b = sub.add_parser("bench")
    b.add_argument("--out", default="bench")
    b.add_argument("--n", type=int, default=40)
    b.add_argument("--sentences", default=None, help="ملف txt جملة في كل سطر")
    b.add_argument("--device", default=None)
    args = ap.parse_args()
    if getattr(args, "device", None) is not None and str(args.device).isdigit():
        args.device = int(args.device)
    run_wake(args) if args.mode == "wake" else run_bench(args)


if __name__ == "__main__":
    main()
