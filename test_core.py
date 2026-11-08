# -*- coding: utf-8 -*-
"""Verification tests for Yobi's pure-logic core (v7.3 Pro).

Run directly:  python test_core.py
"""
import sys
import traceback

from app_scanner import resolve_target
from system_control import match_system_command
from device_control import match_device_command
from file_ops import match_file_command
from natural_qa import is_question, try_system_answer
from smart_suggestions import is_suggestion_request
from media_handler import handle_media_or_search
from transliteration import normalize_transcription
from aliases import ARABIC_TO_CANONICAL, normalize_name
from context_memory import ContextMemory
from addressing import AddressedClassifier
from scheduler import TaskScheduler
import target_resolver as tr
from smart_open import exe_matches


class MockAgent:
    def __init__(self, websites, local_apps, installed_apps, games):
        self.websites = websites
        self.local_apps = local_apps
        self.installed_apps = installed_apps
        self.games = games

    def open_target(self, target):
        return f"opened_{target}"


def test_system_commands():
    for cmd in [
        "علي الصوت", "وطي الصوت", "علي شويه", "وطي شويه",
        "اكتم الصوت", "الغي كتم الصوت", "علي الصوت للاخر",
        "وقف الاغاني", "التراك اللي بعده", "الاغنية اللي فاتت",
        "خلي الصوت 50%", "خلي الصوت للنص", "ظبط السطوع على 70",
    ]:
        assert match_system_command(cmd) is not None, f"Failed match: {cmd}"

    mute_fn, mute_desc, _ = match_system_command("اكتم الصوت")
    unmute_fn, unmute_desc, _ = match_system_command("الغي كتم الصوت")
    assert mute_desc == "كتم الصوت", mute_desc
    assert unmute_desc == "إلغاء كتم الصوت", unmute_desc
    assert mute_fn is not unmute_fn

    _, vol50_desc, _ = match_system_command("خلي الصوت للنص")
    assert vol50_desc == "ضبط الصوت على 50%", vol50_desc


def test_device_commands():
    for cmd, expected_desc in [
        ("فضي الرامات", "تنظيف وتفريغ الرامات"),
        ("فعل مود المذاكرة", "تفعيل مود المذاكرة والكودينج"),
        ("فعل مود الجيمينج", "تفعيل مود الجيمينج"),
        ("شغل مود السينما", "تفعيل مود السينما"),
        ("ايه اللي شغال", "عرض العمليات الشغالة"),
    ]:
        m = match_device_command(cmd)
        assert m is not None and m[1] == expected_desc, (cmd, m)


def test_file_commands():
    m1 = match_file_command("افتح آخر ملف كنت شغال عليه")
    assert m1 is not None and m1[1] == "فتح آخر ملف", m1
    m2 = match_file_command("اعمل فولدر اسمه مشروع التخرج")
    assert m2 is not None and "مشروع التخرج" in m2[1], m2


def test_natural_qa():
    assert is_question("عايز افتح التيرمينال") is False
    assert is_question("ممكن تفتح وينرار") is False
    assert is_question("قفل الكمبيوتر") is False
    assert is_question("الساعة كام") is True
    assert is_question("كام الرام فاضي") is True
    assert is_question("الجهاز شغال بقاله قد ايه") is True
    assert try_system_answer("الساعة كام") is not None
    assert try_system_answer("النهاردة كام") is not None


def test_alias_and_transliteration():
    assert normalize_name("Rocket League®") == "rocket league"
    assert normalize_name("The Last of Us™ Part I") == "the last of us part i"
    assert "spotify" in normalize_transcription("افتح سبوتيفاي", [])
    assert "euro truck simulator 2" in normalize_transcription("افتح يورو", [])


def test_target_resolver():
    cat = tr.Catalog(
        websites={"youtube": "https://www.youtube.com"},
        local_apps={"discord": "discord"},
        games={"euro truck simulator 2": "game:ets2", "assetto corsa competizione": "game:acc"},
        installed={"excel": "C:/Office/EXCEL.EXE"},
    )
    for phrase, expected in [
        ("افتح يورو", "euro truck simulator 2"),
        ("افتح júru", "euro truck simulator 2"),
        ("شغل اسيتو", "assetto corsa competizione"),
        ("افتح excel", "excel"),
    ]:
        r = tr.resolve(cat, phrase, utterance=phrase)
        assert r.status == "ok" and r.best.display == expected, (phrase, r)

    assert exe_matches("euro truck simulator 2", "C:/Games/eurotrucks2.exe") is True
    assert exe_matches("ساكه", "C:/Games/SACKE.exe") is False


def test_context_and_addressing():
    cm = ContextMemory()
    cm.record("open", "euro truck simulator 2", "تم")
    assert cm.resolve_pronoun("في دي لسيات ما تنزلها ايش.") is None
    assert cm.resolve_pronoun("اقفلها") == "euro truck simulator 2"
    assert cm.resolve_pronoun("افتحه تاني") == "euro truck simulator 2"

    clf = AddressedClassifier(llm_client=None)
    assert clf.is_addressed("يا يوبي افتح ديسكورد") is True
    assert clf.is_addressed("الساعة كام دلوقتي") is True


def test_scheduler():
    s = TaskScheduler(lambda m: None, lambda c: None)
    for cmd in [
        "فكرني اروح الجيم بعد ساعة",
        "فكرني أروح الجيم كمان ساعة",
        "اظبط تايمر لمدة نص ساعة",
        "فكرني بعد عشر دقايق",
        "اقفل اللعبة كمان تلت ساعة",
    ]:
        assert s.has_scheduled_intent(cmd), f"Scheduler missed: {cmd}"


def test_media_handler():
    agent = MockAgent(
        websites={"netflix": "https://netflix.com", "كورة": "https://kooora.com"},
        local_apps={"spotify": "C:/fake/spotify.exe"},
        installed_apps={},
        games={},
    )
    for phrase, expected in [
        ("شغل اغنية عمرو دياب", "يوتيوب"),
        ("شغل فيلم interstellar", "interstellar"),
        ("ابحث عن بايثون", "بايثون"),
        ("افتح موقع كورة", "كورة"),
    ]:
        handled, msg = handle_media_or_search(phrase, agent)
        assert handled and expected in msg, (phrase, handled, msg)


def run_tests():
    tests = [
        ("system_commands", test_system_commands),
        ("device_commands", test_device_commands),
        ("file_commands", test_file_commands),
        ("natural_qa", test_natural_qa),
        ("alias_and_transliteration", test_alias_and_transliteration),
        ("target_resolver", test_target_resolver),
        ("context_and_addressing", test_context_and_addressing),
        ("scheduler", test_scheduler),
        ("media_handler", test_media_handler),
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"✅ {name}")
        except AssertionError as e:
            failures += 1
            print(f"❌ {name}: {e}")
        except Exception:
            failures += 1
            print(f"💥 {name}: crashed")
            traceback.print_exc()

    if failures:
        print(f"\n{failures} test(s) failed.")
        sys.exit(1)
    print("\nAll 9 core test suites passed 100%!")


if __name__ == "__main__":
    run_tests()