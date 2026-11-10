# Yobi — يوبي

مساعد صوتي عربي (مصري) للويندوز: بتكلّمه فيفتح برامجك وألعابك ومواقعك، يتحكم في الصوت، ويرد عليك.

## التحميل

1. نزّل **Yobi-Setup.zip** من صفحة [Releases](https://github.com/abohamada15423/yobi/releases/latest).
2. فك الضغط، ودوس مرتين على **Install Yobi.cmd** (من غير صلاحيات أدمن).
3. أول مرة هيطلب مفتاح Gemini المجاني — الخطوات في `README.txt` جوه الملف. تقدر كمان تكمّل من غير مفتاح (أوامر بس).

ويندوز ممكن يعرض تحذير SmartScreen عشان البرنامج مش موقّع: دوس More info ثم Run anyway.

## إزاي تكلّمه

- قول «يا يوبي» وبعدها الأمر، أو دوس `Ctrl + Alt + Y`.
- تقدر تغيّر الزرار لأي زرار من الإعدادات ← الاختصار والشاشة ← زرار النداء.

## للمطورين

Python 3.12 + واجهة Tauri في `island-tauri/`. انسخ `config.example.json` إلى `config.json` و `.env.example` إلى `.env`، ثم `python agent.py`.
