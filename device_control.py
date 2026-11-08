# -*- coding: utf-8 -*-
"""
Device Control — الأوامر الصوتية للفحص الشامل، المتصفح، العمليات، تنظيف الرامات، والأوضاع الذكية (Macros).

match_device_command() بترجع (action_fn, description, needs_confirm) أو None.
"""

import os
import re
import subprocess
import urllib.parse
import webbrowser

from smart_scan import run_full_scan
from browser_reader import search_bookmarks, search_history
from startup_manager import (
    list_startup_items, disable_startup_item, list_running_processes,
)
from launcher_discovery import scan_all_other_launchers


def handle_scan():
    r = run_full_scan(force=True)
    return (
        f"فحصت كل حاجة! لقيت {r['apps_count']} برنامج، "
        f"{r['games_count']} لعبة، "
        f"{len(r['startup_programs'])} برنامج بدء، "
        f"{len(r['wifi_networks'])} شبكة واي فاي."
    )


def handle_find_site(query):
    bm = search_bookmarks(query)
    if bm:
        first = bm[0]
        webbrowser.open(first["url"])
        return f"لقيت bookmark: {first['name']} — فتحته"
    hist = search_history(query)
    if hist:
        first = hist[0]
        webbrowser.open(first["url"])
        return f"لقيت في التاريخ: {first.get('title') or first['url']} — فتحته"
    q = urllib.parse.quote_plus(query)
    webbrowser.open(f"https://www.google.com/search?q={q}")
    return f"مش لاقي — بحثت على جوجل عن '{query}'"


def handle_list_processes():
    procs = list_running_processes(minimal=True)[:10]
    if not procs:
        return "مفيش عمليات شغالة"
    names = [f"{p['name']} ({p['mem_mb']}MB)" for p in procs[:6]]
    return "أعلى استهلاك للرامات: " + " ، ".join(names)


def handle_free_ram():
    """Trim working sets of background processes safely via Windows PSAPI + report freed RAM."""
    import psutil
    before_avail = psutil.virtual_memory().available
    trimmed = 0
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_SET_QUOTA = 0x0100
        for proc in psutil.process_iter(["pid"]):
            try:
                h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, proc.info["pid"])
                if h:
                    if psapi.EmptyWorkingSet(h):
                        trimmed += 1
                    kernel32.CloseHandle(h)
            except Exception:
                continue
    except Exception:
        pass
    after_avail = psutil.virtual_memory().available
    freed_mb = max(0, int((after_avail - before_avail) / (1024 * 1024)))
    mem_pct = psutil.virtual_memory().percent
    if freed_mb > 10:
        return f"فضيت حوالي {freed_mb}MB من الرامات (الاستخدام دلوقتي {mem_pct}%) 🚀"
    return f"نظفت الذاكرة المؤقتة لـ {trimmed} عملية (الرام دلوقتي {mem_pct}%) ✅"


def activate_smart_mode(mode_name):
    """Execute a multi-step smart macro: 'study', 'gaming', or 'cinema'."""
    from system_control import set_volume, set_brightness
    mode = (mode_name or "").lower().strip()

    if mode in ("study", "coding", "work", "مذاكرة", "شغل", "كودينج"):
        set_volume(25)
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "code"], shell=False)
        except Exception:
            pass
        return "فعلت مود المذاكرة والكودينج 💻 (فتحت VS Code وهديت الصوت لـ 25%)"

    if mode in ("gaming", "game", "جيمينج", "لعب"):
        set_volume(80)
        handle_free_ram()
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "discord:"], shell=False)
        except Exception:
            pass
        return "فعلت مود الجيمينج 🎮 (فضيت الرامات، فتحت ديسكورد، وظبطت الصوت 80%)"

    if mode in ("cinema", "chill", "movie", "سينما", "روقان", "راحة"):
        set_volume(70)
        set_brightness(40)
        webbrowser.open("https://www.netflix.com")
        return "فعلت مود السينما والروقان 🍿 (فتحت نتفليكس وهديت الإضاءة)"

    return f"مش عارف المود '{mode_name}'"


def handle_list_startup():
    items = list_startup_items()
    if not items:
        return "مفيش برامج بدء"
    names = [i["name"] for i in items[:8]]
    return f"عندك {len(items)} برنامج بيشتغل مع الويندوز: " + ", ".join(names)


