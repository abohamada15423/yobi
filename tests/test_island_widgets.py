# -*- coding: utf-8 -*-
"""Island widgets logic without Windows APIs: python tests/test_island_widgets.py"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import island_widgets as iw  # noqa: E402


class TestIslandWidgets(unittest.TestCase):
    def test_app_label(self):
        self.assertEqual(iw.app_label("SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"), "Spotify")
        self.assertEqual(iw.app_label("Chrome"), "Chrome")
        self.assertEqual(iw.app_label("308046B0AF4A39CB"), "Firefox")
        self.assertEqual(iw.app_label("Contoso.Player_8wekyb3d8bbwe!App"), "App")

    def test_player_in_front(self):
        sp = "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"
        self.assertTrue(iw.same_app(sp, "Spotify.exe"))
        self.assertFalse(iw.same_app(sp, "chrome.exe"))
        self.assertTrue(iw.same_app("308046B0AF4A39CB", "firefox.exe"))
        self.assertFalse(iw.same_app("Chrome", "msedge.exe"))
        self.assertFalse(iw.same_app("Chrome", ""))

    def test_messages_from_window(self):
        w = iw.IslandWidgets(send=lambda m: None)
        w._push_stats = lambda: None
        w.handle({"t": "panel", "open": True})
        self.assertTrue(w._panel_open.is_set())
        w.handle({"t": "panel", "open": False})
        self.assertFalse(w._panel_open.is_set())
        w.handle({"t": "media", "cmd": "seek", "pos": 42})
        w.handle({"t": "media", "cmd": "rm -rf"})          # unknown commands are dropped
        self.assertEqual(w._cmds.get_nowait(), ("seek", 42))
        self.assertTrue(w._cmds.empty())

    def test_artwork_is_shrunk(self):
        from PIL import Image
        raw = io.BytesIO()
        Image.new("RGB", (600, 600), (30, 90, 168)).save(raw, "PNG")
        url = iw.art_data_url(raw.getvalue())
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))
        self.assertLess(len(url), 20000)
        self.assertIsNone(iw.art_data_url(b"not an image"))


if __name__ == "__main__":
    unittest.main()
