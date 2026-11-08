# تدريب نداء «يا يوبي» (openWakeWord)

التدريب نفسه بيشتغل على **Linux** بس (مولّد الأصوات الصناعية اللي بيستخدمه openWakeWord مش بيدعم ويندوز). عندك 3 طرق: **Google Colab** (الأسهل، وفيه GPU مجاني)، أو **WSL2 Ubuntu** على جهازك، أو أي جهاز Linux. يوبي نفسه بيشغّل الموديل الناتج عادي على ويندوز.

## 1) سجّل صوتك على ويندوز (حوالي 15 دقيقة)
```bash
python tools/record_clips.py wake --positives 200 --negatives 120
```
بيطلع فولدر `wake_data/` فيه `positive/` و `negative/`. غيّر طريقة كلامك بين التسجيلات (قريب وبعيد، عالي وواطي، بسرعة وببطء، ومع موسيقى أو مروحة شغالة). التنويع ده هو اللي بيخلي الموديل يفهمك في أي ظروف.

اضغط الفولدر كده: `wake_data.zip`.

## 2) درّب على Colab
1. افتح الـ notebook الرسمي:
   https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb
   (Open in Colab ← Runtime ← GPU).
2. شغّل خلايا **التسطيب وتنزيل البيانات** بس: piper-sample-generator، و MIT RIRs، و AudioSet/FMA، وملفات الـ features. وقف قبل خلية "Modify values in the config".
3. ارفع `ya_yobi.yaml` و `merge_real_voice.py` و `wake_data.zip`، وبعدين شغّل:
```python
!unzip -q wake_data.zip
!python openwakeword/openwakeword/train.py --training_config ya_yobi.yaml --generate_clips
!python merge_real_voice.py --data wake_data --out my_custom_model/ya_yobi
!python openwakeword/openwakeword/train.py --training_config ya_yobi.yaml --augment_clips
!python openwakeword/openwakeword/train.py --training_config ya_yobi.yaml --train_model
```
4. نزّل `my_custom_model/ya_yobi.onnx`. لو الخطوة الأخيرة طلّعت خطأ في التحويل لـ tflite، تجاهله طالما ملف الـ `.onnx` اتعمل.

> **الوقت:** حوالي 1–2 ساعة على GPU في Colab. لو عايز تجربة أسرع، خلّي `n_samples: 5000` و `steps: 15000`.

## 3) شغّله في يوبي
- حط الملف في `Yobi/models/ya_yobi.onnx`. ده المسار الافتراضي، فمش محتاج تغيّر حاجة.
- `pip install openwakeword`
- أول تشغيل بينزّل ملفات الـ features المشتركة لوحده، وده محتاج نت مرة واحدة.

## 4) اظبط الحساسية
في `config.json`:
```json
"hearing": {
  "wake_threshold": 0.5,
  "wake_patience": 2,
  "wake_debug": true,
  "wake_verify_whisper": false
}
```
- **بيصحى لوحده كتير:** ارفع `wake_threshold` لـ 0.6–0.7 أو `wake_patience` لـ 3.
- **مش بيسمعك:** نزّل `wake_threshold` لـ 0.35–0.4.
- `wake_debug: true` بيطبع الـ score، فتقدر تشوف أرقامك الحقيقية.
- `wake_verify_whisper: true` بيخلي Whisper يتأكد من كل نداء قبل ما يوبي يرد. فعّله أول أسبوع لو الموديل لسه بيغلط.

## من غير موديل لسه؟
تقدر تجرّب الـ pipeline كله بموديل جاهز: `"wake_model": "hey_jarvis"` (قول «hey jarvis»). ولو مفيش أي موديل خالص، يوبي بيرجع لوحده للنداء بـ Whisper زي الأول.
