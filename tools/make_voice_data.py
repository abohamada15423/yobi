# -*- coding: utf-8 -*-
"""
اعمل داتا صوت لأوامر يوبي من غير ما حد يسجّل: جمل أوامر مصرية بصوت Edge (نفس صوت يوبي).

    python tools/make_voice_data.py --n 400                 400 مقطع في voice_data/
    python tools/make_voice_data.py --n 2000 --noise        ومعاهم نسخ بدوشة أوضة
    python tools/stt_benchmark.py --clips voice_data --engines local --show

Each clip is a command built from a template and a name (an app, a game, a site), said by
one of the Egyptian voices at a random speed, with or without "يا يوبي" first. The name is
*said* the Egyptian way ("ديسكورد") and *written* the way Yobi wants to read it ("Discord").

Output (same layout as tools/record_clips.py bench, so stt_benchmark.py reads it):
    voice_data/*.wav            16 kHz mono
    voice_data/metadata.csv     file,text,spoken,voice,rate

What this data is good for: comparing hearing engines and settings on the same sentences,
and as extra sentences when fine-tuning. What it is not: a replacement for real voices.
Two synthetic voices teach a model those two voices; the clips Yobi records of you
(data/commands, tools/export_dataset.py) are the ones that teach it your voice.
"""
import argparse
import asyncio
import csv
import os
import random
import sys
import wave

import numpy as np

VOICES = ["ar-EG-ShakirNeural", "ar-EG-SalmaNeural"]
RATES = ["-12%", "-5%", "+0%", "+8%", "+18%"]

# said → written
NAMES = {
    "ديسكورد": "Discord", "كروم": "Chrome", "سبوتيفاي": "Spotify", "يوتيوب": "YouTube", "ستيم": "Steam",
    "واتساب": "WhatsApp", "تيليجرام": "Telegram", "فايرفوكس": "Firefox", "إيدج": "Edge", "فيسبوك": "Facebook",
    "تويتر": "Twitter", "انستجرام": "Instagram", "نتفليكس": "Netflix", "تويتش": "Twitch", "جوجل": "Google",
    "فوتوشوب": "Photoshop", "وورد": "Word", "إكسيل": "Excel", "باوربوينت": "PowerPoint", "نوت باد": "Notepad",
    "في إس كود": "VS Code", "أو بي إس": "OBS", "في إل سي": "VLC", "زووم": "Zoom", "تيمز": "Teams",
    "فالورانت": "Valorant", "روكيت ليج": "Rocket League", "ماين كرافت": "Minecraft", "فورتنايت": "Fortnite",
    "ليج أوف ليجندز": "League of Legends", "كاونتر سترايك": "Counter-Strike", "جي تي إيه": "GTA",
    "أبيكس ليجندز": "Apex Legends", "أوفرواتش": "Overwatch", "فيفا": "FIFA", "ببجي": "PUBG",
    "إيبك جيمز": "Epic Games", "كول أوف ديوتي": "Call of Duty", "روبلوكس": "Roblox", "شات جي بي تي": "ChatGPT",
}
WITH_NAME = [
    "افتح {}", "افتحلي {}", "شغل {}", "شغللي {}", "اقفل {}", "اقفللي {}", "عايز افتح {}", "ممكن تفتح {}",
    "افتح {} بسرعة", "شغل {} لو سمحت", "اقفل {} خالص", "افتح موقع {}", "دور على {} في جوجل", "نزل {}",
]
PLAIN = [
    "علي الصوت", "علي الصوت شوية", "وطي الصوت", "وطي الصوت شوية", "اكتم الصوت", "شغل الصوت تاني",
    "الساعة كام دلوقتي", "النهارده كام في الشهر", "مواقيت الصلاة النهارده", "الفجر الساعة كام", "العصر امتى",
    "خد سكرين شوت", "افتح فولدر التحميلات", "افتح المستندات", "افتح الديسكتوب", "اقفل الجهاز", "اقفل الجهاز بعد ساعة",
    "اعمل ريستارت", "نيم الجهاز", "علي الإضاءة", "وطي الإضاءة", "فكرني اشرب مية بعد عشر دقايق",
    "فكرني بالاجتماع بعد نص ساعة", "شغل مؤقت التركيز", "وقف الأغنية", "كمل الأغنية", "الأغنية اللي بعدها",
    "الأغنية اللي قبلها", "ايه اللي شغال دلوقتي", "ايه اللي على الشاشة", "افحص جهازي", "الجو عامل ايه النهارده",
    "ابحث عن اغاني عمرو دياب", "شغل قرآن", "لا مش ده", "أيوه", "خلاص شكرا", "اقترح عليا لعبة",
]


