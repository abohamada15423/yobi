# -*- coding: utf-8 -*-
"""
Island widgets — اللي الجزيرة بتعرضه من الجهاز: المزيكا، الصوت، السطوع، المعالج
والرامات والبطارية، ولغة الكيبورد و Caps Lock.

Python reads Windows; the island (island/island.js) decides when to show it.
Every reader is optional: if one API is missing, that widget simply stays quiet.
"""

import asyncio
import base64
import ctypes
import datetime
import io
import queue
import threading
import time
from ctypes import wintypes

try:
    import psutil
except Exception:          # pragma: no cover
    psutil = None

# primary language id (low 10 bits of the layout) -> name, badge
LANGS = {
    0x01: ("العربية", "ع"), 0x09: ("English", "EN"), 0x0c: ("Français", "FR"),
    0x07: ("Deutsch", "DE"), 0x0a: ("Español", "ES"), 0x10: ("Italiano", "IT"),
    0x1f: ("Türkçe", "TR"), 0x29: ("فارسی", "فا"), 0x19: ("Русский", "RU"),
}
APP_NAMES = {
    "spotify": "Spotify", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox",
    "308046b0af4a39cb": "Firefox", "vlc": "VLC", "zunemusic": ("مشغل الوسائط", "Media Player"),
    "microsoft.media.player": ("مشغل الوسائط", "Media Player"), "brave": "Brave", "opera": "Opera",
    "applemusic": "Apple Music", "anghami": ("أنغامي", "Anghami"), "youtube music": "YouTube Music",
    "electron": ("يوبي", "Yobi"),   # (Arabic, English) where the name differs
}
LOW_BATTERY = 20

_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None


def app_label(app_id):
    """'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify' -> 'Spotify'."""
    a = (app_id or "").lower()
    from island_tools import tr
    for key, name in APP_NAMES.items():
        if key in a:
            return tr(*name) if isinstance(name, tuple) else name
    tail = (app_id or "").split("!")[-1]
    tail = tail[:-4] if tail.lower().endswith(".exe") else tail
    return tail.split("_")[0].split(".")[-1][:24] or tr("مشغل", "Player")


def same_app(app_id, exe_name):
    """Is the media player the window in front?"""
    a = (app_id or "").lower()
    stem = (exe_name or "").lower().removesuffix(".exe")
    if not a or not stem or len(stem) < 3:
        return False
    if a == "308046b0af4a39cb":
        return stem == "firefox"
    return stem in a or a.split("!")[-1].removesuffix(".exe") in stem


def foreground():
    """(hwnd, pid, exe name, keyboard layout lang id) of the window in front."""
    if _user32 is None:
        return 0, 0, "", 0
    hwnd = _user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    tid = _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    kl = _user32.GetKeyboardLayout(tid) & 0xFFFF
    name = ""
    if psutil is not None and pid.value:
        try:
            name = psutil.Process(pid.value).name()
        except Exception:
            pass
    return hwnd, pid.value, name, kl


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


