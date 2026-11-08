# -*- coding: utf-8 -*-
"""
System Tray — أيقونة يوبي في شريط المهام.

Provides a system tray icon with controls:
  • تشغيل/إيقاف الاستماع
  • تشغيل/إيقاف الرد الصوتي (TTS)
  • إعادة فحص البرامج
  • خروج

Uses pystray + Pillow to draw a minimal icon.
"""

import json
import os
import threading
import sys

try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except ImportError:
    _HAS_TRAY = False


def _initial_voice_state():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool((data.get("replies") or {}).get("voice", False))
    except Exception:
        return False


def _create_icon_image():
    """Draw a minimal 'Y' icon for Yobi in the system tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle — dark with green accent
    draw.ellipse([2, 2, size - 2, size - 2], fill=(15, 15, 23, 255))
    draw.ellipse([4, 4, size - 4, size - 4], fill=(20, 25, 35, 255))

    # Green "Y" letter
    cx, cy = size // 2, size // 2
    draw.line([(16, 14), (cx, cy)], fill=(74, 222, 128, 255), width=4)
    draw.line([(size - 16, 14), (cx, cy)], fill=(74, 222, 128, 255), width=4)
    draw.line([(cx, cy), (cx, size - 14)], fill=(74, 222, 128, 255), width=4)

    # Small green dot ("alive" indicator)
    draw.ellipse([size - 18, size - 18, size - 8, size - 8],
                 fill=(74, 222, 128, 255))

    return img


class YobiTray:
    """System tray icon with controls for Yobi."""

    def __init__(self, on_toggle_listen=None, on_toggle_tts=None,
                 on_refresh_apps=None, on_quit=None, initial_tts=None):
        if not _HAS_TRAY:
            self._icon = None
            return

        self._on_toggle_listen = on_toggle_listen
        self._on_toggle_tts = on_toggle_tts
        self._on_refresh_apps = on_refresh_apps
        self._on_quit = on_quit

        self._listening = True
        self._tts_on = _initial_voice_state() if initial_tts is None else bool(initial_tts)

        self._icon = pystray.Icon(
            name="Yobi",
            icon=_create_icon_image(),
            title="Yobi — مساعدك الصوتي 🎤",
            menu=self._build_menu(),
        )

    def _build_menu(self):
        """Build the tray context menu."""
        return pystray.Menu(
            pystray.MenuItem(
                lambda _: "⏸️ إيقاف الاستماع" if self._listening else "▶️ تشغيل الاستماع",
                self._toggle_listen,
            ),
            pystray.MenuItem(
                lambda _: "🔇 إيقاف الرد الصوتي" if self._tts_on else "🔊 تشغيل الرد الصوتي",
                self._toggle_tts,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔄 تحديث البرامج", self._refresh_apps),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ خروج", self._quit),
        )

    def _toggle_listen(self, icon, item):
        new_state = None
        if self._on_toggle_listen:
            new_state = self._on_toggle_listen()
        if isinstance(new_state, bool):
            self._listening = new_state
        else:
            self._listening = not self._listening
        self._icon.update_menu()

    def _toggle_tts(self, icon, item):
        new_state = None
        if self._on_toggle_tts:
            new_state = self._on_toggle_tts()
        if isinstance(new_state, bool):
            self._tts_on = new_state
        else:
            self._tts_on = not self._tts_on
        self._icon.update_menu()

    def _refresh_apps(self, icon, item):
        if self._on_refresh_apps:
            self._on_refresh_apps()

    def _quit(self, icon, item):
        icon.stop()
        if self._on_quit:
            self._on_quit()
        else:
            os._exit(0)

    def start(self):
        if not self._icon:
            return
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def notify(self, title, message):
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass