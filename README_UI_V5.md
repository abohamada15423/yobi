# Yobi Dynamic Island v5 (drop-in)

## التركيب
1. اقفل يوبي.
2. انسخ `ui.py` من هنا وحطه مكان `ui.py` في فولدر المشروع (Replace).
3. شغّل `python agent.py`، أو `python ui.py` لعرض كل الحالات.

`agent.py` مش محتاج أي تعديل. المكتبات المطلوبة (Pillow و numpy) موجودة أصلًا في requirements.txt.

## الرجوع للنسخة القديمة
اعمل rename لـ `ui_v4_backup.py` وخليه `ui.py`.

## الحالات
| الحالة | الشكل | الشخصية |
|---|---|---|
| idle | دايرة صغيرة | بترمش وبتبص حواليها، وبتنام بعد دقيقتين ونص |
| hover | كبسولة فيها الساعة | مبسوطة |
| listening | كبسولة عريضة + موجات + جزيئات | عيون واسعة |
| speaking | كبسولة + أعمدة صوت | بقها بيتحرك مع الكلام |
| thinking | بتتقسم لدايرة + كبسولة | نقط بتلف حواليها |
| executing | كبسولة + spinner + progress | مركّزة |
| account | كبسولة + نقط باسورد | مغمّضة + قفل |
| recording | كبسولة + عداد | نقطة تسجيل حمرا |
| suggesting | كارت + أزرار | لمبة فوق راسها |
| success / error / info | كبسولة على قد النص | مبسوطة / X / عادية |

النصوص القديمة بتتعرف لوحدها: «بنفذ...» تبقى executing، و«🔐 حساب» تبقى account، و«💡 / إيه رأيك» تبقى suggesting، و«بسجل» تبقى recording.

## التحكم
- كليك على الدايرة: أوامر سريعة
- دبل كليك: الشات
- كليك يمين: القايمة (فيها «✨ استعراض الحالات»)
- اسحب لتحريكها؛ قربها من نص الشاشة فوق وهي هترجع لمكانها

## API جديد
```python
island.set_progress(0.5)    # 50%
island.set_progress(2.0)    # indeterminate
island.set_progress(-1)     # إخفاء
island.set_suggestions(["افتح فالورانت", "شغل مزيكا"], callback=fn)
island.set_speaking(None)   # تلقائي من tts_engine
```

## ملاحظات
- على ويندوز بتستخدم شفافية حقيقية لكل بكسل، فالتوهج شكله صح على أي خلفية. لو حصلت مشكلة بترجع لوحدها لوضع color-key.
- لو عايز تجبر الوضع البسيط: ضيف `"render": "colorkey"` في `ui_prefs.json`.
- chat_window.py و ui_extras.py و overlay_ui.py ما اتغيروش في الحزمة دي.
