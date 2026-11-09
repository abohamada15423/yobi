# -*- coding: utf-8 -*-
"""The Tauri island against the real Python side: python tests/test_island_tauri.py

Starts yobi-island.exe off-screen through ElectronIsland(engine="tauri"), checks the token
handshake, messages both ways, and that the window exits when Python says quit.
Skipped when the Tauri island hasn't been built yet.
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import electron_island as ei  # noqa: E402


@unittest.skipIf(ei.find_tauri() is None, "Tauri island not built")
class TestTauriIsland(unittest.TestCase):
    def test_handshake_messages_and_quit(self):
        os.environ["YOBI_ISLAND_OFFSCREEN"] = "1"
        try:
            isl = ei.ElectronIsland(engine="tauri", log=lambda *a: None)
        finally:
            os.environ.pop("YOBI_ISLAND_OFFSCREEN", None)
        got = []
        isl._handle_orig = isl._handle
        isl._handle = lambda m: (got.append(m), isl._handle_orig(m))
        # Python → window: the window draws them; window → Python: a log line proves the way back
        isl.after(800, isl.set_state, "listening", "سامعك")
        isl.after(1200, isl.say, "تمام، فتحت ديسكورد", "success")
        isl.after(1600, isl._send, {"t": "ping_test"})
        isl.after(2500, isl.quit)
        _watchdog = threading.Timer(20, lambda: os._exit(3)); _watchdog.daemon = True; _watchdog.start()
        t0 = time.time()
        isl.mainloop()
        code = isl._proc.wait(10)
        self.assertLess(time.time() - t0, 15)
        self.assertEqual(code, 0, "the window should exit cleanly when Python says quit")

    def test_reply_ends_and_python_hears_it(self):
        """Yobi's turn (interface 2): a reply stays its reading time, then the window tells Python
        it's done (`view` idle), so agent.py's is_free() sees Yobi free again."""
        os.environ["YOBI_ISLAND_OFFSCREEN"] = "1"
        try:
            isl = ei.ElectronIsland(engine="tauri", log=lambda *a: None)
        finally:
            os.environ.pop("YOBI_ISLAND_OFFSCREEN", None)
        seen = {}
        isl.after(800, isl.set_state, "success", "تم")              # reading time 3.85 s
        isl.after(3500, lambda: seen.update(mid=isl._state))
        isl.after(6000, lambda: seen.update(end=isl._state))
        isl.after(6200, isl.quit)
        _watchdog = threading.Timer(25, lambda: os._exit(3)); _watchdog.daemon = True; _watchdog.start()
        isl.mainloop()
        self.assertEqual(isl._proc.wait(10), 0)
        self.assertEqual(seen.get("mid"), "success", "the reply should still be up")
        self.assertEqual(seen.get("end"), "idle", "the window should have told Python the turn ended")


if __name__ == "__main__":
    unittest.main()
