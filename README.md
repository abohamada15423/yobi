<div align="center">

<img src="island-tauri/src-tauri/icons/128x128@2x.png" width="110" alt="Yobi">

# يوبي · Yobi

**مساعد صوتي بالمصري للويندوز.** بتكلّمه فيفتح برامجك وألعابك ومواقعك، يتحكم في جهازك، ويرد عليك بصوته.

*An Egyptian Arabic voice assistant for Windows.*

[![تحميل يوبي](https://img.shields.io/badge/%D8%AA%D8%AD%D9%85%D9%8A%D9%84-Yobi--Setup.zip-3CC2B4?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/abohamada15423/yobi/releases/latest/download/Yobi-Setup.zip)

![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?style=flat-square)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Tauri](https://img.shields.io/badge/UI-Tauri%20%2B%20React-E3B04B?style=flat-square&logo=tauri&logoColor=white)
[![Release](https://img.shields.io/github/v/release/abohamada15423/yobi?style=flat-square&color=3CC2B4)](https://github.com/abohamada15423/yobi/releases/latest)

<br>

<img src="docs/screenshots/panel.png" width="400" alt="الجزيرة مفتوحة">

</div>

---

## يعمل إيه

| | |
|---|---|
| 🎙️ **بتكلّمه عادي** | «يا يوبي افتح ديسكورد»، «علّي الصوت»، «شغّل يوتيوب». بيفهم المصري ولو الكلمة اتنطقت غلط. |
| 🎮 **يعرف جهازك** | بيلاقي البرامج والألعاب (Steam وغيره) والمواقع اللي في المتصفح لوحده من أول تشغيل. |
| 🏝️ **جزيرة فوق الشاشة** | شريط صغير بيوريك الساعة والطقس والأغنية الشغالة والتحميلات، ويكبر لما تحتاجه. |
| 🕌 **الصلاة والأذكار** | مواعيد الصلاة لمدينتك، تنبيه قبل الأذان، أذكار وآيات خفيفة طول اليوم. |
| ⏱️ **تركيز واجتماعات** | مؤقّت تركيز، وتنبيه قبل اجتماعاتك من Google Calendar أو Outlook. |
| 👁️ **بيشوف الشاشة** | اسأله «إيه اللي على الشاشة؟» أو علّمه مهمة يعيدها بعدين (محتاج مفتاح Gemini). |
| 🔌 **من غير نت** | من غير مفتاح ولا إنترنت بينفّذ الأوامر الأساسية بموديل صغير على جهازك. |

<div align="center">
<img src="docs/screenshots/music.png" width="300" alt="الموسيقى">
&nbsp;
<img src="docs/screenshots/question.png" width="420" alt="يوبي بيسأل">
<br>
<img src="docs/screenshots/prayer.png" width="420" alt="تنبيه الصلاة">
</div>

---

## التثبيت

1. نزّل **[Yobi-Setup.zip](https://github.com/abohamada15423/yobi/releases/latest/download/Yobi-Setup.zip)** (حوالي 270 MB).
2. فك الضغط، ودوس مرتين على **`Install Yobi.cmd`**. مش محتاج صلاحيات أدمن.
3. أول مرة هيطلب **مفتاح Gemini المجاني** — الخطوات مكتوبة في `README.txt` جوه الملف. أو دوس «كمّل من غير مفتاح» للأوامر بس.

> [!NOTE]
> ويندوز ممكن يطلّع تحذير SmartScreen عشان البرنامج مش موقّع. دوس **More info** وبعدين **Run anyway**.

## إزاي تكلّمه

- قول **«يا يوبي»** وبعدها الأمر، أو دوس **`Ctrl + Alt + Y`** وكلّمه.
- عايز زرار تاني؟ الإعدادات ← **الاختصار والشاشة** ← **زرار النداء**، ودوس أي زرار تختاره (مثلاً `F8`).
- النداء بالصوت متدرّب على صوت واحد، فلو مش بيسمعك كويس خلّيه بالزرار بس من نفس المكان.

## المتطلبات

- Windows 10 أو 11 (64-bit) ومايك.
- حوالي 700 MB مساحة.
- مفتاح [Gemini](https://aistudio.google.com/apikey) مجاني للدردشة وشوف الشاشة (اختياري).

## إزالة يوبي

من **Settings ← Apps** دوّر على Yobi ودوس Uninstall. بياناتك بتتمسح معاه.

---

<details>
<summary><b>للمطورين</b></summary>

<br>

```bash
pip install -r requirements.txt
copy config.example.json config.json
copy .env.example .env
python agent.py
```

الجزيرة (Tauri) محتاجة Node و Rust:

```bash
cd island-tauri
npm install
npx tauri build
```

| الفولدر | فيه إيه |
|---|---|
| `*.py` | يوبي نفسه: `agent.py` البداية، `brain.py` و `local_brain.py` الفهم، `audio_input.py` و `stt_engine.py` و `tts_engine.py` الصوت |
| `island-tauri/` | الجزيرة والإعدادات (React + Tauri) |
| `packaging/` | بناء `Yobi-Setup.zip` والتثبيت |
| `tests/` | الاختبارات: `python tests/test_<name>.py` |
| `tools/` | سكريبتات تدريب وقياس |

بناء ملف التثبيت: `python packaging/build.py` (بعد بناء الجزيرة).

</details>
