# -*- coding: utf-8 -*-
"""
Vision Agent v2.2 — Gemini Flash Edition.

• Uses Google Gemini Flash (`gemini-2.5-flash` / `gemini-2.0-flash`) as primary
  vision model with automatic fallback.
• Fast JPEG Compression — 10x smaller payload (~200KB vs 3MB PNG) while
  keeping 100% identical pixel resolution for (x, y) click coordinates.
• OCR + Element Detection — annotates screenshots with detected UI
  elements using Windows UI Automation.
• Screen Description — "إيه اللي على الشاشة؟" / "إيه الإيرور ده؟"
• Visual Memory — caches successful step sequences keyed by goal.
"""

import base64
import difflib
import hashlib
import io
import json
import os
import re
import threading
import time

import keyboard
import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

VISION_MODEL = "gemini-3.8-flash"
_VISION_FALLBACKS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]

TASKS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_tasks.json")
VISUAL_MEMORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visual_memory.json")


def _parse_json_safe(raw_text: str) -> dict:
    t = (raw_text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```$", "", t)
    m = re.search(r"\{.*\}", t, flags=re.S)
    if m:
        t = m.group(0)
    return json.loads(t)


def _vision_completion(client, messages, temperature=0.2, max_tokens=350):
    """Call Gemini Flash (or fallback vision models) with automatic retry."""
    last_err = None
    is_gemini = getattr(client, "is_gemini", False)
    models = _VISION_FALLBACKS[:4] if is_gemini else _VISION_FALLBACKS
    for model in models:
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("All vision model fallbacks failed")


# ===========================================================================
# Task persistence
# ===========================================================================
def load_tasks():
    if os.path.exists(TASKS_PATH):
        try:
            with open(TASKS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_tasks(data):
    try:
        with open(TASKS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"⚠️ Could not save tasks: {e}")


def find_matching_task(command, tasks):
    """Fuzzy-match a spoken command against learned task names."""
    if not tasks:
        return None
    command_l = command.lower().strip()
    for name in tasks:
        if name and len(name) >= 3 and name in command_l:
            return name
    close = difflib.get_close_matches(command_l, list(tasks.keys()), n=1, cutoff=0.75)
    return close[0] if close else None


# ===========================================================================
# Visual Memory — cache successful action sequences for repeat tasks
# ===========================================================================
class VisualMemory:
    def __init__(self, path=VISUAL_MEMORY_PATH):
        self._path = path
        self._data = self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _key(goal):
        return goal.lower().strip()

    def lookup(self, goal):
        entry = self._data.get(self._key(goal))
        if entry and entry.get("success_count", 0) >= 1:
            return entry["steps"]
        return None

    def record_success(self, goal, steps):
        key = self._key(goal)
        existing = self._data.get(key)
        if existing:
            existing["success_count"] = existing.get("success_count", 0) + 1
            existing["steps"] = steps
            existing["last_used"] = time.time()
        else:
            self._data[key] = {
                "goal_key": key,
                "steps": steps,
                "success_count": 1,
                "last_used": time.time(),
            }
        self._save()

    def invalidate(self, goal):
        key = self._key(goal)
        if key in self._data:
            del self._data[key]
            self._save()


_visual_memory = VisualMemory()


# ===========================================================================
# Screenshot utilities (Fast JPEG at native resolution)
# ===========================================================================
def _screenshot_b64(region=None):
    """Capture a screenshot and return as base64 JPEG."""
    img = pyautogui.screenshot(region=region)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _screenshot_with_size():
    """Return (base64_jpeg, width, height)."""
    img = pyautogui.screenshot()
    w, h = img.size
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8"), w, h


# ===========================================================================
# OCR + UI Element Detection
# ===========================================================================
def _detect_ui_elements():
    try:
        import uiautomation as auto
    except ImportError:
        return None

    elements = []
    try:
        root = auto.GetForegroundControl()
        if not root:
            return None

        def _walk(ctrl, depth=0, max_depth=2):
            if depth > max_depth or len(elements) >= 40:
                return
            try:
                name = (ctrl.Name or "").strip()
                ctype = ctrl.ControlTypeName or ""
                rect = ctrl.BoundingRectangle
                if name and rect.width() > 0 and rect.height() > 0:
                    cx = rect.left + rect.width() // 2
                    cy = rect.top + rect.height() // 2
                    elements.append(f"[{ctype}] \"{name}\" at ({cx},{cy})")
            except Exception:
                pass
            try:
                for child in ctrl.GetChildren():
                    _walk(child, depth + 1, max_depth)
            except Exception:
                pass

        _walk(root)
    except Exception:
        return None

    if not elements:
        return None
    return "Detected UI elements in foreground window:\n" + "\n".join(elements[:40])


# ===========================================================================
# Screen Description
# ===========================================================================
_DESCRIBE_SCREEN_PROMPT = """أنت يوبي — مساعد ذكي. شايف قدامك صورة لشاشة كمبيوتر.
وصفلي بالعامية المصرية إيه اللي باين على الشاشة — البرنامج المفتوح، أي رسائل أو errors،
وأي حاجة مميزة تقدر تلاحظها. خلي الوصف مفيد ومختصر (٢-٣ جمل).
لو فيه error أو مشكلة واضحة، اذكرها بالتحديد واقترح حل سريع.
Respond ONLY with raw JSON: {"description": "<Arabic description>"}"""


def describe_screen(client):
    """Capture the full screen and return an Arabic description."""
    try:
        screenshot = _screenshot_b64()
        ui_hint = _detect_ui_elements()

        user_content = [{"type": "text", "text": "وصفلي الشاشة دي:"}]
        if ui_hint:
            user_content.append({"type": "text", "text": ui_hint})
        user_content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot}"}}
        )

        response = _vision_completion(
            client,
            messages=[
                {"role": "system", "content": _DESCRIBE_SCREEN_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        data = _parse_json_safe(response.choices[0].message.content)
        return data.get("description", "مش قادر أوصف الشاشة")
    except Exception as e:
        return f"معرفتش أشوف الشاشة: {e}"


def describe_area(client, x, y, w, h):
    """Describe a specific rectangular region of the screen."""
    try:
        screenshot = _screenshot_b64(region=(x, y, w, h))
        response = _vision_completion(
            client,
            messages=[
                {"role": "system", "content": _DESCRIBE_SCREEN_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "وصفلي الجزء ده من الشاشة:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot}"}},
                    ],
                },
            ],
            temperature=0.3,
            max_tokens=300,
        )
        data = _parse_json_safe(response.choices[0].message.content)
        return data.get("description", "مش قادر أوصف المنطقة دي")
    except Exception as e:
        return f"معرفتش أوصف المنطقة: {e}"


# ===========================================================================
# Extended action set
# ===========================================================================
_ACTION_SYSTEM_PROMPT = """You are a computer-use agent controlling a Windows desktop via screenshots.
You are shown the CURRENT screenshot and a GOAL. Decide exactly ONE next action toward the goal.

Respond ONLY with a raw JSON object (no markdown), one of these shapes:

CLICK ACTIONS:
{"action": "click", "x": <int>, "y": <int>, "reason": "<short reason>"}
{"action": "double_click", "x": <int>, "y": <int>, "reason": "<short reason>"}
{"action": "right_click", "x": <int>, "y": <int>, "reason": "<short reason>"}
{"action": "triple_click", "x": <int>, "y": <int>, "reason": "<short reason>"}

MOUSE ACTIONS:
{"action": "drag", "from_x": <int>, "from_y": <int>, "to_x": <int>, "to_y": <int>, "reason": "<short reason>"}
{"action": "move_to", "x": <int>, "y": <int>, "reason": "<short reason>"}

TEXT ACTIONS:
{"action": "type", "text": "<text to type>", "reason": "<short reason>"}
{"action": "select_all", "reason": "<short reason>"}

KEYBOARD ACTIONS:
{"action": "key", "key": "<single key name, e.g. enter, esc, tab>", "reason": "<short reason>"}
{"action": "hotkey", "keys": ["ctrl", "c"], "reason": "<short reason>"}

SCROLL:
{"action": "scroll", "amount": <int, positive=up negative=down>, "reason": "<short reason>"}

WAIT / DONE:
{"action": "wait", "seconds": <number>, "reason": "<short reason>"}
{"action": "done", "reason": "<why the goal is complete, or why you're giving up>"}

Coordinates are pixel positions on the screenshot shown (top-left is 0,0).
If the goal already looks complete, respond "done".
If stuck after a few attempts, respond "done" and explain why — never loop forever.
"""


def ask_next_action(client, goal, screenshot_b64, step_history, ui_elements=None):
    """Ask the LLM for the next action, with optional UI element hints."""
    history_text = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(step_history)) or "(none yet)"
    user_text = f"GOAL: {goal}\n\nSteps taken so far:\n{history_text}\n\nWhat is the next action?"
    if ui_elements:
        user_text += f"\n\n{ui_elements}"

    try:
        response = _vision_completion(
            client,
            messages=[
                {"role": "system", "content": _ACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"}},
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=300,
        )
        return _parse_json_safe(response.choices[0].message.content)
    except Exception as e:
        return {"action": "done", "reason": f"error: {e}"}


def _execute_action(action):
    """Execute a single action dict. Returns True if executed, False if 'done'."""
    kind = action.get("action")

    if kind == "click":
        pyautogui.click(action["x"], action["y"])
    elif kind == "double_click":
        pyautogui.doubleClick(action["x"], action["y"])
    elif kind == "right_click":
        pyautogui.rightClick(action["x"], action["y"])
    elif kind == "triple_click":
        pyautogui.click(action["x"], action["y"], clicks=3)
    elif kind == "drag":
        pyautogui.moveTo(action["from_x"], action["from_y"])
        time.sleep(0.1)
        pyautogui.mouseDown()
        time.sleep(0.05)
        pyautogui.moveTo(action["to_x"], action["to_y"], duration=0.4)
        time.sleep(0.05)
        pyautogui.mouseUp()
    elif kind == "move_to":
        pyautogui.moveTo(action["x"], action["y"])
    elif kind == "type":
        text = action.get("text", "")
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.typewrite(text, interval=0.02)
    elif kind == "select_all":
        pyautogui.hotkey("ctrl", "a")
    elif kind == "key":
        pyautogui.press(action.get("key", ""))
    elif kind == "hotkey":
        keys = action.get("keys", [])
        if keys:
            pyautogui.hotkey(*keys)
    elif kind == "scroll":
        pyautogui.scroll(action.get("amount", 0))
    elif kind == "wait":
        time.sleep(min(float(action.get("seconds", 1)), 5))

    return kind != "done"


def _screenshot_hash():
    img = pyautogui.screenshot()
    thumb = img.resize((16, 16))
    pixels = list(thumb.getdata())
    return hashlib.md5(str(pixels).encode()).hexdigest()


def run_task_live(client, goal, max_steps=15, step_delay=1.0, on_step=None):
    """Runs the screenshot → decide → act loop with visual memory and OCR."""
    cached_steps = _visual_memory.lookup(goal)
    if cached_steps:
        if on_step:
            on_step("⚡ لقيت الخطوات محفوظة — بعيد التنفيذ بسرعة...")

        replay_ok = True
        for i, action in enumerate(cached_steps, 1):
            kind = action.get("action", "unknown")
            reason = action.get("reason", "")
            if on_step:
                on_step(f"↻ خطوة {i}/{len(cached_steps)}: {kind} — {reason}")

            try:
                if not _execute_action(action):
                    break
            except pyautogui.FailSafeException:
                if on_step:
                    on_step("🛑 إيقاف طارئ — الماوس اتحرك لركن الشاشة.")
                _visual_memory.invalidate(goal)
                return False, "emergency stop"
            except Exception as e:
                if on_step:
                    on_step(f"⚠️ فشلت خطوة الريبلاي: {e}")
                replay_ok = False
                break

            time.sleep(step_delay * 0.5)

        if replay_ok:
            try:
                verify_screenshot = _screenshot_b64()
                verify = ask_next_action(
                    client, goal, verify_screenshot,
                    [f"Replayed {len(cached_steps)} cached steps"],
                )
                if verify.get("action") == "done":
                    _visual_memory.record_success(goal, cached_steps)
                    return True, verify.get("reason", "replay succeeded")
            except Exception:
                pass

        if on_step:
            on_step("🔄 الريبلاي مش واضح نجح — بكمل live...")
        _visual_memory.invalidate(goal)

    step_history = []
    recorded_actions = []
    stale_count = 0

    for step_num in range(1, max_steps + 1):
        try:
            screenshot = _screenshot_b64()
        except Exception as e:
            if on_step:
                on_step(f"⚠️ فشل أخذ screenshot: {e}")
            return False, "screenshot failed"

        ui_elements = _detect_ui_elements()
        action = ask_next_action(client, goal, screenshot, step_history,
                                 ui_elements=ui_elements)
        reason = action.get("reason", "")
        kind = action.get("action", "unknown")

        if on_step:
            on_step(f"خطوة {step_num}: {kind} — {reason}")

        if kind == "done":
            if recorded_actions:
                _visual_memory.record_success(goal, recorded_actions)
            return True, reason

        pre_hash = _screenshot_hash()

        try:
            _execute_action(action)
        except pyautogui.FailSafeException:
            if on_step:
                on_step("🛑 إيقاف طارئ — الماوس اتحرك لركن الشاشة.")
            return False, "emergency stop"
        except Exception as e:
            if on_step:
                on_step(f"⚠️ فشلت الخطوة: {e}")
            step_history.append(f"{kind} FAILED: {e}")
            continue

        time.sleep(step_delay * 0.7)
        post_hash = _screenshot_hash()

        if post_hash == pre_hash:
            stale_count += 1
            if stale_count >= 3:
                if on_step:
                    on_step("⚠️ الشاشة مش بتتغير — بوقف عشان مش عايز أضيع وقت")
                return False, "screen not responding to actions"
            step_history.append(f"{kind} ({reason}) — ⚠️ screen unchanged")
        else:
            stale_count = 0
            step_history.append(f"{kind} ({reason})")

        recorded_actions.append(action)
        time.sleep(step_delay * 0.3)

    return False, "max steps reached"


def record_demo(stop_hotkey="f9", interval=2.0, max_frames=20, on_frame=None):
    frames = []
    stop_event = threading.Event()
    keyboard.add_hotkey(stop_hotkey, stop_event.set)

    try:
        while not stop_event.is_set() and len(frames) < max_frames:
            frames.append(_screenshot_b64())
            if on_frame:
                on_frame(len(frames))
            stop_event.wait(interval)
    finally:
        keyboard.remove_hotkey(stop_hotkey)

    return frames


_DESCRIBE_SYSTEM_PROMPT = """You will be shown a sequence of screenshots, in order, taken a few seconds
apart while a user performed a task on their Windows PC. Describe, in
Arabic, in 2-4 short sentences, what task the user appears to have
accomplished — concretely enough that someone (or an automated agent) could
recognize and repeat the same kind of task on a similar screen later.
Respond ONLY with a raw JSON object: {"description": "<Arabic description>"}
"""


def describe_demo(client, frames):
    if not frames:
        return ""
    if len(frames) > 6:
        step = len(frames) / 6
        frames = [frames[int(i * step)] for i in range(6)]

    content = [{"type": "text", "text": "Screenshots in order:"}]
    for f in frames:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{f}"}})

    try:
        response = _vision_completion(
            client,
            messages=[
                {"role": "system", "content": _DESCRIBE_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        data = _parse_json_safe(response.choices[0].message.content)
        return data.get("description", "")
    except Exception as e:
        return f"(تعذر وصف المهمة: {e})"