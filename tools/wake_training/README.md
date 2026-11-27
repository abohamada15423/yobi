# تدريب نداء «يا يوبي» (openWakeWord)

التدريب بيتعمل على **Google Colab** (الكارت المجاني T4 كفاية، حوالي نص ساعة)، ويوبي بيشغّل الموديل الناتج عادي على ويندوز. النوتبوك الرسمي بتاع openWakeWord مبقاش شغال، فالتدريب هنا بسكريبت `train_wake.py`.

## 1) سجّل صوتك على ويندوز (حوالي 15 دقيقة)
```bash
python tools/record_clips.py wake --positives 200 --negatives 120
```
بيطلع فولدر `wake_data/` فيه `positive/` و `negative/`. غيّر طريقة كلامك بين التسجيلات (قريب وبعيد، عالي وواطي، بسرعة وببطء). التنويع ده هو اللي بيخلي الموديل يفهمك في أي ظروف. التسجيل فوق موسيقى عالية مش بيفيد: السكريبت مش بيعرف يحدد مكان النداء فيه وبيسيبه.

## 2) جهّز التسجيلات للرفع
```bash
python tools/wake_training/make_bundle.py
```
بيطلّع `data/colab/wake/real_1.zip`, `real_2.zip`, … (كل ملف تحت 9 ميجا)، وبيقسم التسجيلات لتدريب واختبار. بياخد كمان الأوامر اللي يوبي سجّلها (`data/commands`) ودوشة الأوضة (`data/room_noise`) كأمثلة «مش نداء».

⚠️ دي أصوات حقيقية: الفولدر تحت `data/` اللي git بيتجاهله. ماتعملهاش commit وماتنشرهاش.

## 3) درّب على Colab
Runtime ← Change runtime type ← **T4 GPU**. ارفع `train_wake.py` وملفات `real_*.zip` من لوحة Files، وشغّل:
```python
!pip -q install piper-sample-generator onnx onnxscript soundfile
!pip -q install --no-deps openwakeword
!pip -q uninstall -y onnxruntime && pip -q install onnxruntime-gpu
!git clone -q --depth 1 https://github.com/rhasspy/piper-sample-generator psg
!mkdir -p models esc50 music
!wget -q -nc -P models https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt
!wget -q -nc -P models https://raw.githubusercontent.com/rhasspy/piper-sample-generator/master/models/en_US-libritts_r-medium.pt.json
!wget -q -nc https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy
!wget -q -nc https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy
!wget -q -nc -O esc50.zip https://github.com/karolpiczak/ESC-50/archive/master.zip && unzip -q -n esc50.zip 'ESC-50-master/audio/*' -d esc50
!wget -q -nc https://huggingface.co/datasets/marsyas/gtzan/resolve/main/data/genres.tar.gz && tar -xzf genres.tar.gz -C music 2>/dev/null
!for z in real_*.zip; do unzip -q -o $z; done

!PYTHONPATH=psg python train_wake.py gen --work w --piper-model models/en_US-libritts_r-medium.pt
!python train_wake.py feats --work w --real real --bg esc50 music --rir psg/piper_sample_generator/impulses
!python train_wake.py train --work w --acav openwakeword_features_ACAV100M_2000_hrs_16bit.npy --fp-val validation_set_features.npy --out ya_yobi.onnx
!python train_wake.py eval --real real --models ya_yobi.onnx
```
- `gen` بيولّد 6000 نداء و6000 جملة شبهه بأصوات كتير (دقيقتين)، و`feats` بيجهّز أمثلة التدريب (5 دقايق)، و`train` بيدرّب (حوالي ربع ساعة).
- `train` بيطبع جدول: عند كل حد (threshold) الموديل بيسمع كام في المية من النداءات، وبيصحى غلط كام مرة في الساعة على 11 ساعة صوت عام. الموديل بيتحفظ بحيث الحد **0.5** يساوي حوالي مرتين صحيان غلط في الساعة (`--target` لو عايز رقم تاني).
- `eval` بيشغّل تسجيلات الاختبار الحقيقية على الموديل زي ما يوبي بيسمع، وبيقول أنهي تسجيلات «مش نداء» خدعته.
- لو عايز تقارن بموديل قديم: `train_wake.py score --work w --fp-val validation_set_features.npy --models old.onnx ya_yobi.onnx`.

نزّل `ya_yobi.onnx`.

## 4) شغّله في يوبي
- حط الملف في `Yobi/models/ya_yobi.onnx`. ده المسار الافتراضي، فمش محتاج تغيّر حاجة.
- `pip install openwakeword`
- أول تشغيل بينزّل ملفات الـ features المشتركة لوحده، وده محتاج نت مرة واحدة.

## 5) اظبط الحساسية
في `config.json`:
```json
"hearing": {
  "wake_threshold": 0.5,
  "wake_patience": 1,
  "wake_debug": true,
  "wake_verify_whisper": false
}
```
- **بيصحى لوحده كتير:** ارفع `wake_threshold` لـ 0.6–0.7 أو `wake_patience` لـ 2.
- **مش بيسمعك:** نزّل `wake_threshold` لـ 0.3–0.4.
- `wake_debug: true` بيطبع الـ score، فتقدر تشوف أرقامك الحقيقية.
- `wake_verify_whisper: true` بيخلي Whisper يتأكد من كل نداء قبل ما يوبي يرد. محتاج كارت شاشة عشان مايبطّأش الرد.

## من غير موديل لسه؟
تقدر تجرّب الـ pipeline كله بموديل جاهز: `"wake_model": "hey_jarvis"` (قول «hey jarvis»). ولو مفيش أي موديل خالص، يوبي بيرجع لوحده للنداء بـ Whisper زي الأول.
