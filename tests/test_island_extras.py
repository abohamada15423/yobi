# -*- coding: utf-8 -*-
"""Island extras logic, no network and no window: python tests/test_island_extras.py"""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import island_extras as ix  # noqa: E402
import island_tools as it  # noqa: E402


class TestSmartClipboard(unittest.TestCase):
    def test_calc_is_arithmetic_only(self):
        self.assertEqual(ix.calc("12*(3+4)"), 84)
        self.assertEqual(ix.calc("١٢ × ٣"), 36)
        self.assertEqual(ix.calc("15%*200"), 30)
        self.assertEqual(ix.calc("2^3^2"), 512)
        for bad in ("__import__('os')", "2**", "1/0", "9^999", "abc", ""):
            with self.assertRaises((ValueError, ZeroDivisionError)):
                ix.calc(bad)

    def test_classify(self):
        self.assertEqual(ix.classify("https://example.com/x")["kind"], "link")
        self.assertEqual(ix.classify("#abc"), {"kind": "color", "value": "#AABBCC"})
        self.assertEqual(ix.classify("rgb(30, 90, 168)")["value"], "#1E5AA8")
        self.assertEqual(ix.classify("12*(3+4)")["result"], "84")
        self.assertEqual(ix.classify(" ".join(["كلمة"] * 45))["words"], 45)
        for plain in ("2026-11-07", "010-1234-5678", "10:30", "hello", "javascript:alert(1)", "rgb(300,1,1)"):
            self.assertIsNone(ix.classify(plain), plain)


class TestSettingsAndRadio(unittest.TestCase):
    def test_radio_hosts(self):
        self.assertTrue(ix.radio_url_ok("https://backup.qurango.net/radio/ahmad_alajmy"))
        self.assertFalse(ix.radio_url_ok("http://backup.qurango.net/radio/x"))
        self.assertFalse(ix.radio_url_ok("https://evil.example.com/stream"))
        self.assertFalse(ix.radio_url_ok("https://backup.qurango.net.evil.com/x"))

    def test_new_island_settings(self):
        got = it.clean_settings("island", {
            "weather": False, "battery_saver_at": 5, "radio_volume": 250,
            "radio_station": "https://stream.radiojar.com/abc", "pinned_apps": ["Discord", 3, "", "Steam"],
            "celebrate": "yes"})
        self.assertEqual(got, {"weather": False, "battery_saver_at": 10, "radio_volume": 100,
                               "radio_station": "https://stream.radiojar.com/abc",
                               "pinned_apps": ["Discord", "Steam"]})
        self.assertEqual(it.clean_settings("island", {"radio_station": "https://evil.com/x"}), {})


class _Entry:
    def __init__(self, display, kind="installed", launch="x"):
        self.display, self.kind, self.launch = display, kind, launch


class _Catalog:
    entries = [_Entry("Discord"), _Entry("Steam"), _Entry("YouTube", kind="site"), _Entry("Spotify")]


class TestAppsAndMoments(unittest.TestCase):
    def make(self, pinned=None):
        sent = []
        island = mock.Mock()
        island._agent.catalog = _Catalog()
        tools = mock.Mock()
        tools.cfg = {"pinned_apps": pinned or []}
        x = ix.IslandExtras(sent.append, island=island, tools=tools)
        return x, sent

    def test_default_pins_come_from_installed_apps_only(self):
        x, _ = self.make()
        self.assertEqual(x._pins(), ["Discord", "Spotify", "Steam"])   # websites are not pinned

    def test_pin_and_unpin(self):
        x, sent = self.make(pinned=["Steam"])
        with mock.patch.object(it, "save_section") as save:
            x._pin("discord", True)
            save.assert_called_with("island", {"pinned_apps": ["Steam", "Discord"]})
            x._pin("Steam", False)
            save.assert_called_with("island", {"pinned_apps": ["Discord"]})
        with mock.patch.object(it, "save_section") as save:
            x._pin("YouTube", True)              # a website: refused
            save.assert_not_called()

    def test_welcome_back_lists_prayers_missed(self):
        x, _ = self.make()
        now = time.time()
        x._daily = mock.Mock(_times={"asr": (now - 600) * 1000, "maghrib": (now + 3600) * 1000})
        self.assertEqual(x._prayers_between(now - 1800, now), ["أذان العصر"])

    def test_brief_has_next_prayer_and_weather(self):
        x, _ = self.make()
        now = time.time() * 1000
        x._daily = mock.Mock(_times={"fajr": now - 3e6, "dhuhr": now + 6e5}, _events=[])
        x.weather = {"temp": 23, "code": 2}
        b = x._brief()
        self.assertEqual(b["kind"], "brief")
        self.assertEqual(b["next"]["prayer"], "dhuhr")
        self.assertEqual(b["weather"]["temp"], 23)
        self.assertEqual(b["meetings"], 0)


if __name__ == "__main__":
    unittest.main()