def foreground_fullscreen():
    """True while a game or video covers the whole screen."""
    if _user32 is None:
        return False
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return False
    cls = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):      # the desktop itself
        return False
    r, mi = _RECT(), _MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    if not _user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    if not _user32.GetMonitorInfoW(_user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


def art_data_url(raw, size=112):
    """Shrink the player's artwork to a small JPEG data URL."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((size, size))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return None


class IslandWidgets:
    FAST_S = 0.1          # volume, caps, keyboard, music level
    MEDIA_S = 1.0
    STATS_S = 2.0

    def __init__(self, send, log=print):
        self._send = send
        self._log = log
        self._stop = threading.Event()
        self._panel_open = threading.Event()
        self._cmds = queue.Queue()
        self.media_playing = False
        self.media_front = False
        self._last_media = None
        self._art_key = None

    # ── lifecycle ─────────────────────────────────────────────
    def start(self):
        for target, name in ((self._fast_loop, "island-fast"), (self._media_thread, "island-media"),
                             (self._stats_loop, "island-stats"), (self._brightness_loop, "island-bright")):
            threading.Thread(target=target, name=name, daemon=True).start()

    def stop(self):
        self._stop.set()

    def handle(self, msg):
        """Messages from the window (called on the island's main thread: keep it quick)."""
        t = msg.get("t")
        if t == "panel":
            if msg.get("open"):
                self._panel_open.set()
                threading.Thread(target=self._push_stats, daemon=True).start()
            else:
                self._panel_open.clear()
        elif t == "media" and msg.get("cmd") in ("toggle", "next", "prev", "seek"):
            self._cmds.put((msg["cmd"], msg.get("pos")))

    # ── volume, caps lock, keyboard language, music level ────
    def _fast_loop(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        vol = meter = None
        vol_at = 0.0
        last_vol = last_caps = last_lang = last_pid = None
        last_music = -1.0
        while not self._stop.wait(self.FAST_S):
            now = time.monotonic()
            # volume (re-acquire the device every few seconds if it vanished)
            if vol is None and now - vol_at > 5:
                vol_at = now
                vol, meter = self._audio_interfaces()
            if vol is not None:
                try:
                    v = (round(vol.GetMasterVolumeLevelScalar() * 100), bool(vol.GetMute()))
                    if last_vol is not None and v != last_vol:
                        self._send({"t": "hud", "kind": "volume", "value": v[0], "muted": v[1]})
                    last_vol = v
                except Exception:
                    vol = meter = None
            # caps lock
            if _user32 is not None:
                caps = bool(_user32.GetKeyState(0x14) & 1)
                if last_caps is not None and caps != last_caps:
                    self._send({"t": "hud", "kind": "caps", "on": caps})
                last_caps = caps
                # keyboard language: per-app layouts change with focus, so only count
                # a switch inside the same app
                try:
                    _, pid, _, kl = foreground()
                    lang = kl & 0x3FF
                    if lang and last_lang is not None and lang != last_lang and pid == last_pid:
                        name, badge = LANGS.get(lang, (f"0x{kl:04x}", "⌨"))
                        self._send({"t": "hud", "kind": "kbd", "name": name, "badge": badge})
                    if lang:
                        last_lang, last_pid = lang, pid
                except Exception:
                    pass
            # music level drives the idle line while something plays
            if meter is not None and self.media_playing and not self.media_front:
                try:
                    lv = round(min(1.0, float(meter.GetPeakValue()) * 1.6), 2)
                    if abs(lv - last_music) >= 0.03:
                        self._send({"t": "music_level", "v": lv})
                        last_music = lv
                except Exception:
                    meter = None
            elif last_music != 0.0:
                last_music = 0.0

    @staticmethod
    def _audio_interfaces():
        try:
            import system_control as sc
            vol = sc._get_endpoint_volume()
        except Exception:
            vol = None
        meter = None
        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            dev = AudioUtilities.GetSpeakers()
            dev = getattr(dev, "_dev", dev)
            iface = dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
            meter = ctypes.cast(iface, ctypes.POINTER(IAudioMeterInformation))
        except Exception:
            pass
        return vol, meter

    # ── brightness (only screens Windows reports itself: laptops) ──
    def _brightness_loop(self):
        try:
            import screen_brightness_control as sbc
            wmi = [m for m in sbc.list_monitors_info() if "wmi" in str(m.get("method", "")).lower()]
        except Exception:
            return
        if not wmi:
            return          # external monitors: polling DDC/CI is slow and can flicker, skip
        last = None
        while not self._stop.wait(1.0):
            try:
                b = int(sbc.get_brightness(display=wmi[0]["index"])[0])
            except Exception:
                continue
            if last is not None and b != last:
                self._send({"t": "hud", "kind": "brightness", "value": b})
            last = b

    # ── CPU, RAM, battery ─────────────────────────────────────
    def _stats_loop(self):
        if psutil is None:
            return
        psutil.cpu_percent(None)
        last_plugged = last_low = None
        tick = 0
        while not self._stop.wait(self.STATS_S):
            tick += 1
            if self._panel_open.is_set():
                self._push_stats()
            if tick % 10 == 0:                       # battery toasts every ~20 s
                bat = psutil.sensors_battery()
                if bat is None:
                    continue
                low = bat.percent <= LOW_BATTERY and not bat.power_plugged
                if last_plugged is not None and bat.power_plugged != last_plugged:
                    self._send({"t": "hud", "kind": "battery", "value": round(bat.percent),
                                "plugged": bool(bat.power_plugged), "low": False})
                elif low and last_low is False:
                    self._send({"t": "hud", "kind": "battery", "value": round(bat.percent),
                                "plugged": False, "low": True})
                last_plugged, last_low = bat.power_plugged, low

    def _push_stats(self):
        try:
            vm = psutil.virtual_memory()
            bat = psutil.sensors_battery()
            self._send({
                "t": "stats", "cpu": round(psutil.cpu_percent(None) / 100, 3),
                "ram": round(vm.percent / 100, 3),
                "ram_used": vm.used, "ram_total": vm.total,
                "battery": None if bat is None else {"percent": round(bat.percent),
                                                     "plugged": bool(bat.power_plugged)},
            })
        except Exception:
            pass

    # ── media (Windows media session) ─────────────────────────
    def _media_thread(self):
        try:
            asyncio.run(self._media_loop())
        except Exception as e:
            self._log(f"ℹ️ المزيكا على الجزيرة مش شغالة: {str(e)[:80]}")

    async def _media_loop(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MM
        mgr = await MM.request_async()
        last_sent = 0.0
        while not self._stop.is_set():
            try:
                cmd = self._cmds.get_nowait()
            except queue.Empty:
                cmd = None
            if cmd is not None:
                await self._media_command(mgr, *cmd)
                await asyncio.sleep(0.35)          # let the player update before reading
            snap = await self._media_snapshot(mgr)
            key = {k: v for k, v in snap.items() if k not in ("pos", "art")}
            now = time.monotonic()
            if key != self._last_media or "art" in snap or cmd is not None or now - last_sent > 5:
                self._send(snap)
                self._last_media, last_sent = key, now
            self.media_playing = bool(snap.get("playing"))
            self.media_front = bool(snap.get("front"))
            # wake early for a click, otherwise poll once a second
            for _ in range(int(self.MEDIA_S / 0.05)):
                if self._stop.is_set() or not self._cmds.empty():
                    break
                await asyncio.sleep(0.05)

    async def _media_snapshot(self, mgr):
        s = mgr.get_current_session()
        if s is None:
            self._art_key = None
            return {"t": "media", "has": False}
        props = await s.try_get_media_properties_async()
        info = s.get_playback_info()
        tl = s.get_timeline_properties()
        playing = int(info.playback_status) == 4          # Playing
        dur = tl.end_time.total_seconds() if tl.end_time else 0.0
        pos = tl.position.total_seconds() if tl.position else 0.0
        if playing and tl.last_updated_time:
            try:
                pos += (datetime.datetime.now(datetime.timezone.utc) - tl.last_updated_time).total_seconds()
            except Exception:
                pass
        app_id = s.source_app_user_model_id
        _, _, exe, _ = foreground()
        snap = {
            "t": "media", "has": True, "playing": playing,
            "title": props.title or "", "artist": props.artist or props.album_artist or "",
            "app": app_label(app_id), "front": same_app(app_id, exe),
            "pos": round(max(0.0, min(pos, dur or pos)), 1), "dur": round(dur, 1),
            "seek": bool(info.controls.is_playback_position_enabled and dur > 0),
        }
        art_key = (app_id, snap["title"], snap["artist"])
        if art_key != self._art_key:
            self._art_key = art_key
            snap["art"] = await self._read_art(props)
        return snap

    @staticmethod
    async def _read_art(props):
        if props.thumbnail is None:
            return None
        try:
            from winrt.windows.storage.streams import Buffer, InputStreamOptions
            stream = await props.thumbnail.open_read_async()
            size = min(int(stream.size), 4 * 1024 * 1024)
            buf = await stream.read_async(Buffer(size), size, InputStreamOptions.READ_AHEAD)
            return art_data_url(bytes(buf))
        except Exception:
            return None

    @staticmethod
    async def _media_command(mgr, cmd, pos=None):
        s = mgr.get_current_session()
        try:
            if s is None:
                raise RuntimeError("no session")
            if cmd == "toggle":
                await s.try_toggle_play_pause_async()
            elif cmd == "next":
                await s.try_skip_next_async()
            elif cmd == "prev":
                await s.try_skip_previous_async()
            elif cmd == "seek" and pos is not None:
                await s.try_change_playback_position_async(int(max(0.0, float(pos)) * 10_000_000))
        except Exception:
            # no session API: fall back to the media keys yopi already uses
            try:
                import system_control as sc
                {"toggle": sc.media_play_pause, "next": sc.media_next,
                 "prev": sc.media_previous}.get(cmd, lambda: None)()
            except Exception:
                pass