def handle_disable_startup(name_query):
    q = name_query.lower().strip()
    for item in list_startup_items():
        if q in item["name"].lower():
            _, msg = disable_startup_item(item)
            return msg
    return f"مش لاقي برنامج اسمه '{name_query}'"


def handle_kill_process(name_query):
    import psutil
    q = name_query.lower().strip()
    killed = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if q in (proc.info["name"] or "").lower():
                proc.kill()
                killed += 1
        except Exception:
            pass
    return f"قفلت {killed} عملية" if killed else f"مفيش عملية اسمها '{name_query}'"


def handle_list_other_launcher_games():
    games = scan_all_other_launchers()
    if not games:
        return "مفيش ألعاب من launchers تانية"
    return f"لقيت {len(games)} لعبة: " + ", ".join(list(games.keys())[:10])


def match_device_command(command):
    cmd = (command or "").lower().strip()
    if not cmd:
        return None

    # 1. Smart Modes / Macros
    if any(p in cmd for p in [
        "فعل مود المذاكرة", "فعل مود الكودينج", "مود المذاكرة", "مود الكودينج",
        "يلا نشتغل", "جهز الجهاز للشغل", "وضع التركيز",
    ]):
        return (lambda: activate_smart_mode("study"), "تفعيل مود المذاكرة والكودينج", False)

    if any(p in cmd for p in [
        "فعل مود الجيمينج", "مود الجيمينج", "يلا نلعب", "حول الجهاز لوضع الأداء العالي",
        "وضع اللعب", "مود اللعب",
    ]):
        return (lambda: activate_smart_mode("gaming"), "تفعيل مود الجيمينج", False)

    if any(p in cmd for p in [
        "فعل مود السينما", "شغل مود السينما", "مود السينما", "شغل وضع الراحة",
        "مود الروقان",
    ]):
        return (lambda: activate_smart_mode("cinema"), "تفعيل مود السينما", False)

    # 2. Free RAM / Memory optimization
    if any(p in cmd for p in [
        "فضي الرامات", "نضف الرامات", "سرع الجهاز", "الجهاز تقيل",
        "امسح الملفات المؤقتة",
    ]):
        return (handle_free_ram, "تنظيف وتفريغ الرامات", False)

    # 3. Full scan
    if any(p in cmd for p in [
        "افحص كل حاجة", "افحص كل حاجه", "فحص شامل", "افحص الجهاز كله",
        "افحص الجهاز كلو", "افحص كل حاجه علي الجهاز",
    ]):
        return (handle_scan, "فحص شامل للجهاز", False)

    # 4. Find website (bookmarks/history)
    m = re.match(
        r"(?:فين|دور على|افتح)\s+(?:موقع|سايت|bookmark|بوكمارك)\s+(.+)", cmd
    )
    if m:
        q = m.group(1).strip()
        return (lambda x=q: handle_find_site(x), f"بحث عن موقع {q}", False)

    # 5. List processes / heavy RAM consumers
    if any(p in cmd for p in [
        "ايه اللي شغال", "إيه اللي شغال", "العمليات الشغالة",
        "المهام الشغالة", "ايه العمليات", "ساحب رامات",
    ]):
        return (handle_list_processes, "عرض العمليات الشغالة", False)

    # 6. List startup items
    if any(p in cmd for p in [
        "برامج البدء", "الستارت اب", "بيشتغل مع الويندوز", "startup",
    ]):
        return (handle_list_startup, "عرض برامج البدء", False)

    # 7. Disable a startup item
    m = re.match(
        r"(?:اوقف|عطل|الغي)\s+(.+?)\s+(?:من الستارت اب|من بدء التشغيل)", cmd
    )
    if m:
        name = m.group(1).strip()
        return (
            lambda n=name: handle_disable_startup(n),
            f"تعطيل {name} من الستارت اب",
            True,
        )

    # 8. Kill process
    m = re.match(
        r"(?:اقفل|kill|اقتل)\s+(?:العملية|عملية|process)\s+(.+)", cmd
    )
    if m:
        name = m.group(1).strip()
        return (
            lambda n=name: handle_kill_process(n),
            f"قفل عملية {name}",
            True,
        )

    # 9. List other launchers' games
    if any(p in cmd for p in [
        "العاب باتل نت", "العاب يوبيسوفت", "العاب جوج",
        "العاب ubisoft", "العاب ea", "العاب itch",
    ]):
        return (handle_list_other_launcher_games, "عرض ألعاب الـ launchers التانية", False)

    return None