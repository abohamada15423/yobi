# -*- coding: utf-8 -*-
"""Voice commands for the island: python tests/test_island_voice.py"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import island_voice as iv  # noqa: E402

H = 3600 * 1000


def day(now):
    """Prayer times around `now` (ms): asr in 30 minutes."""
    return {"fajr": now - 9 * H, "sunrise": now - 8 * H, "dhuhr": now - 3 * H, "asr": now + 30 * 60000,
            "maghrib": now + 3 * H, "isha": now + 4 * H + 20 * 60000, "next_fajr": now + 15 * H}


class Pages(unittest.TestCase):
    def test_pages(self):
        for text, page in [("افتح الرف", "shelf"), ("يوبي افتحلي الحافظة", "clips"), ("الحافظة", "clips"),
                           ("افتح التطبيقات", "apps"), ("وريني اللي فات", "history"), ("مواقيت الصلاة", "prayer"),
                           ("افتح مواقيت الصلاه", "prayer"), ("إعدادات يوبي", "settings"), ("افتح اعدادات الجزيرة", "settings")]:
            self.assertEqual(iv.page_for(text), page, text)

    def test_not_pages(self):
        # other things Yobi must keep doing as before
        for text in ["افتح الإعدادات", "افتح كروم", "الأسبوع اللي فات كان حلو", "شغل سورة الرحمن", "افتح رف الكتب في المكتبة"]:
            self.assertIsNone(iv.page_for(text), text)


class Prayer(unittest.TestCase):
    def setUp(self):
        self.now = time.time() * 1000
        self.t = day(self.now)

    def test_next(self):
        r = iv.prayer_reply("الصلاة الجاية امتى؟", self.t, self.now)
        self.assertTrue(r.startswith("العصر الساعة") and "فاضل ٣٠ دقيقة" in r, r)

    def test_a_named_prayer(self):
        r = iv.prayer_reply("فاضل قد ايه على المغرب", self.t, self.now)
        self.assertIn("المغرب الساعة", r)
        self.assertIn("فاضل ٣ ساعات", r)
        r = iv.prayer_reply("الضهر الساعة كام", self.t, self.now)
        self.assertIn("الظهر النهارده كان", r)
        r = iv.prayer_reply("الفجر امتى", self.t, self.now)
        self.assertIn("فاضل ١٥ ساعة", r)          # today's has passed: tomorrow's

    def test_not_prayer(self):
        for text in ["اتعشيت بدري", "شغل سورة العصر", "العصر كان حر", "الصلاة على النبي"]:
            self.assertIsNone(iv.prayer_reply(text, self.t, self.now), text)

    def test_counting(self):
        self.assertEqual(iv._span(60000), "دقيقة")
        self.assertEqual(iv._span(2 * 60000), "دقيقتين")
        self.assertEqual(iv._span(5 * 60000), "٥ دقايق")
        self.assertEqual(iv._span(H + 2 * 60000), "ساعة ودقيقتين")
        self.assertEqual(iv._span(2 * H + 30 * 60000), "ساعتين و٣٠ دقيقة")

    def test_no_times_yet(self):
        self.assertIn("المدينة", iv.prayer_reply("الصلاة الجاية امتى", {}, self.now))


class Matching(unittest.TestCase):
    def test_tk_island_is_left_alone(self):
        self.assertIsNone(iv.match_island_command("افتح الرف", object()))

    def test_open_page_ends_the_turn_then_opens(self):
        sent = []

        class Island:
            _daily = None
            def end_turn(self): sent.append("end_turn")
            def _send(self, m): sent.append(m)
        isl = Island()
        self.assertEqual(iv.match_island_command("افتح الرف", isl), ("page", "shelf"))
        self.assertEqual(iv.open_page(isl, "shelf"), "فتحتلك الرف")
        self.assertEqual(sent, ["end_turn", {"t": "open", "page": "shelf"}])


if __name__ == "__main__":
    unittest.main()
