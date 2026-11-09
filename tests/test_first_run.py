# -*- coding: utf-8 -*-
"""First run on a friend's PC: python tests/test_first_run.py"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import first_run as fr  # noqa: E402
import island_tools as it  # noqa: E402

G = "AIza" + "x" * 35
Q = "gsk_" + "y" * 52


class TestKeys(unittest.TestCase):
    def test_shapes(self):
        self.assertTrue(fr.looks_like("gemini", G))
        self.assertFalse(fr.looks_like("gemini", "AIza short"))
        self.assertTrue(fr.looks_like("gemini", "AQ.Ab8RN6" + "z" * 40))      # Google's newer format
        self.assertFalse(fr.looks_like("gemini", Q))
        self.assertTrue(fr.looks_like("groq", Q))
        self.assertFalse(fr.looks_like("groq", G))

    def test_write_keeps_other_lines_and_replaces_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            with open(p, "w", encoding="utf-8") as f:
                f.write("YOBI_MODEL=x\nGROQ_API_KEY=old\nAIzaOLDKEYWITHOUTNAME\n")
            fr.write_env(p, G, "")
            keys = fr.read_env(p)
            self.assertEqual(keys["GEMINI_API_KEY"], G)
            self.assertEqual(keys["YOBI_MODEL"], "x")
            self.assertNotIn("GROQ_API_KEY", keys)
            self.assertNotIn("AIzaOLD", open(p, encoding="utf-8").read())
            fr.write_env(p, G, Q)
            self.assertEqual(fr.read_env(p)["GROQ_API_KEY"], Q)

    def test_no_window_when_a_key_is_there(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"GROQ_API_KEY={G}\n")                 # a Gemini key under the Groq name
            with mock.patch("tkinter.Tk", side_effect=AssertionError("no window")):
                self.assertEqual(fr.ask_keys(p), (G, ""))

    def test_offline_check_never_raises(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("no net")):
            self.assertEqual(fr.check_online("gemini", G), "offline")

    def test_no_key_choice_is_remembered_then_replaced_by_a_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            fr.write_env(p, "", "")
            self.assertEqual(fr.read_env(p).get("YOBI_NO_KEY"), "1")
            with mock.patch("tkinter.Tk", side_effect=AssertionError("no window")):
                self.assertEqual(fr.ask_keys(p), ("", ""))            # not asked again
            fr.write_env(p, G, "")
            self.assertNotIn("YOBI_NO_KEY", fr.read_env(p))


class TestAutostart(unittest.TestCase):
    def test_uses_the_launcher_and_still_knows_the_old_entry(self):
        new, old = it.autostart_command(), it.autostart_command(legacy=True)
        self.assertIn("launcher.pyw", new)
        self.assertIn("-s -E", new)
        self.assertIn("agent.py", old)


if __name__ == "__main__":
    unittest.main()