def sentences(rng, n):
    """n (spoken, written) pairs: mostly commands with a name, the rest fixed commands."""
    out = []
    names = list(NAMES.items())
    while len(out) < n:
        if rng.random() < 0.65:
            said, written = rng.choice(names)
            t = rng.choice(WITH_NAME)
            out.append((t.format(said), t.format(written)))
        else:
            s = rng.choice(PLAIN)
            out.append((s, s))
    return out


def to_pcm16k(mp3):
    import miniaudio
    d = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=16000)
    return np.frombuffer(d.samples, dtype=np.int16).copy()


def with_noise(pcm, rng, snr_db):
    """The same clip in a room: steady noise at the given signal-to-noise ratio."""
    x = pcm.astype(np.float32)
    speech = float(np.sqrt(np.mean(x[np.abs(x) > 300] ** 2))) if np.any(np.abs(x) > 300) else 1000.0
    noise = rng.standard_normal(len(x)).astype(np.float32)
    noise = np.convolve(noise, np.ones(8) / 8, mode="same")          # duller than white: fans, a PC
    noise *= speech / (10 ** (snr_db / 20)) / (float(np.sqrt(np.mean(noise ** 2))) or 1.0)
    return np.clip(x + noise, -32768, 32767).astype(np.int16)


def save_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(pcm.tobytes())


async def speak(text, voice, rate, proxy):
    import edge_tts
    buf = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate, proxy=proxy).stream():
        if chunk["type"] == "audio":
            buf += chunk["data"]
    return bytes(buf)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400, help="عدد الجمل")
    ap.add_argument("--out", default="voice_data")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--wake", type=float, default=0.3, help="نسبة الجمل اللي قبلها «يا يوبي»")
    ap.add_argument("--noise", action="store_true", help="نسخة تانية من كل مقطع بدوشة أوضة")
    ap.add_argument("--voices", nargs="+", default=VOICES)
    args = ap.parse_args()

    rng, nrng = random.Random(args.seed), np.random.default_rng(args.seed)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    os.makedirs(args.out, exist_ok=True)
    meta_path = os.path.join(args.out, "metadata.csv")
    done = set()
    if os.path.exists(meta_path):                           # a second run carries on
        with open(meta_path, encoding="utf-8", newline="") as f:
            done = {r["file"] for r in csv.DictReader(f)}
    meta = open(meta_path, "a", encoding="utf-8", newline="")
    out = csv.writer(meta)
    if not done:
        out.writerow(["file", "text", "spoken", "voice", "rate"])

    made = failed = 0
    for i, (said, written) in enumerate(sentences(rng, args.n)):
        voice, rate = rng.choice(args.voices), rng.choice(RATES)
        if rng.random() < args.wake:
            said, written = "يا يوبي، " + said, "يا يوبي " + written
        name = f"s{args.seed}_{i:05d}.wav"
        if name in done:
            continue
        try:
            pcm = to_pcm16k(await speak(said, voice, rate, proxy))
        except Exception as e:
            failed += 1
            print(f"⚠️ {name}: {str(e)[:100]}")
            if failed >= 5 and not made:
                sys.exit("الصوت مش بيتولّد — النت شغال؟ (pip install edge-tts miniaudio)")
            continue
        save_wav(os.path.join(args.out, name), pcm)
        out.writerow([name, written, said, voice, rate])
        if args.noise:
            snr = rng.choice([20, 15, 10])
            noisy = name[:-4] + f"_n{snr}.wav"
            save_wav(os.path.join(args.out, noisy), with_noise(pcm, nrng, snr))
            out.writerow([noisy, written, said, voice, rate])
        made += 1
        if made % 50 == 0:
            meta.flush()
            print(f"… {made} مقطع")
    meta.close()
    print(f"✅ {made} مقطع جديد في {args.out}/ ({len(done)} كانوا موجودين)")


if __name__ == "__main__":
    asyncio.run(main())
