# -*- coding: utf-8 -*-
"""Start Yobi with no console window (the friends' build runs this; `python agent.py` still works).

  • one Yobi at a time (a second start just says it's already running)
  • everything Yobi prints goes to logs/yobi.log (the old one is kept as yobi.old.log)
  • a crash at startup shows a message instead of vanishing silently
  • --keys opens the API keys window again
"""
import ctypes
import os
import runpy
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
TITLE = "Yobi"
MB_ICONINFO, MB_ICONERROR, MB_RTL = 0x40, 0x10, 0x00180000   # RTL reading + right-aligned


def message(text, icon=MB_ICONINFO):
    ctypes.windll.user32.MessageBoxW(0, text, TITLE, icon | MB_RTL)


def open_log():
    logs = os.path.join(HERE, "logs")
    os.makedirs(logs, exist_ok=True)
    path = os.path.join(logs, "yobi.log")
    try:
        if os.path.getsize(path) > 5 * 2**20:
            os.replace(path, os.path.join(logs, "yobi.old.log"))
    except OSError:
        pass
    f = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
    f.write(f"\n===== Yobi {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    return f, path


def main():
    os.chdir(HERE)
    sys.path.insert(0, HERE)
    log, log_path = open_log()
    sys.stdout = sys.stderr = log

    if "--keys" in sys.argv:
        from first_run import ask_keys
        if ask_keys(os.path.join(HERE, ".env"), force=True) is not None:
            message("تمام، المفاتيح اتحفظت. اقفل يوبي وافتحه تاني عشان يستخدمها.")
        return

    # one Yobi at a time: two would fight over the mic, the hotkey and the island
    # use_last_error: a plain GetLastError() can be overwritten by ctypes before we read it
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, "Local\\YobiAssistant")
    if ctypes.get_last_error() == 183:                        # ERROR_ALREADY_EXISTS
        message("يوبي شغال بالفعل. دوس زرار النداء وكلّمه.")
        return

    sys.argv = [os.path.join(HERE, "agent.py")]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        message("يوبي وقف بسبب خطأ.\n\nالتفاصيل في الملف ده (ابعته لصاحب البرنامج):\n" + log_path, MB_ICONERROR)


if __name__ == "__main__":
    main()
