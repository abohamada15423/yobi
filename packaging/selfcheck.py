# -*- coding: utf-8 -*-
"""Run with the build's own Python to prove it stands alone:

    payload/runtime/python.exe -s -E payload/app/../../selfcheck.py <app dir>

Imports every app module and the libraries behind each feature, and checks that nothing
comes from outside the build (e.g. this PC's own Python)."""
import importlib
import os
import sys
import traceback

app = os.path.abspath(sys.argv[1])
build = os.path.dirname(os.path.dirname(app))          # .../payload
sys.path.insert(0, app)
os.chdir(app)
os.environ["YOBI_SELFCHECK"] = "1"

LIBS = ["numpy", "scipy.signal", "sounddevice", "webrtcvad", "speech_recognition", "faster_whisper", "ctranslate2",
        "av", "onnxruntime", "openwakeword.model", "edge_tts", "pygame", "groq", "dotenv", "sklearn", "joblib",
        "arabic_reshaper", "bidi.algorithm", "psutil", "win32api", "win32gui", "pythoncom", "comtypes", "pycaw.pycaw",
        "keyboard", "pyautogui", "pyperclip", "pygetwindow", "uiautomation", "screen_brightness_control", "keyring",
        "customtkinter", "pystray", "PIL.ImageGrab", "yaml", "winrt.windows.media.control", "icalendar",
        "recurring_ical_events", "tkinter", "sqlite3", "ssl", "ctypes", "GPUtil", "requests", "httpx"]
SKIP_APP = {"agent", "selfcheck"}                       # agent runs the whole assistant on import

bad = []
for m in LIBS:
    try:
        importlib.import_module(m)
    except Exception as e:
        bad.append(f"lib {m}: {type(e).__name__}: {e}")
for f in sorted(os.listdir(app)):
    if f.endswith(".py") and f[:-3] not in SKIP_APP:
        try:
            importlib.import_module(f[:-3])
        except SystemExit:
            pass
        except Exception as e:
            bad.append(f"app {f}: {type(e).__name__}: {e}")
            traceback.print_exc()

outside = sorted({os.path.dirname(getattr(m, "__file__", "") or "") for m in list(sys.modules.values())
                  if getattr(m, "__file__", None) and not os.path.abspath(m.__file__).lower().startswith(build.lower())})
outside = [p for p in outside if p and "windows" not in p.lower() and p != os.path.dirname(os.path.abspath(__file__))]

print("sys.prefix", sys.prefix)
print("modules loaded:", len(sys.modules))
if outside:
    print("LOADED FROM OUTSIDE THE BUILD:\n  " + "\n  ".join(outside))
for b in bad:
    print("FAIL", b)
print("SELFCHECK", "OK" if not bad and not outside else "FAILED")
