# -*- coding: utf-8 -*-
"""v7.2: موديل الأوامر بيتعلم من أخطاء السمع وبيسكت لما مش واثق."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import intent_model as im   # noqa: E402

try:
    import sklearn  # noqa: F401
    HAVE_SK = True
except ImportError:
    HAVE_SK = False

DATA = {
    "euro truck simulator 2": ["افتح يورو ترك", "افتح يوروت روك", "شغل يورو تراك", "يورو ترك",
                               "افتحلي يوروترك", "افتح يورو ترق"],
    "league of legends": ["افتح لول", "افتح ليجو في اللجنس", "افتح لوني", "شغل ليج اوف ليجندز",
                          "افتح league of legends", "لول"],
    "spotify": ["افتح سبوتيفاي", "افتح سبوتيفويل", "زبوتيفويل", "شغل سبوتي فاي",
                "افتح سبوتفاي", "سبوتيفاي"],
    im.NONE_LABEL: ["علي الصوت", "الساعة كام", "عامل ايه", "اعمل سكرين شوت", "وطي الصوت",
                    "فكرني بعد ساعة", "شكرا يا يوبي", "ايه اللي على الشاشة"],
}


@unittest.skipUnless(HAVE_SK, "scikit-learn مش متسطب")
class IntentModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        X = [im.normalize(t) for lab, ts in DATA.items() for t in ts]
        y = [lab for lab, ts in DATA.items() for _ in ts]
        pipe = im.build_pipeline()
        pipe.fit(X, y)
        cls.m = im.IntentModel(pipe, threshold=0.5)

    def test_mishearings(self):
        self.assertEqual(self.m.predict("افتح يوروت ترك").target, "euro truck simulator 2")
        self.assertEqual(self.m.predict("افتح سبوتيفوي").target, "spotify")

    def test_stays_quiet_on_chat(self):
        self.assertIsNone(self.m.predict("علي الصوت شوية"))
        self.assertIsNone(self.m.predict("الساعة كام دلوقتي"))

    def test_close_verb(self):
        p = self.m.predict("اقفل لول", threshold=0.3)
        self.assertEqual(p.intent, "close")

    def test_fast(self):
        self.assertLess(self.m.predict("افتح لول").ms, 50)

    def test_normalize(self):
        self.assertEqual(im.normalize("إفتح الأغنيّة!"), "افتح الاغنيه")

    def test_missing_model_is_none(self):
        self.assertIsNone(im.IntentModel.load(path="/nope.joblib", log=lambda *_: None))


if __name__ == "__main__":
    unittest.main()
