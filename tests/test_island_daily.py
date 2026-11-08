# -*- coding: utf-8 -*-
"""Island daily logic, no Electron and no network: python tests/test_island_daily.py"""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import island_daily as idl  # noqa: E402


def hm(h):
    return int(h) * 60 + h % 1 * 60


def make(**cfg):
    sent = []
    base = dict(idl.DEFAULTS, **cfg)
    d = idl.IslandDaily(sent.append, cfg=base)
    return d, sent


class TestPrayerTimes(unittest.TestCase):
    def test_cairo_matches_noaa_within_two_minutes(self):
        # NOAA solar calculator for Cairo, 7 Nov 2026, UTC+2: sunrise 6:13, noon 11:39, sunset 17:05
        h = idl.prayer_hours(2026, 11, 7, 30.0444, 31.2357, 2)
        self.assertAlmostEqual(hm(h["sunrise"]), 6 * 60 + 13, delta=2)
        self.assertAlmostEqual(hm(h["dhuhr"]), 11 * 60 + 39, delta=2)
        self.assertAlmostEqual(hm(h["maghrib"]), 17 * 60 + 5, delta=2)
        order = [h[k] for k in ("fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha")]
        self.assertEqual(order, sorted(order))

    def test_hanafi_asr_is_later(self):
        std = idl.prayer_hours(2026, 11, 7, 30.0444, 31.2357, 2, asr_factor=1)["asr"]
        han = idl.prayer_hours(2026, 11, 7, 30.0444, 31.2357, 2, asr_factor=2)["asr"]
        self.assertGreater(han, std + 0.5)

    def test_makkah_isha_is_90_minutes_after_maghrib(self):
        h = idl.prayer_hours(2026, 11, 7, 21.4225, 39.8262, 3, method="MAKKAH")
        self.assertAlmostEqual(h["isha"] - h["maghrib"], 1.5, places=6)

    def test_quiet_hours_wrap_midnight(self):
        self.assertTrue(idl.in_quiet("23:00-07:00", 30))
        self.assertFalse(idl.in_quiet("23:00-07:00", 12 * 60))
        self.assertFalse(idl.in_quiet("", 30))


class TestFocus(unittest.TestCase):
    def test_focus_then_break_starts_by_itself_then_asks(self):
        d, sent = make(focus_min=25, break_min=5, long_break_min=15)
        d.focus_start()
        self.assertEqual(d.phase, "focus")
        d.ends_at = time.time() - 1
        d._focus_tick()
        self.assertEqual(d.phase, "break")
        self.assertIn({"t": "notice", "kind": "focus_done", "round": 1, "next_min": 5}, sent)
        d.ends_at = time.time() - 1
        d._focus_tick()
        self.assertIsNone(d.phase)
        self.assertEqual(sent[-1]["kind"], "break_done")

    def test_every_fourth_break_is_long(self):
        d, _ = make()
        d.focus_start()
        d.round = 3
        d.ends_at = time.time() - 1
        d._focus_tick()
        self.assertEqual(d.phase, "long")

    def test_pause_keeps_time_left(self):
        d, _ = make()
        d.focus_start()
        d.focus_pause()
        self.assertIsNone(d.ends_at)
        self.assertGreater(d.paused_left, 24 * 60)
        d.focus_resume()
        self.assertIsNotNone(d.ends_at)


class TestReminders(unittest.TestCase):
    def test_waits_during_focus(self):
        d, sent = make()
        d.focus_start()
        d._next_reminder = 0
        d._reminder_tick()
        self.assertFalse(any(m.get("kind") == "reminder" for m in sent))

    def test_no_repeats_until_all_shown(self):
        d, sent = make()
        for _ in range(len(idl.REMINDERS)):
            d._next_reminder = 0
            d._reminder_tick()
        texts = [m["text"] for m in sent if m.get("kind") == "reminder"]
        self.assertEqual(len(texts), len(set(texts)), len(idl.REMINDERS))

    def test_only_the_kinds_left_on(self):
        d, sent = make(remind_dua=False, remind_dhikr=False)
        for _ in range(30):
            d._next_reminder = 0
            d._reminder_tick()
        got = [m for m in sent if m.get("kind") == "reminder"]
        self.assertEqual({m["sub"] for m in got}, {"ayah"})
        self.assertTrue(all(m["ref"] and isinstance(m["quran"], bool) for m in got))
        self.assertEqual(len(idl.reminder_pool({"remind_ayah": False, "remind_dua": False, "remind_dhikr": False})),
                         len(idl.REMINDERS))       # all off: every text rather than none

    def test_dropped_reminder_comes_back(self):
        d, sent = make()
        d._next_reminder = 0
        d._reminder_tick()
        shown = sent[-1]["text"]
        d.handle({"t": "notice_dropped", "kind": "reminder"})
        self.assertLess(d._next_reminder - time.time(), 61)
        self.assertEqual(d._bag[-1][1], shown)


class TestWaterAndMeetings(unittest.TestCase):
    def test_water_uses_the_companion(self):
        class C:
            data, cfg = {"water_cups": 2}, {"water_goal": 8}
            def _drank(self):
                self.data["water_cups"] += 1
                return "عاش"
        d, sent = make()
        d.set_companion(C())
        d._add_water()
        self.assertIn({"t": "water", "count": 3, "goal": 8}, sent)
        self.assertEqual(sent[-1]["t"], "say")

    def test_only_known_meeting_links_open(self):
        d, _ = make()
        d._links = {"a": "https://meet.google.com/abc-defg-hij", "b": "https://evil.example.com/x"}
        with mock.patch("webbrowser.open") as op:
            d.handle({"t": "meeting_join", "id": "a"})
            d.handle({"t": "meeting_join", "id": "b"})
            d.handle({"t": "meeting_join", "id": "nope"})
        op.assert_called_once_with("https://meet.google.com/abc-defg-hij")


if __name__ == "__main__":
    unittest.main()
