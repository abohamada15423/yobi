# -*- coding: utf-8 -*-
"""
Intent model — موديل صغير بيفهم "افتح X" من غير ما يستنى الـ LLM.

بيتدرب على أوامرك الحقيقية (tools/train_intent.py) وبيشتغل على الـ CPU في
أقل من 5ms. لو مش واثق (أقل من الـ threshold اللي اتحسب وقت التدريب)،
بيرجّع None ويوبي يكمل بالـ LLM عادي. يعني في أسوأ الأحوال مش هيبوّظ حاجة.

    m = IntentModel.load()          # None لو مفيش موديل متدرب أو sklearn مش متسطب
    p = m.predict("افتح يوروت روك")  # Prediction(intent='open', target='euro truck simulator 2', prob=0.97)
"""

import json
import os
import re
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_HERE, "models", "intent_model.joblib")
META_PATH = os.path.join(_HERE, "models", "intent_model.json")
NONE_LABEL = "__none__"            # مش أمر فتح (دردشة، صوت، أسئلة…)

_TASHKEEL = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_CLOSE_RE = re.compile(r"^(?:اقفل|قفل|اغلق|سكر|close|kill|stop)\b")


def normalize(text):
    """توحيد الكتابة العربي: أ/إ/آ → ا ، ى → ي ، ة → ه ، من غير تشكيل."""
    t = (text or "").lower().strip()
    t = _TASHKEEL.sub("", t)
    t = re.sub("[أإآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub(r"[،,.!؟?\"'«»:;()\[\]\-_]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def detect_verb(text):
    return "close" if _CLOSE_RE.search(normalize(text)) else "open"


def build_pipeline():
    """char n-grams: بتستحمل أخطاء السمع ("يوروت روك" ≈ "يورو ترك") أحسن من الكلمات."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline, FeatureUnion

    feats = FeatureUnion([
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5),
                                  min_df=1, sublinear_tf=True)),
        ("words", TfidfVectorizer(analyzer="word", ngram_range=(1, 2),
                                  token_pattern=r"(?u)\b\w+\b", sublinear_tf=True)),
    ])
    clf = LogisticRegression(C=10.0, max_iter=3000, class_weight="balanced")
    return Pipeline([("feats", feats), ("clf", clf)])


class Prediction:
    __slots__ = ("intent", "target", "prob", "ms")

    def __init__(self, intent, target, prob, ms):
        self.intent, self.target, self.prob, self.ms = intent, target, prob, ms

    def __repr__(self):
        return f"<Prediction {self.intent} {self.target} {self.prob:.2f} {self.ms:.1f}ms>"


class IntentModel:
    def __init__(self, pipeline, threshold=0.8, meta=None):
        self.pipe = pipeline
        self.threshold = float(threshold)
        self.meta = meta or {}

    @classmethod
    def load(cls, path=MODEL_PATH, meta_path=META_PATH, log=print):
        if not os.path.exists(path):
            return None
        try:
            import joblib
            pipe = joblib.load(path)
            meta = {}
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            m = cls(pipe, meta.get("threshold", 0.8), meta)
            log(f"🧠 موديل الأوامر شغال ({meta.get('n_train', '?')} مثال، "
                f"threshold {m.threshold:.2f})")
            return m
        except Exception as e:
            log(f"ℹ️ موديل الأوامر مش شغال: {str(e)[:100]}")
            return None

    def predict(self, text, threshold=None):
        """Prediction لو واثق، None لو لأ (أو لو مش أمر فتح/قفل)."""
        t0 = time.perf_counter()
        x = normalize(text)
        if not x:
            return None
        probs = self.pipe.predict_proba([x])[0]
        classes = self.pipe.classes_
        i = int(probs.argmax())
        label, p = classes[i], float(probs[i])
        ms = (time.perf_counter() - t0) * 1000
        if label == NONE_LABEL or p < (threshold if threshold is not None else self.threshold):
            return None
        return Prediction(detect_verb(text), label, p, ms)

    def top(self, text, k=3):
        probs = self.pipe.predict_proba([normalize(text)])[0]
        order = probs.argsort()[::-1][:k]
        return [(self.pipe.classes_[i], float(probs[i])) for i in order]
