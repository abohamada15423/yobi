# -*- coding: utf-8 -*-
"""Local brain (no key, no internet): python tests/test_local_brain.py

EVAL is written apart from local_brain.TEMPLATES (other words, speech slips, chatter), so the
numbers say how it does on phrasings it never saw. A wrong action is worse than "I don't know":
the test demands near-perfect precision and good coverage."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_brain as lb  # noqa: E402

APPS_HERE = {"discord", "spotify", "valorant", "chrome", "steam", "euro truck simulator 2", "minecraft",
             "ديسكورد", "سبوتيفاي", "كروم", "فالورانت", "ستيم", "ماين كرافت", "يوتيوب", "youtube"}

# (what was heard, expected tool, expected detail or None)
EVAL = [
    # open
    ("افتح الديسكورد", "open_app", "ديسكورد"), ("افتحلي سبوتيفاي يا يوبي", "open_app", "سبوتيفاي"),
    ("ممكن تفتح كروم", "open_app", "كروم"), ("عايز ادخل يوتيوب", "open_app", "يوتيوب"),
    ("open steam", "open_app", "steam"), ("افتح فالورانت بسرعه", "open_app", "فالورانت"),
    ("شغل ماين كرافت", "open_app", "ماين كرافت"), ("افطح ديسكورد", "open_app", None),
    ("يوبي افتح الكروم لو سمحت", "open_app", None), ("سبوتيفاي", "open_app", "سبوتيفاي"),
    ("افتح يورو تراك", "open_app", "يورو تراك"), ("launch valorant", "open_app", "valorant"),
    ("هات الفيسبوك", "open_app", None), ("افتح الوورد", "open_app", None),
    # close
    ("اقفل الديسكورد", "close_app", "ديسكورد"), ("قفلي كروم", "close_app", None),
    ("اقفل اللعبة دي فالورانت", "close_app", None), ("close spotify", "close_app", "spotify"),
    ("اكفل ديسكورد", "close_app", None), ("سكر السبوتيفاي", "close_app", None),
    # volume / media / screen
    ("علي الصوت", "system_control", "volume_up"), ("علّي الصوت شويه", "system_control", "volume_up"),
    ("هل السوط شوي", "system_control", "volume_up"), ("الصوت واطي خالص", "system_control", None),
    ("وطي الصوت شويه", "system_control", "volume_down"), ("الصوت عالي قوي", "system_control", "volume_down"),
    ("وطى السوت", "system_control", "volume_down"), ("خلي الصوت خمسين", "system_control", "set_volume"),
    ("الصوت على ٣٠", "system_control", "set_volume"), ("اكتم الصوت", "system_control", "mute"),
    ("اعمل ميوت", "system_control", "mute"), ("وقف الاغنيه", "system_control", "media_play_pause"),
    ("كمل الاغنية", "system_control", "media_play_pause"), ("الاغنيه اللي بعديها", "system_control", "media_next"),
    ("سكيب الاغنيه دي", "system_control", "media_next"), ("رجع الاغنيه اللي فاتت", "system_control", "media_previous"),
    ("علي الاضاءه", "system_control", "brightness_up"), ("الشاشه منوره قوي", "system_control", "brightness_down"),
    ("خد اسكرين شوت", "system_control", "screenshot"), ("صورلي الشاشه", "system_control", "screenshot"),
    ("اقفل الشاشه", "system_control", "lock_screen"), ("فضي الرامات", "system_control", "free_ram"),
    ("اقفل الجهاز", "system_control", "shutdown"), ("اطفي الكمبيوتر", "system_control", "shutdown"),
    ("اعمل ريستارت", "system_control", "restart"),
    # play / search
    ("شغل اغنيه لعمرو دياب", "play_media", None), ("عايز اسمع ويجز", "play_media", None),
    ("شغل سوره الكهف", "play_media", None), ("شغل عمرو دياب", "play_media", None),
    ("ابحث عن سعر الدولار النهارده", "web_search", None), ("دور على وصفة مكرونه", "web_search", None),
    ("دورلي على ماتش الاهلي في يوتيوب", "web_search", None),
    # reminders / later
    ("فكرني اشرب ميه بعد نص ساعه", "set_reminder", 30.0), ("فكرني بعد ساعتين اكلم احمد", "set_reminder", 120.0),
    ("نبهني بعد عشر دقايق", "set_reminder", 10.0), ("اقفل فالورانت بعد ساعه", "schedule_command", 60.0),
    ("اطفي الجهاز بعد نص ساعه", "schedule_command", 30.0),
    # info / pc / modes
    ("الساعه كام دلوقتي", "system_info", None), ("النهارده كام", "system_info", None),
    ("البطاريه فيها كام", "system_info", None), ("افحص جهازي", "pc_command", None),
    ("افتح فولدر التحميلات", "pc_command", None), ("يلا نذاكر", "activate_mode", "study"),
    ("وضع الالعاب", "activate_mode", "gaming"),
    # chatter: must NOT do anything
    ("صباح الفل", None, None), ("ازيك يا يوبي", None, None), ("انت عامل ايه", None, None),
    ("شكرا", None, None), ("انا اسمي كريم", None, None), ("دفعت كتير قوي في تصليح العربيه", None, None),
    ("هما لسه منزلوش التحديث", None, None), ("الموضوع صعب قوي طيب يلا", None, None),
    ("هو فيه ايه يا عم", None, None), ("الاكل النهارده كان حلو", None, None), ("خلاص خلاص", None, None),
    ("وبعدين", None, None), ("يا حبيبي", None, None), ("اشرب ميه", None, None), ("انا تعبان", None, None),
    ("احكيلي نكته", None, None), ("مين كسب الماتش امبارح", None, None), ("شوف العربيه دي بتطير", None, None),
    ("go go go", None, None), ("nice one bro", None, None), ("يلا يا جدعان", None, None),
    ("ارمي الكوره هنا", None, None), ("خش يمين خش يمين", None, None), ("ايه ده يا عم", None, None),
    ("انا جعان قوي", None, None), ("تصبح على خير", None, None),
]


def detail(d):
    a = d.args
    return a.get("name") or a.get("action") or a.get("minutes") or a.get("mode") or a.get("query") or a.get("question") or a.get("command")


class TestLocalBrain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = time.time()
        cls.brain = lb.LocalBrain.train(app_names=sorted(APPS_HERE), app_score=lambda n: 1.0 if n in APPS_HERE else 0.0)
        cls.train_s = time.time() - t

    def test_eval_set(self):
        right = wrong = unsure = chatter_fired = 0
        lines = []
        for text, tool, want in EVAL:
            d = self.brain.understand(text)
            if tool is None:
                if d is not None:
                    chatter_fired += 1
                    lines.append(f"  CHATTER FIRED  {text!r} → {d}")
                continue
            if d is None:
                unsure += 1
                lines.append(f"  unsure         {text!r}  top={self.brain.top(text, 2)}")
            elif d.tool == tool and (want is None or str(detail(d)) == str(want) or str(want) in str(d.args)):
                right += 1
            else:
                wrong += 1
                lines.append(f"  WRONG          {text!r} → {d}  (wanted {tool} {want})")
        cmds = sum(1 for _, t, _ in EVAL if t)
        chat = len(EVAL) - cmds
        print(f"\ntrained in {self.train_s:.1f}s | commands {cmds}: right {right}, unsure {unsure}, WRONG {wrong}"
              f" | chatter {chat}: fired {chatter_fired}")
        print("\n".join(lines))
        self.assertLessEqual(wrong + chatter_fired, 2, "a wrong action is worse than asking")
        self.assertGreaterEqual(right / cmds, 0.85)

    def test_numbers_and_times(self):
        self.assertEqual(lb.parse_number("خلي الصوت خمسين"), 50)
        self.assertEqual(lb.parse_number("الصوت على ٣٠"), 30)
        self.assertEqual(lb.parse_minutes("بعد نص ساعة"), 30)
        self.assertEqual(lb.parse_minutes("بعد ساعة ونص"), 90)
        self.assertEqual(lb.parse_minutes("بعد 5 دقايق"), 5)
        self.assertEqual(lb.parse_minutes("بعد تلات ساعات"), 180)
        self.assertEqual(lb.parse_minutes("in 10 minutes"), 10)
        self.assertIsNone(lb.parse_minutes("فكرني بصلاة العشا"))

    def test_fast(self):
        t = time.perf_counter()
        for _ in range(50):
            self.brain.understand("افتح ديسكورد")
        self.assertLess((time.perf_counter() - t) / 50 * 1000, 30)


class FakeTools:
    schemas = []

    def __init__(self):
        self.ran = []

    def execute(self, name, args):
        import json
        self.ran.append((name, json.loads(args)))
        return "ASK: تقصد ديسكورد؟" if name == "open_app" and "ديس" not in json.loads(args)["name"] else "تمام ✅"


class Broken:
    """A Gemini client whose every call fails (no internet)."""
    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                raise ConnectionError("no internet")


class TestBrainWithoutGemini(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lb = lb.LocalBrain.train(app_names=sorted(APPS_HERE), app_score=lambda n: 1.0 if n in APPS_HERE else 0.0)

    def brain(self, client):
        import brain
        self.tools = FakeTools()
        return brain.Brain(client, "m", self.tools, local=lambda: self.lb)

    def test_no_key_runs_commands_and_explains_chat(self):
        import brain
        b, said = self.brain(None), []
        self.assertEqual(b.run("علي الصوت", on_sentence=said.append), "تمام ✅")
        self.assertEqual(self.tools.ran, [("system_control", {"action": "volume_up"})])
        self.assertEqual(b.run("احكيلي نكته"), brain.NEEDS_KEY)
        self.assertEqual(len(self.tools.ran), 1)                 # chat ran nothing

    def test_tool_questions_are_said_plainly(self):
        b = self.brain(None)
        self.assertEqual(b.run("افتح الكروم"), "تقصد ديسكورد؟")

    def test_no_internet_falls_back_to_local(self):
        b = self.brain(Broken())
        self.assertEqual(b.run("اقفل ديسكورد"), "تمام ✅")
        self.assertEqual(self.tools.ran[0][0], "close_app")
        self.assertIn("مشكلة في الاتصال", b.run("انت عامل ايه"))

    def test_untrained_yet_is_safe(self):
        import brain
        b = brain.Brain(None, "m", FakeTools(), local=lambda: None)
        b._local_wait = 0.2
        self.assertEqual(b.run("علي الصوت"), brain.NOT_READY)        # not "needs a key": it's a command
        failed = brain.Brain(None, "m", FakeTools(), local=lambda: False)
        self.assertEqual(failed.run("علي الصوت"), brain.NEEDS_KEY)

    def test_a_command_waits_for_the_model_still_training(self):
        import threading
        holder = {}
        threading.Timer(0.4, lambda: holder.update(lb=self.lb)).start()
        b = self.brain(None)
        b._local = lambda: holder.get("lb")
        self.assertEqual(b.run("علي الصوت"), "تمام ✅")
        self.assertEqual(self.tools.ran, [("system_control", {"action": "volume_up"})])


if __name__ == "__main__":
    unittest.main(verbosity=1)
