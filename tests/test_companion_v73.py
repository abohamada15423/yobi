# -*- coding: utf-8 -*-
"""v7.3: المياه كل نص ساعة + يوبي بيفهم إنت بتعمل إيه قبل ما يسأل."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion import Companion                  # noqa: E402
from test_companion import Clock, FakeUI         # noqa: E402

OFF = "00:00-00:01"


def make(c, ui, game=None, idle=None, **cfg):
    base = dict(gym_ask_window=OFF, music_window=OFF, series_window=OFF, tea_windows=[],
                mood_window=OFF, night_summary_window=OFF, sleep_nudge_window=OFF)
    base.update(cfg)
    st = {"game": None, "idle": 0}
    comp = Companion(ui.ask, ui.say, is_free=lambda: ui.free and not st["game"],
                     config=base, data_path=os.path.join(tempfile.mkdtemp(), "c.json"),
                     clock=c, log=lambda *_: None,
                     get_game=lambda: st["game"], idle_s=lambda: st["idle"])
    return comp, st


class Water(unittest.TestCase):
    def test_every_30_min(self):
        c, ui = Clock(h=15), FakeUI()
        comp, _ = make(c, ui)
        self.assertEqual(comp.tick(), "water")
        ui.answer("yes")
        c.add(20)
        self.assertIsNone(comp.tick())
        c.add(11)
        self.assertEqual(comp.tick(), "water")

    def test_water_does_not_eat_question_budget(self):
        c, ui = Clock(h=15), FakeUI()
        comp, _ = make(c, ui, max_per_day=1)
        for _ in range(5):
            self.assertEqual(comp.tick(), "water")
            ui.answer("yes")
            c.add(31)
        self.assertEqual(comp.data["count_today"], 0)
        self.assertEqual(comp.data["water_cups"], 5)

    def test_counts_from_when_you_drank(self):
        c, ui = Clock(h=15), FakeUI()
        comp, _ = make(c, ui)
        comp.tick()                     # سأل 3:00
        c.add(25)
        comp.handle_text("شربت مياه")   # شرب 3:25 → الجاي 3:55 مش 3:30
        c.add(10)
        self.assertIsNone(comp.tick())
        c.add(21)
        self.assertEqual(comp.tick(), "water")

    def test_no_then_10_min(self):
        c, ui = Clock(h=15), FakeUI()
        comp, _ = make(c, ui)
        comp.tick()
        ui.answer("no")
        self.assertIn("١٠", ui.said[-1])
        c.add(10)
        self.assertEqual(comp.tick(), "water")

    def test_goal_message(self):
        c, ui = Clock(h=15), FakeUI()
        comp, _ = make(c, ui, water_goal=2)
        comp.handle_text("شربت مياه")
        self.assertIn("كمّلت", comp.handle_text("شربت كوباية"))
        self.assertIn("٢ من ٢", comp.handle_text("شربت كام كوباية"))

    def test_behind_schedule_wording(self):
        c, ui = Clock(h=20), FakeUI()
        comp, _ = make(c, ui)
        comp.tick()
        self.assertIn("بس النهارده", ui.asked[-1][0])

    def test_ignored_twice_backs_off(self):
        c, ui = Clock(h=15), FakeUI()
        comp, _ = make(c, ui, answer_timeout_s=45)
        self.assertEqual(comp.tick(), "water"); c.add(31)   # طنّش 1
        self.assertEqual(comp.tick(), "water"); c.add(31)   # طنّش 2
        self.assertIsNone(comp.tick())  # بقى كل ساعة بدل نص ساعة
        self.assertEqual(comp.data["water_ignored"], 2)
        c.add(31)
        self.assertEqual(comp.tick(), "water")
        ui.answer("yes")
        self.assertEqual(comp.data["water_ignored"], 0)


class Context(unittest.TestCase):
    def test_waits_for_game_then_reminds(self):
        c, ui = Clock(h=15), FakeUI()
        comp, st = make(c, ui)
        comp.tick(); ui.answer("yes")
        st["game"] = "League of Legends"
        comp.tick()
        for _ in range(9):              # ٤٥ دقيقة لعب
            c.add(5)
            self.assertIsNone(comp.tick())
        st["game"] = None
        self.assertEqual(comp.tick(), "water")
        self.assertIn("League of Legends", ui.asked[-1][0])
        self.assertIn("٤٥", ui.asked[-1][0])

    def test_short_game_no_special_message(self):
        c, ui = Clock(h=15), FakeUI()
        comp, st = make(c, ui)
        comp.tick(); ui.answer("yes")
        st["game"] = "Valorant"; comp.tick(); c.add(5)
        st["game"] = None
        self.assertIsNone(comp.tick())

    def test_away_then_welcome_back(self):
        c, ui = Clock(h=15), FakeUI()
        comp, st = make(c, ui)
        comp.tick(); ui.answer("yes")
        st["idle"] = 40 * 60
        c.add(40)
        self.assertIsNone(comp.tick())
        st["idle"] = 3
        self.assertEqual(comp.tick(), "water")
        self.assertIn("رجعت", ui.asked[-1][0])


class Mood(unittest.TestCase):
    def test_once_a_day_and_tired_is_quieter(self):
        c, ui = Clock(h=14), FakeUI()
        comp, _ = make(c, ui, mood_window="13:00-22:00", music_window="12:00-23:00",
                       water_every_min=10 ** 6)
        comp.data["asked"]["water"] = c()
        self.assertEqual(comp.tick(), "mood")
        ui.answer("tired")
        self.assertIn("بريك", ui.said[-1])
        c.add(120)
        self.assertIsNone(comp.tick())  # تعبان → مفيش مزيكا النهارده

    def test_free_text_mood(self):
        c, ui = Clock(h=14), FakeUI()
        comp, _ = make(c, ui)
        self.assertIn("نفس", comp.handle_text("انا مضغوط شوية"))
        self.assertTrue(comp._tired())


class Night(unittest.TestCase):
    def test_summary_once(self):
        c, ui = Clock(h=23, mi=40), FakeUI()
        comp, _ = make(c, ui, night_summary_window="23:30-00:30", water_every_min=10 ** 6)
        comp.data["asked"]["water"] = c()
        comp.handle_text("شربت مياه")
        self.assertEqual(comp.tick(), "night_summary")
        self.assertIn("١ من ٨", ui.said[-1])
        c.add(5)
        self.assertIsNone(comp.tick())


if __name__ == "__main__":
    unittest.main()
