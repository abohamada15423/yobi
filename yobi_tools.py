# -*- coding: utf-8 -*-
"""
Yobi Tools — الأدوات اللي العقل الجديد (brain.py) بيستخدمها.

Supports:
  • open_app / close_app (via v7 smart_open & LearningGuard)
  • system_control (including exact volume/brightness percentage 0..100)
  • activate_mode (study / gaming / cinema macros)
  • play_media / web_search / set_reminder / schedule_command
  • pc_command (files, folders, RAM cleanup, startup, processes)
  • system_info (time, date, battery, RAM, CPU, GPU, disk, IP, uptime)
  • look_at_screen / do_on_screen (vision agent v2.1)
"""

import json
import urllib.parse
import webbrowser

import system_control as sc
from device_control import match_device_command, activate_smart_mode, handle_free_ram
from file_ops import match_file_command
from media_handler import handle_media_or_search
from natural_qa import try_system_answer


def _fn(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


_SYSTEM_ACTIONS = {
    "volume_up": (sc.volume_up, False),
    "volume_down": (sc.volume_down, False),
    "volume_max": (sc.volume_max, False),
    "volume_min": (sc.volume_min, False),
    "set_volume": (sc.set_volume, False),
    "mute": (sc.volume_mute, False),
    "unmute": (sc.volume_unmute, False),
    "media_play_pause": (sc.media_play_pause, False),
    "media_next": (sc.media_next, False),
    "media_previous": (sc.media_previous, False),
    "brightness_up": (sc.brightness_up, False),
    "brightness_down": (sc.brightness_down, False),
    "set_brightness": (sc.set_brightness, False),
    "lock_screen": (sc.lock_screen, False),
    "screenshot": (sc.take_screenshot, False),
    "free_ram": (handle_free_ram, False),
    "sleep": (sc.sleep_pc, True),
    "log_off": (sc.log_off, True),
    "shutdown": (sc.shutdown_pc, True),
    "restart": (sc.restart_pc, True),
    "cancel_shutdown": (sc.cancel_shutdown, False),
}

TOOL_SCHEMAS = [
    _fn("open_app",
        "Open an installed program, game, or website on the user's PC. "
        "Pass the name EXACTLY as it appears in the installed list in the "
        "context (e.g. 'euro truck simulator 2', 'valorant', 'discord'). "
        "Only pass a URL for famous sites you are sure about; never invent a domain. "
        "If the user's words don't clearly name something, ask instead of calling this.",
        {"name": {"type": "string", "description": "App/game name or URL"}},
        ["name"]),
    _fn("close_app",
        "Close / kill a running program or game.",
        {"name": {"type": "string"}}, ["name"]),
    _fn("system_control",
        "Volume, media keys, brightness, RAM cleanup, lock, screenshot, power. "
        "For 'set_volume' or 'set_brightness', pass `level` (0..100).",
        {
            "action": {"type": "string", "enum": list(_SYSTEM_ACTIONS)},
            "level": {"type": "number", "description": "Percentage 0..100 for set_volume / set_brightness"},
        },
        ["action"]),
    _fn("activate_mode",
        "Activate a multi-step smart preset mode: 'study' (coding/study focus), "
        "'gaming' (free RAM + Discord + 80% volume), or 'cinema' (Netflix + dim screen).",
        {"mode": {"type": "string", "enum": ["study", "gaming", "cinema"]}},
        ["mode"]),
    _fn("play_media",
        "Play a song, artist, playlist, Quran surah, video or movie (YouTube/Spotify logic "
        "already built in). Example query: 'عمرو دياب تملي معاك'.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("web_search",
        "Search the web and open results in the browser.",
        {"query": {"type": "string"},
         "where": {"type": "string", "enum": ["google", "youtube"]}},
        ["query"]),
    _fn("set_reminder",
        "Remind the user of something after N minutes.",
        {"minutes": {"type": "number"}, "text": {"type": "string"}},
        ["minutes", "text"]),
    _fn("schedule_command",
        "Run a Yobi command later, e.g. close a game after 60 minutes. "
        "`command` is a short Egyptian-Arabic Yobi command like 'اقفل فالورانت'.",
        {"minutes": {"type": "number"}, "command": {"type": "string"}},
        ["minutes", "command"]),
    _fn("pc_command",
        "Files, folders and device commands. Pass a short canonical Arabic "
        "command, for example: 'افتح فولدر التحميلات', 'اعمل فولدر اسمه X', "
        "'دور على ملف X', 'امسح ملف X', 'ايه اللي شغال', 'فضي الرامات', 'برامج البدء', "
        "'عطل X من البدء', 'افحص جهازي', 'فين موقع X'.",
        {"command": {"type": "string"}}, ["command"]),
    _fn("system_info",
        "Live PC facts: time, date, battery, RAM, CPU, GPU, disk space, IP, uptime.",
        {"question": {"type": "string",
                      "description": "The question in Arabic, e.g. 'كام الرام فاضي'"}},
        ["question"]),
    _fn("look_at_screen",
        "Take a screenshot and describe what's on the screen (errors, "
        "windows, text). Use when the user asks about their screen."),
    _fn("do_on_screen",
        "Computer-use: control mouse/keyboard to complete a multi-step goal "
        "inside an app (e.g. 'ابعت رسالة لأحمد على ديسكورد'). Slow; use only "
        "when no other tool fits.",
        {"goal": {"type": "string"}}, ["goal"]),
]


class YobiTools:
    """Executes tool calls. `confirm(description) -> bool` is called before
    anything destructive (shutdown, delete…)."""

    def __init__(self, agent, scheduler, groq_client, confirm,
                 on_opened=None, on_action=None, choose=None, guard=None):
        self.agent = agent
        self.choose = choose
        self.guard = guard
        self.current_utterance = None
        self.current_stt_low = False
        self.scheduler = scheduler
        self.client = groq_client
        self.confirm = confirm
        self.on_opened = on_opened or (lambda target, result: None)
        self.on_action = on_action or (lambda desc: None)
        self.schemas = TOOL_SCHEMAS

    def execute(self, name, args):
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {}
        fn = getattr(self, f"_t_{name}", None)
        if not fn:
            return f"tool '{name}' مش موجودة"
        try:
            result = fn(**(args or {}))
        except TypeError as e:
            result = f"arguments غلط: {e}"
        except Exception as e:
            result = f"فشل: {e}"
        result = "" if result is None else str(result)
        self.on_action(f"{name}: {result[:120]}")
        return result

    # ── tools ───────────────────────────────────────────────────

    def _t_open_app(self, name):
        if not hasattr(self.agent, "resolve"):
            res = self.agent.open_target(name.strip())
            if res in ("مش لاقي البرنامج ده", "مش لاقي حاجة أفتحها"):
                return f"NOT_FOUND: مش لاقي '{name}' على الجهاز"
            self.on_opened(name, res)
            return res
        from smart_open import smart_open
        return smart_open(self.agent, name.strip(), utterance=self.current_utterance,
                          stt_low=self.current_stt_low, choose=self.choose,
                          guard=self.guard, on_opened=self.on_opened)

    def _t_close_app(self, name):
        if self.guard is not None:
            self.guard.on_close(name)
        return self.agent.kill_process(name.strip())

    def _t_system_control(self, action, level=None):
        entry = _SYSTEM_ACTIONS.get(action)
        if not entry:
            return f"action مش معروف: {action}"
        fn, dangerous = entry
        if dangerous and not self.confirm(action.replace("_", " ")):
            return "CANCELLED: المستخدم لغى"
        if action in ("set_volume", "set_brightness"):
            lvl = 50 if level is None else int(float(level))
            return fn(lvl)
        return fn()

    def _t_activate_mode(self, mode):
        return activate_smart_mode(mode)

    def _t_play_media(self, query):
        handled, msg = handle_media_or_search(f"شغل {query}", self.agent)
        if handled:
            return msg
        q = urllib.parse.quote_plus(query)
        webbrowser.open(f"https://www.youtube.com/results?search_query={q}")
        return f"فتحت يوتيوب على '{query}'"

    def _t_web_search(self, query, where="google"):
        q = urllib.parse.quote_plus(query)
        if where == "youtube":
            webbrowser.open(f"https://www.youtube.com/results?search_query={q}")
        else:
            webbrowser.open(f"https://www.google.com/search?q={q}")
        return f"بحثت عن '{query}' على {where}"

    @staticmethod
    def _minutes(m):
        m = float(m)
        return int(m) if m.is_integer() else m

    def _t_set_reminder(self, minutes, text):
        minutes = self._minutes(minutes)
        self.scheduler._add_task(minutes, f"تذكير: {text}",
                                 lambda t=text: self.scheduler._on_notify(t))
        return f"هفكرك بعد {self.scheduler._format_duration(minutes)}: {text}"

    def _t_schedule_command(self, minutes, command):
        minutes = self._minutes(minutes)
        self.scheduler._add_task(minutes, command,
                                 lambda c=command: self.scheduler._on_execute(c))
        return f"هنفذ '{command}' بعد {self.scheduler._format_duration(minutes)}"

    def _t_pc_command(self, command):
        for matcher in (match_file_command, match_device_command):
            m = matcher(command)
            if not m:
                continue
            action_fn, description, needs_confirm = m
            if needs_confirm and not self.confirm(description):
                return "CANCELLED: المستخدم لغى"
            return action_fn()
        m = sc.match_system_command(command)
        if m:
            action_fn, description, needs_confirm = m
            if needs_confirm and not self.confirm(description):
                return "CANCELLED: المستخدم لغى"
            return action_fn()
        return "UNKNOWN_COMMAND: مفيش أمر بالصيغة دي"

    def _t_system_info(self, question):
        return try_system_answer(question) or "مش عارف أجيب المعلومة دي من الجهاز"

    def _t_look_at_screen(self):
        from vision_agent import describe_screen
        return describe_screen(self.client)

    def _t_do_on_screen(self, goal):
        from vision_agent import run_task_live
        ok, reason = run_task_live(self.client, goal, max_steps=15)
        return "DONE" if ok else f"FAILED: {reason}"