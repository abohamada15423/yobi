# -*- coding: utf-8 -*-
"""v7: تستات فهم أسماء البرامج — كلها من أوامر حقيقية اتقالت ليوبي.

    python -m pytest tests/test_resolver.py      أو      python tests/test_resolver.py
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import target_resolver as tr                      # noqa: E402
from learning_guard import LearningGuard          # noqa: E402
from smart_open import smart_open, exe_matches    # noqa: E402

WEBSITES = {"youtube": "https://www.youtube.com", "يوتيوب": "https://www.youtube.com",
            "facebook": "https://www.facebook.com", "فيسبوك": "https://www.facebook.com",
            "netflix": "https://www.netflix.com", "youtube music": "https://music.youtube.com",
            "discord web": "https://discord.com/app", "discord": "https://discord.com/app",
            "kooora": "https://www.kooora.com", "github": "https://github.com",
            "جيت هب": "https://github.com"}
LOCAL = {"spotify": "spotify.exe", "سبوتيفاي": "spotify.exe", "discord": "discord.exe",
         "ديسكورد": "discord.exe", "calculator": "calc.exe", "الحاسبة": "calc.exe"}
GAMES = {"league of legends": "C:/Riot/LeagueClient.exe", "valorant": "C:/Riot/VALORANT.exe",
         "rocket league": ["steam", "rocket"], "euro truck simulator 2": ["steam", "ets2"],
         "forza horizon 5": ["steam", "fh5"], "the last of us part i": ["steam", "tlou"],
         "celeste": ["steam", "celeste"], "grand theft auto v": ["steam", "gta"],
         "steamworks common redistributables": ["steam", "x"]}
INSTALLED = {"google chrome": "chrome.exe", "valorant": "C:/Riot/VALORANT.exe",
             "microsoft windows desktop runtime - 8.0.19 (x64)": "x.exe",
             "riot client ": "RiotClientServices.exe", "word": "winword.exe"}

CAT = tr.Catalog(WEBSITES, LOCAL, GAMES, INSTALLED)


def R(name, utt=None, low=False):
    return tr.resolve(CAT, name, utterance=utt, stt_low=low)


class OpensTheRightThing(unittest.TestCase):
    def check(self, utt, display, name=None):
        r = R(name or utt, utt)
        self.assertEqual(r.status, "ok", f"{utt}: {r}")
        self.assertEqual(r.best.display, display, f"{utt}: {r}")

    def test_egyptian_spellings(self):
        self.check("افتح يورو ترك", "euro truck simulator 2")
        self.check("افتح، يوروت روك", "euro truck simulator 2")
        self.check("افتح لول", "league of legends")
        self.check("افتح ليجو في اللجنس", "league of legends")
        self.check("افتح فالورانت", "valorant")
        self.check("سبوتيفويل", "spotify")
        self.check("افتح روكيت ليج", "rocket league")
        self.check("افتح كروم", "google chrome")
        self.check("وفيسبوك", "facebook")
        self.check("افتح الحاسبة", "calculator")
        self.check("lol", "league of legends")
        self.check("افتح gta", "grand theft auto v")

    def test_local_beats_website(self):
        self.check("افتح ديسكورد", "discord")
        self.assertEqual(R("افتح ديسكورد").best.kind, "app")
        # الـ LLM قال playvalorant.com بس اللعبة متسطبة
        self.check("افتح valorant", "valorant", name="https://playvalorant.com")

    def test_longer_match_wins(self):
        self.check("افتح يوتيوب ميوزك", "youtube music")
        self.check("افتح يوتيوب", "youtube")

    def test_junk_is_hidden(self):
        names = " ".join(CAT.display_names()).lower()
        self.assertNotIn("runtime", names)
        self.assertNotIn("redistributable", names)


class DoesNotGuess(unittest.TestCase):
    def test_gibberish_is_not_opened(self):
        for utt, name in [("ساكه", "sacke"), ("تالا مصمس", "tala"),
                          ("رحفت اكاري", "akari"), ("خلي بالك باكي", "baki")]:
            r = R(name, utt)
            self.assertNotEqual(r.status, "ok", f"{utt}: {r}")

    def test_llm_picked_something_you_did_not_say(self):
        r = R("euro truck simulator 2", "شارف، مش عارف اقوله ايه الصراحة")
        self.assertEqual(r.status, "ask")
        self.assertIn("not grounded", r.reason)

    def test_reference_words_skip_grounding(self):
        self.assertEqual(R("valorant", "افتحها تاني").status, "ok")

    def test_invented_domains(self):
        self.assertEqual(R("https://www.ism.com", "افتح اسم التفوق").status, "url")
        self.assertEqual(R("https://www.youtube.com", "افتح يوتيوب").status, "ok")

    def test_low_stt_confidence_asks(self):
        self.assertEqual(R("valorant", "افتح فالورانت", low=True).status, "ask")

    def test_garbled_text(self):
        self.assertTrue(tr.text_looks_garbled("шагал инстаграм"))
        self.assertTrue(tr.text_looks_garbled("ufta hlúl"))
        self.assertFalse(tr.text_looks_garbled("افتح valorant"))

    def test_exe_search_is_strict(self):
        self.assertFalse(exe_matches("sacke", "D:/Games/x/SACKEBOY_launcher.exe"))
        self.assertFalse(exe_matches("ac", "D:/Games/ac/ac.exe"))
        self.assertTrue(exe_matches("celeste", "D:/Games/Celeste/Celeste.exe"))


class FakeAgent:
    def __init__(self):
        self.launched = []

    def resolve(self, name, utterance=None, stt_low=False):
        return tr.resolve(CAT, name, utterance=utterance, stt_low=stt_low)

    def launch(self, entry):
        self.launched.append(entry.display)
        return "تم تشغيل اللعبة 🎮"

    def find_on_disk(self, name):
        return None


class SmartOpenFlow(unittest.TestCase):
    def test_ask_then_user_picks(self):
        a, learned = FakeAgent(), []
        g = LearningGuard(lambda *x: learned.append(x), delay=60)
        res = smart_open(a, "euro truck simulator 2", utterance="شارف مش عارف اقوله ايه",
                         choose=lambda q, opts: opts[0][1], guard=g)
        self.assertEqual(a.launched, ["euro truck simulator 2"])
        self.assertTrue(res.startswith("تم"))
        self.assertEqual(learned[0][1], "euro truck simulator 2")   # اختيار صريح = اتعلم

    def test_ask_then_user_says_no(self):
        a = FakeAgent()
        res = smart_open(a, "euro truck simulator 2", utterance="شارف مش عارف",
                         choose=lambda q, opts: "none")
        self.assertTrue(res.startswith("CANCELLED"))
        self.assertEqual(a.launched, [])

    def test_no_buttons_returns_question(self):
        res = smart_open(FakeAgent(), "euro truck simulator 2", utterance="شارف", choose=None)
        self.assertTrue(res.startswith("ASK: قصدك"))


class GuardLearnsOnlyWhatWorked(unittest.TestCase):
    def test_commit_after_delay(self):
        saved = []
        g = LearningGuard(lambda *a: saved.append(a), delay=0.05, check_process=False)
        g.propose("افتح لوني", "league of legends")
        time.sleep(0.2)
        self.assertEqual(saved, [("افتح لوني", "league of legends", "open")])

    def test_no_cancels(self):
        saved = []
        g = LearningGuard(lambda *a: saved.append(a), delay=0.05, log=lambda *_: None)
        g.propose("افتح فالو", "valorant")
        self.assertTrue(g.on_command("لا مش ده"))
        time.sleep(0.2)
        self.assertEqual(saved, [])
        self.assertEqual(g.last_vetoed, "افتح فالو")

    def test_quick_close_cancels(self):
        saved = []
        g = LearningGuard(lambda *a: saved.append(a), delay=0.05, log=lambda *_: None)
        g.propose("افتح ساكه", "sacke")
        self.assertTrue(g.on_close("sacke"))
        time.sleep(0.2)
        self.assertEqual(saved, [])

    def test_normal_command_does_not_cancel(self):
        g = LearningGuard(lambda *a: None, delay=60)
        g.propose("افتح لول", "league of legends")
        self.assertFalse(g.on_command("علي الصوت"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
