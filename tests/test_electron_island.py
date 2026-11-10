# -*- coding: utf-8 -*-
"""ElectronIsland logic without starting Electron: python tests/test_electron_island.py"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import electron_island as ei  # noqa: E402


def make():
    isl = ei.ElectronIsland.__new__(ei.ElectronIsland)
    isl._init_core(log=lambda *a: None)
    isl.sent = []
    isl._send = isl.sent.append
    return isl


def run_until_idle(isl, seconds=0.5):
    isl.after(seconds * 1000, isl.quit)     # on the loop's own clock: a slow start can't end it before the jobs ran
    isl.mainloop()


class TestElectronIsland(unittest.TestCase):
    def test_state_aliases(self):
        self.assertEqual(ei.norm_state("hide"), "idle")
        self.assertEqual(ei.norm_state("ok"), "success")
        self.assertEqual(ei.norm_state("whatever"), "info")

    def test_long_text_is_cut(self):
        self.assertTrue(ei.shorten("ا " * 400).endswith("…"))
        self.assertLessEqual(len(ei.shorten("ا " * 400)), ei.SAY_MAX)

    def test_after_runs_in_order_and_cancel_works(self):
        isl, seen = make(), []
        isl.after(30, seen.append, "b")
        isl.after(0, seen.append, "a")
        job = isl.after(10, seen.append, "x")
        isl.after_cancel(job)
        run_until_idle(isl, 1.0)          # roomy: a busy machine can delay a 30 ms timer
        self.assertEqual(seen, ["a", "b"])

    def test_only_latest_question_is_answered(self):
        isl, got = make(), []
        isl.ask("q1", [("A", "a")], lambda v: got.append(("q1", v)))
        old = isl._ask_live
        isl.ask("q2", [("B", "b")], lambda v: got.append(("q2", v)))
        isl._handle({"t": "answer", "id": old, "value": "a"})
        isl._handle({"t": "answer", "id": isl._ask_live, "value": "b"})
        self.assertEqual(got, [("q2", "b")])

    def test_end_turn_keeps_a_reply_on_screen(self):
        isl = make()
        isl.say("تمام، فتحت ديسكورد")
        isl.end_turn()
        self.assertFalse(any(m["t"] == "end_turn" for m in isl.sent))
        isl._reply_until = time.monotonic() - 1
        isl.set_state("thinking")
        isl.end_turn()
        self.assertEqual(isl.sent[-1]["t"], "end_turn")
        self.assertEqual(isl._state, "idle")

    def test_window_hide_marks_free(self):
        isl = make()
        isl.say("hi")
        isl._handle({"t": "view", "state": "idle"})
        self.assertTrue(isl.is_free(0))


if __name__ == "__main__":
    unittest.main()
