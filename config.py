# -*- coding: utf-8 -*-
"""
Yobi Configuration System — إعدادات يوبي الموحّدة.

Single source of truth for all settings:
  • Loads from config.yaml (auto-created with defaults on first run)
  • Hot-reload via watch() — detects file changes without restart
  • Validation — type-checks critical values
  • Environment support — dev / prod profiles
  • Thread-safe access

Usage:
    from config import cfg
    api_key = cfg.get("groq.api_key")
    cfg.set("ui.theme", "dark")
    cfg.save()
"""

import copy
import json
import os
import threading
import time

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_HERE, "config.yaml")
CONFIG_JSON_FALLBACK = os.path.join(_HERE, "config.json")


# ============================================================================
# Default configuration — every key Yobi might ever read
# ============================================================================
DEFAULTS = {
    "env": "prod",

    # ── Groq / LLM ─────────────────────────────────────────────
    "groq": {
        "api_key": "",                          # from env GROQ_API_KEY
        "chat_model": "llama-3.3-70b-versatile",
        "vision_model": "meta-llama/llama-4-maverick-17b-128e-instruct",
        "whisper_model": "whisper-large-v3-turbo",
        "temperature": 0.7,
        "max_tokens": 300,
    },

    # ── Voice / TTS ────────────────────────────────────────────
    "voice": {
        "tts_enabled": True,
        "tts_voice": "ar-EG-SalmaNeural",
        "tts_rate": "+10%",
        "tts_volume": "+0%",
        "wake_word_enabled": True,
        "wake_words": ["يوبي", "yobi", "يا يوبي"],
        "silence_threshold": 1.5,
        "listen_timeout": 8,
    },

    # ── UI ──────────────────────────────────────────────────────
    "ui": {
        "theme": "auto",
        "island_x": 14,
        "island_y": 18,
        "chat_window_enabled": True,
        "quick_actions_enabled": True,
        "overlay_enabled": False,
        "avatar_enabled": True,
        "avatar_style": "default",
        "notification_sound": True,
        "max_history": 50,
    },

    # ── Context / Memory ────────────────────────────────────────
    "memory": {
        "context_depth": 10,
        "session_summary_enabled": True,
        "entity_tracking_enabled": True,
        "mood_detection_enabled": True,
        "topic_clustering_enabled": True,
        "max_session_history": 200,
        "summary_save_path": "session_summaries.json",
    },

    # ── Retry / Error Handling ──────────────────────────────────
    "retry": {
        "max_retries": 3,
        "base_delay": 1.0,
        "max_delay": 30.0,
        "backoff_factor": 2.0,
        "jitter": True,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_timeout": 60,
        "fallback_to_offline": True,
        "health_check_interval": 30,
    },

    # ── Game Companion ──────────────────────────────────────────
    "game_companion": {
        "enabled": True,
        "session_tracking": True,
        "break_reminder_minutes": 60,
        "performance_monitor": True,
        "tips_enabled": True,
        "stats_save_path": "game_stats.json",
    },

    # ── Logging ─────────────────────────────────────────────────
    "logging": {
        "level": "INFO",
        "file_enabled": True,
        "file_path": "yobi.log",
        "max_file_size_mb": 10,
        "backup_count": 3,
        "console_colors": True,
        "performance_tracking": True,
    },

    # ── Paths ───────────────────────────────────────────────────
    "paths": {
        "apps_cache": "installed_apps_cache.json",
        "games_cache": "games_cache.json",
        "learning_data": "learning_data.json",
        "chat_history": "chat_memory.json",
        "usage_patterns": "usage_patterns.json",
        "scan_cache": "smart_scan_cache.json",
    },
}


