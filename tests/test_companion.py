# -*- coding: utf-8 -*-
"""Companion tests — run: python -m unittest tests/test_companion.py"""
import os, sys, tempfile, unittest
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from companion import Companion, in_window


class Clock:
    def __init__(self, y=2026, mo=10, d=5, h=12, mi=0):
        self.t = datetime(y, mo, d, h, mi).timestamp()
    def __call__(self):
        return self.t
    def at(self, h, mi=0, d=5):
        self.t = datetime(2026, 10, d, h, mi).timestamp()
    def add(self, minutes):
        self.t += minutes * 60


class FakeUI:
    def __init__(self):
        self.asked, self.said, self.free = [], [], True
    def ask(self, q, opts, cb, timeout):
        self.asked.append((q, opts, cb))
    def say(self, t):
        self.said.append(t)
    def answer(self, value):
        self.asked[-1][2](value)


def make(clock, ui, ran=None, **cfg):
    path = os.path.join(tempfile.mkdtemp(), "c.json")
    no_water = cfg.pop("no_water", False)
    # v7.3: سؤال "عامل إيه" وملخص الليل مقفولين هنا إلا لو التست طلبهم
    cfg.setdefault("mood_window", "00:00-00:01")
    cfg.setdefault("night_summary_window", "00:00-00:01")
    cfg.setdefault("sleep_nudge_window", "00:00-00:01")
    comp = Companion(ui.ask, ui.say, is_free=lambda: ui.free,
                     run_command=(ran.append if ran is not None else None),
                     config=cfg, data_path=path, clock=clock, log=lambda *_: None)
    if no_water:
        comp.cfg["water_every_min"] = 10 ** 6
        comp.data["asked"]["water"] = clock()
    return comp


class T(unittest.TestCase):
    def test_window_wraps_midnight(self):
        self.assertTrue(in_window(30, "21:00-01:00"))
        self.assertTrue(in_window(22 * 60, "21:00-01:00"))
        self.assertFalse(in_window(12 * 60, "21:00-01:00"))

    def test_quiet_hours_and_busy(self):
        c, ui = Clock(h=3), FakeUI()
        comp = make(c, ui)
        self.assertIsNone(comp.tick())
        c.at(12); ui.free = False
        self.assertIsNone(comp.tick())
        self.assertEqual(ui.asked, [])

    def test_gym_first_then_reminder(self):
        c, ui = Clock(h=12), FakeUI()
        comp = make(c, ui)
        self.assertEqual(comp.tick(), "gym")
        labels = [l for l, _ in ui.asked[-1][1]]
        self.assertIn("مش رايح", labels)
        ui.answer("19:00")
        self.assertIn("الجيم", ui.said[-1])
        c.at(18, 35); ui.free = False          # reminder shows even when busy
        self.assertEqual(comp.tick(), "gym_reminder")
        self.assertIsNone(comp.tick())          # only once

    def test_gap_between_questions(self):
        c, ui = Clock(h=12), FakeUI()
        comp = make(c, ui, no_water=True)   # v7.3: المياه ليها عداد لوحدها
        comp.tick()
        c.add(10)
        self.assertIsNone(comp.tick())
        c.add(30)
        self.assertIsNotNone(comp.tick())

    def test_water_no_then_snooze(self):
        c, ui = Clock(h=12), FakeUI()
        comp = make(c, ui, gym_ask_window="00:00-00:01", music_window="00:00-00:01")
        self.assertEqual(comp.tick(), "water")
        ui.answer("no")
        c.add(21)
        self.assertEqual(comp.tick(), "water")     # snooze ignores the normal gap
        ui.answer("yes")
        self.assertIn("كوباية", ui.said[-1])
        self.assertEqual(comp.data["water_cups"], 1)

    def test_tea_once_per_window(self):
        c, ui = Clock(h=17), FakeUI()
        comp = make(c, ui, gym_ask_window="00:00-00:01", music_window="00:00-00:01",
                    no_water=True)
        self.assertEqual(comp.tick(), "tea")
        c.add(40)
        self.assertIsNone(comp.tick())

    def test_music_runs_command(self):
        c, ui, ran = Clock(h=13), FakeUI(), []
        comp = make(c, ui, ran, gym_ask_window="00:00-00:01", no_water=True)
        self.assertEqual(comp.tick(), "music")
        ui.answer("yes")
        self.assertEqual(ran, ["شغل اغاني"])

    def test_series_flow_buttons_and_text(self):
        c, ui = Clock(h=20), FakeUI()
        comp = make(c, ui, gym_ask_window="00:00-00:01", music_window="00:00-00:01",
                    no_water=True, tea_windows=[])
        self.assertEqual(comp.tick(), "series")
        ui.answer("other")
        self.assertTrue(comp.has_pending_text())
        r = comp.handle_text("الاختيار الحلقة ٥")
        self.assertIn("الاختيار", r)
        self.assertEqual(comp.data["series"], {**comp.data["series"], "name": "الاختيار", "episode": 5})
        c.at(20, d=6)
        self.assertEqual(comp.tick(), "series")
        self.assertIn("الاختيار", ui.asked[-1][0])
        ui.answer("next")
        self.assertEqual(comp.data["series"]["episode"], 6)

    def test_free_text_facts(self):
        c, ui = Clock(h=14), FakeUI()
        comp = make(c, ui)
        self.assertIn("الاختيار", comp.handle_text("بتفرج على مسلسل الاختيار الحلقة 7"))
        self.assertEqual(comp.data["series"]["episode"], 7)
        self.assertIn("٨", comp.handle_text("انا وصلت الحلقة 8"))
        self.assertIn("كوباية", comp.handle_text("شربت مياه"))
        self.assertIn("٧", comp.handle_text("هروح الجيم الساعة 7"))
        self.assertEqual(comp.data["gym"]["time"], "19:00")
        self.assertIsNone(comp.handle_text("افتح كروم"))

    def test_max_per_day_and_disable(self):
        c, ui = Clock(h=12), FakeUI()
        comp = make(c, ui, max_per_day=1, no_water=True)
        comp.tick(); c.add(60)
        self.assertIsNone(comp.tick())
        comp.set_enabled(False)
        c.at(12, d=6)
        self.assertIsNone(comp.tick())

    def test_new_day_resets(self):
        c, ui = Clock(h=12), FakeUI()
        comp = make(c, ui, max_per_day=1)
        comp.tick()
        c.at(12, d=6)
        self.assertEqual(comp.tick(), "gym")


if __name__ == "__main__":
    unittest.main()
