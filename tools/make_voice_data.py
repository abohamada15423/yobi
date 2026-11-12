# -*- coding: utf-8 -*-
"""
اعمل داتا صوت لأوامر يوبي من غير ما حد يسجّل: جمل أوامر مصرية بصوت Edge (نفس صوت يوبي).

    python tools/make_voice_data.py --n 400                 400 مقطع في voice_data/
    python tools/make_voice_data.py --n 2500 --noise        ومعاهم نسخ بدوشة أوضة
    python tools/make_voice_data.py --n 2500 --apps installed_apps_cache.json    بأسماء برامجك إنت
    python tools/stt_benchmark.py --clips voice_data --engines local --show

Each clip is a command built from a template and a name (an app, a game, a site), or an
everyday sentence, said by one of Edge's 32 Arabic voices (the two Egyptian ones half the
time) at a random speed and pitch, with or without "يا يوبي" first. The name is *said* the
Egyptian way ("ديسكورد") and *written* the way Yobi wants to read it ("Discord"); a name
from --apps that has no Arabic spelling here is read as it is written.

Output (same layout as tools/record_clips.py bench, so stt_benchmark.py reads it):
    voice_data/*.wav            16 kHz mono
    voice_data/metadata.csv     file,text,spoken,voice,rate

What this data is good for: comparing hearing engines and settings on the same sentences,
and as extra sentences when fine-tuning. What it is not: a replacement for real voices.
Synthetic voices teach a model the sentences and the names; the clips Yobi records of you
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

EGYPTIAN = ["ar-EG-ShakirNeural", "ar-EG-SalmaNeural"]
OTHERS = [f"ar-{c}-{n}Neural" for c, names in {
    "SA": "Hamed Zariyah", "AE": "Hamdan Fatima", "JO": "Taim Sana", "LB": "Rami Layla", "SY": "Laith Amany",
    "IQ": "Bassel Rana", "KW": "Fahed Noura", "QA": "Moaz Amal", "BH": "Ali Laila", "OM": "Abdullah Aysha",
    "YE": "Saleh Maryam", "LY": "Omar Iman", "TN": "Hedi Reem", "DZ": "Ismael Amina", "MA": "Jamal Mouna",
}.items() for n in names.split()]
RATES = ["-15%", "-8%", "-3%", "+0%", "+6%", "+12%", "+20%"]
PITCHES = ["-12Hz", "-6Hz", "+0Hz", "+0Hz", "+6Hz", "+12Hz"]

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
    "افتحلي {} بقى", "يلا شغل {}", "عايز العب {}", "هات {}", "افتح {} تاني", "اقفل {} دلوقتي", "شغل {} على طول",
    "ممكن تقفل {}", "ادخل على {}", "افتح {} وعلي الصوت", "اقفل {} وافتح {}", "لا أقصد {}", "علم نفسك إن {} يعني {}",
]
# everyday talk, so a model trained on this still hears a question or a chat, not only commands
TALK = [
    "عامل ايه النهارده", "احكيلي نكتة", "انت مين", "تقدر تعمل ايه", "ايه رأيك في اللعبة دي", "انا زهقان اعمل ايه",
    "عايز اتعلم برمجة ابدأ منين", "ايه احسن لعبة العبها مع صحابي", "ليه الجهاز بطيء كده", "ازاي اسرع النت عندي",
    "ترجملي الكلمة دي", "اكتبلي رسالة لصاحبي", "ايه اخبار الماتش امبارح", "مين كسب الدوري السنة اللي فاتت",
    "عايز اكلة سهلة اعملها", "صحيني الساعة سبعة الصبح", "انا تعبان وعايز انام", "شكرا يا يوبي تسلم",
    "مش فاهم قصدك ايه", "قول تاني كده", "استنى شوية", "خلاص مش عايز حاجة", "كمل اللي كنت بتقوله", "ايه الجديد النهارده",
    "فاضل كام على رمضان", "كام في كام يساوي كام", "اشرحلي ده ببساطة", "هو ده صح ولا غلط", "طب وبعدين", "تمام كده حلو",
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


def load_apps(path):
    """Names from a file: a text file with a name on each line, or a JSON list or dict of names
    (Yobi's installed_apps_cache.json). They are said as written."""
    import json
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        data = json.loads(raw)
        found = list(data) if isinstance(data, (list, dict)) else []
    except ValueError:
        found = raw.splitlines()
    known = {w.lower() for w in NAMES.values()}
    out = []
    for name in found:
        name = " ".join(str(name).split())
        if 2 <= len(name) <= 30 and name.lower() not in known and not any(ch in name for ch in "\\/:{}"):
            known.add(name.lower())
            out.append((name, name))
    return out


def sentences(rng, n, extra=()):
    """n (spoken, written) pairs: mostly commands with a name, then fixed commands, then talk."""
    out = []
    names = list(NAMES.items()) + list(extra)
    while len(out) < n:
        r = rng.random()
        if r < 0.6:
            t = rng.choice(WITH_NAME)
            picked = rng.sample(names, t.count("{}"))
            if t.startswith("علم نفسك"):            # "X means Y": the same thing said and written
                picked = [(picked[0][0], picked[0][0]), (picked[1][0], picked[1][1])]
            out.append((t.format(*[p[0] for p in picked]), t.format(*[p[1] for p in picked])))
        else:
            s = rng.choice(PLAIN if r < 0.85 else TALK)
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


async def speak(text, voice, rate, pitch, proxy):
    import edge_tts
    buf = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, proxy=proxy).stream():
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
    ap.add_argument("--voices", nargs="+", default=None, help="أصوات معينة بس (الافتراضي: الـ 32 صوت عربي)")
    ap.add_argument("--apps", default=None, help="ملف فيه أسماء برامجك (سطر لكل اسم، أو installed_apps_cache.json)")
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
        out.writerow(["file", "text", "spoken", "voice", "rate", "pitch"])
    extra = load_apps(args.apps) if args.apps else []
    if extra:
        print(f"📋 {len(extra)} اسم من {args.apps}")

    made = failed = 0
    for i, (said, written) in enumerate(sentences(rng, args.n, extra)):
        voice = rng.choice(args.voices) if args.voices else rng.choice(EGYPTIAN if rng.random() < 0.5 else OTHERS)
        rate, pitch = rng.choice(RATES), rng.choice(PITCHES)
        if rng.random() < args.wake:
            said, written = "يا يوبي، " + said, "يا يوبي " + written
        name = f"s{args.seed}_{i:05d}.wav"
        if name in done:
            continue
        try:
            pcm = to_pcm16k(await speak(said, voice, rate, pitch, proxy))
        except Exception as e:
            failed += 1
            print(f"⚠️ {name}: {str(e)[:100]}")
            if failed >= 5 and not made:
                sys.exit("الصوت مش بيتولّد — النت شغال؟ (pip install edge-tts miniaudio)")
            continue
        save_wav(os.path.join(args.out, name), pcm)
        out.writerow([name, written, said, voice, rate, pitch])
        if args.noise:
            snr = rng.choice([20, 15, 10])
            noisy = name[:-4] + f"_n{snr}.wav"
            save_wav(os.path.join(args.out, noisy), with_noise(pcm, nrng, snr))
            out.writerow([noisy, written, said, voice, rate, pitch])
        made += 1
        if made % 50 == 0:
            meta.flush()
            print(f"… {made} مقطع")
    meta.close()
    print(f"✅ {made} مقطع جديد في {args.out}/ ({len(done)} كانوا موجودين)")


if __name__ == "__main__":
    asyncio.run(main())