# ============================================================================
# Config class
# ============================================================================
class YobiConfig:
    """Thread-safe, dot-path configuration manager."""

    def __init__(self, path=CONFIG_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        self._watchers = []          # list of callback(key, old, new)
        self._last_mtime = 0.0
        self._load()

    # ── Loading ────────────────────────────────────────────────

    def _load(self):
        """Load config from YAML (preferred) or JSON fallback."""
        loaded = {}

        # Try YAML first
        if _HAS_YAML and os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                self._last_mtime = os.path.getmtime(self._path)
            except Exception as e:
                print(f"⚠️ Config YAML load error: {e}")

        # Fallback to JSON
        elif os.path.exists(CONFIG_JSON_FALLBACK):
            try:
                with open(CONFIG_JSON_FALLBACK, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._last_mtime = os.path.getmtime(CONFIG_JSON_FALLBACK)
            except Exception as e:
                print(f"⚠️ Config JSON load error: {e}")

        # Merge loaded over defaults (deep merge)
        if loaded:
            self._deep_merge(self._data, loaded)
            # Bridge flat config.json keys into structured sections
            if "wake_words" in loaded and isinstance(loaded["wake_words"], list):
                self._data.setdefault("voice", {})["wake_words"] = loaded["wake_words"]
            if "companion" in loaded and isinstance(loaded["companion"], dict):
                self._deep_merge(self._data.setdefault("game_companion", {}), loaded["companion"])

        # Override with environment variables
        self._apply_env_overrides()

    def _apply_env_overrides(self):
        """Override specific settings from environment variables."""
        env_map = {
            "GROQ_API_KEY": "groq.api_key",
            "YOBI_THEME": "ui.theme",
            "YOBI_ENV": "env",
            "YOBI_LOG_LEVEL": "logging.level",
            "YOBI_TTS_VOICE": "voice.tts_voice",
            "YOBI_TTS_ENABLED": "voice.tts_enabled",
        }
        for env_var, config_key in env_map.items():
            val = os.environ.get(env_var)
            if val is not None:
                # Auto-convert booleans
                if val.lower() in ("true", "1", "yes"):
                    val = True
                elif val.lower() in ("false", "0", "no"):
                    val = False
                self.set(config_key, val, save=False)

    @staticmethod
    def _deep_merge(base, override):
        """Recursively merge override dict into base dict."""
        for key, value in override.items():
            if (key in base and isinstance(base[key], dict)
                    and isinstance(value, dict)):
                YobiConfig._deep_merge(base[key], value)
            else:
                base[key] = value

    # ── Access ─────────────────────────────────────────────────

    def get(self, dot_path, default=None):
        """Get a value by dot-path, e.g. 'groq.api_key'."""
        with self._lock:
            keys = dot_path.split(".")
            node = self._data
            for k in keys:
                if isinstance(node, dict) and k in node:
                    node = node[k]
                else:
                    return default
            return node

    def set(self, dot_path, value, save=True):
        """Set a value by dot-path and optionally persist."""
        with self._lock:
            keys = dot_path.split(".")
            node = self._data
            old_value = self.get(dot_path)

            for k in keys[:-1]:
                if k not in node or not isinstance(node[k], dict):
                    node[k] = {}
                node = node[k]
            node[keys[-1]] = value

        # Notify watchers
        if old_value != value:
            for watcher in self._watchers:
                try:
                    watcher(dot_path, old_value, value)
                except Exception:
                    pass

        if save:
            self.save()

    def section(self, name):
        """Return an entire section dict, e.g. cfg.section('groq')."""
        with self._lock:
            return copy.deepcopy(self._data.get(name, {}))

    # ── Persistence ────────────────────────────────────────────

    def save(self):
        """Save current config to disk."""
        with self._lock:
            try:
                if _HAS_YAML:
                    with open(self._path, "w", encoding="utf-8") as f:
                        yaml.dump(
                            self._data, f,
                            default_flow_style=False,
                            allow_unicode=True,
                            sort_keys=False,
                        )
                else:
                    path = CONFIG_JSON_FALLBACK
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(self._data, f, ensure_ascii=False, indent=2)
                self._last_mtime = time.time()
            except Exception as e:
                print(f"⚠️ Config save error: {e}")

    def reload(self):
        """Force reload from disk."""
        with self._lock:
            self._data = copy.deepcopy(DEFAULTS)
            self._load()

    # ── Hot Reload ─────────────────────────────────────────────

    def check_for_changes(self):
        """Check if the config file was modified externally. Returns True
        if it was reloaded."""
        path = self._path if os.path.exists(self._path) else CONFIG_JSON_FALLBACK
        if not os.path.exists(path):
            return False
        try:
            mtime = os.path.getmtime(path)
            if mtime > self._last_mtime:
                self.reload()
                return True
        except OSError:
            pass
        return False

    def watch(self, callback):
        """Register a watcher: callback(key, old_value, new_value)."""
        self._watchers.append(callback)

    def start_watcher(self, interval=5.0):
        """Start a background thread that checks for config file changes."""
        def _loop():
            while True:
                time.sleep(interval)
                try:
                    self.check_for_changes()
                except Exception:
                    pass

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    # ── Validation ─────────────────────────────────────────────

    def validate(self):
        """Validate critical settings. Returns list of warnings."""
        warnings = []

        api_key = self.get("groq.api_key", "")
        if not api_key:
            warnings.append("⚠️ groq.api_key مش موجود — LLM مش هيشتغل")

        temp = self.get("groq.temperature", 0.7)
        if not (0 <= temp <= 2):
            warnings.append(f"⚠️ groq.temperature={temp} — لازم يكون بين 0 و 2")

        log_level = self.get("logging.level", "INFO")
        if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            warnings.append(f"⚠️ logging.level='{log_level}' — مش معروف")

        theme = self.get("ui.theme", "auto")
        if theme not in ("dark", "light", "auto"):
            warnings.append(f"⚠️ ui.theme='{theme}' — لازم يكون dark/light/auto")

        return warnings

    # ── Utility ─────────────────────────────────────────────────

    def to_dict(self):
        """Return a deep copy of the full config."""
        with self._lock:
            return copy.deepcopy(self._data)

    def reset(self):
        """Reset to defaults."""
        with self._lock:
            self._data = copy.deepcopy(DEFAULTS)
        self.save()

    def __repr__(self):
        return f"YobiConfig(path={self._path!r})"


# ============================================================================
# Module-level singleton
# ============================================================================
cfg = YobiConfig()
