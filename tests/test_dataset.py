# -*- coding: utf-8 -*-
"""v7.1: الـ dataset recorder بيسجل الأوامر واللابل بييجي من LearningGuard."""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataset_recorder import DatasetRecorder, load_records   # noqa: E402
from learning_guard import LearningGuard                      # noqa: E402


class FakeAudio:
    def get_wav_data(self):
        return b"RIFF....WAVEfake"


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.rec = DatasetRecorder(root=self.root, log=lambda *_: None)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _guard(self):
        return LearningGuard(lambda p, t, a: self.rec.label(p, "correct", t), delay=0.05,
                             check_process=False, log=lambda *_: None,
                             on_veto=lambda p: self.rec.label(p, "wrong"))

    def test_correct_wrong_corrected(self):
        g = self._guard()
        # 1. صح: فتح وفضل مفتوح
        self.rec.heard(FakeAudio(), "افتح يوروت روك", engine="groq-turbo",
                       conf={"avg_logprob": -0.4}, low=False)
        self.rec.bind_phrase("افتح يوروت روك")
        g.propose("افتح يوروت روك", "euro truck simulator 2")
        time.sleep(0.2)
        # 2. غلط وبعدين اتصلح
        self.rec.heard(FakeAudio(), "افتح ساكه")
        self.rec.bind_phrase("افتح ساكه")
        g.propose("افتح ساكه", "sacke")
        g.on_command("لا مش ده")
        self.rec.label(g.last_vetoed, "corrected", "rocket league")
        # 3. أمر من غير لابل
        self.rec.heard(None, "علي الصوت")
        self.rec.bind_phrase("علي الصوت")
        self.rec.flush()

        recs = sorted(load_records(self.root).values(), key=lambda r: r["ts"])
        self.assertEqual([r.get("label") for r in recs], ["correct", "corrected", None])
        self.assertEqual(recs[0]["target"], "euro truck simulator 2")
        self.assertEqual(recs[1]["target"], "rocket league")
        self.assertTrue(os.path.exists(os.path.join(self.root, recs[0]["wav"])))
        self.assertIsNone(recs[2]["wav"])

    def test_audio_cap(self):
        rec = DatasetRecorder(root=self.root, max_audio_mb=0, log=lambda *_: None)
        rid = rec.heard(FakeAudio(), "افتح لول")
        rec.flush()
        self.assertIsNone(load_records(self.root)[rid]["wav"])

    def test_disabled_writes_nothing(self):
        root = tempfile.mkdtemp()
        rec = DatasetRecorder(root=os.path.join(root, "x"), enabled=False)
        self.assertIsNone(rec.heard(FakeAudio(), "افتح لول"))
        self.assertFalse(os.path.exists(os.path.join(root, "x")))
        shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
