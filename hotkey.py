# -*- coding: utf-8 -*-
"""The wake key: watched by asking Windows which keys are down, 50 times a second.

Not a keyboard hook (the `keyboard` library): Windows silently removes a hook whose owner is
busy for a moment, and that library turns a key name into scan codes through the active
keyboard layout, so on an Arabic + English PC "[" became the F key. A key here is a Windows
virtual-key code: the same physical key in every layout. The key still reaches the app in
front; nothing is swallowed.
"""
import ctypes
import threading
import time

MODS = {"ctrl": (0x11,), "alt": (0x12,), "shift": (0x10,), "windows": (0x5B, 0x5C)}
KEYS = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "page up": 0x21, "page down": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "pause": 0x13, "scroll lock": 0x91, "caps lock": 0x14, "num lock": 0x90, "print screen": 0x2C, "menu": 0x5D,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "backslash": 0xDC, "comma": 0xBC, ".": 0xBE, "/": 0xBF,
    "semicolon": 0xBA, "quote": 0xDE, "backquote": 0xC0,
    "decimal": 0x6E, "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D, "divide": 0x6F,
}
KEYS.update({f"f{i}": 0x6F + i for i in range(1, 25)})
KEYS.update({f"num {i}": 0x60 + i for i in range(10)})
KEYS.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})


def parse(name):
    """"ctrl+alt+y" → (frozenset of modifier names, virtual-key code); None when it isn't a wake key."""
    if not isinstance(name, str) or not name or len(name) > 40:
        return None
    *mods, key = name.split("+")
    if key not in KEYS or len(set(mods)) != len(mods) or not set(mods) <= set(MODS):
        return None
    return frozenset(mods), KEYS[key]


def _down(vk):
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


class Watcher:
    """Calls `on_press` once each time the key goes down with exactly its modifiers held."""

    def __init__(self, on_press, down=_down, interval=0.02):
        self._on_press, self._is_down, self._interval = on_press, down, interval
        self._key = None            # (mods, vk)
        self._was = False
        self._stop = threading.Event()
        self._thread = None

    def set(self, name):
        """Watch this key from now on ("" or None: none). False when the name isn't a key."""
        key = parse(name) if name else None
        if name and key is None:
            return False
        self._key, self._was = key, True     # True: a key already held when chosen doesn't fire
        if key and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="wake-key", daemon=True)
            self._thread.start()
        return True

    def poll(self):
        key = self._key
        if key is None:
            return
        mods, vk = key
        now = self._is_down(vk) and all(any(self._is_down(v) for v in vks) == (m in mods) for m, vks in MODS.items())
        if now and not self._was:
            self._on_press()
        self._was = now

    def _run(self):
        while not self._stop.wait(self._interval):
            try:
                self.poll()
            except Exception:
                time.sleep(1)       # never let the watcher die

    def stop(self):
        self._stop.set()
