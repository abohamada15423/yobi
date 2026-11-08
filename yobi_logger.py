# -*- coding: utf-8 -*-
"""
Yobi Logger — نظام لوج محترف ليوبي.

Features:
  • Color-coded console output (Arabic-friendly)
  • Rotating file logs (max 10MB × 3 backups)
  • Performance timing decorators
  • Error aggregation — groups repeated errors
  • Structured logging with context
  • Thread-safe

Usage:
    from yobi_logger import log, timed
    log.info("يوبي اشتغل ✅")
    log.error("مشكلة في الـ API", exc_info=True)

    @timed("scan_apps")
    def scan(): ...
"""

import functools
import logging
import logging.handlers
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))

# Try to load config, but work without it
try:
    from config import cfg
    _LOG_LEVEL = cfg.get("logging.level", "INFO")
    _FILE_ENABLED = cfg.get("logging.file_enabled", True)
    _FILE_PATH = cfg.get("logging.file_path", "yobi.log")
    _MAX_SIZE = cfg.get("logging.max_file_size_mb", 10) * 1024 * 1024
    _BACKUP_COUNT = cfg.get("logging.backup_count", 3)
    _CONSOLE_COLORS = cfg.get("logging.console_colors", True)
    _PERF_TRACKING = cfg.get("logging.performance_tracking", True)
except ImportError:
    _LOG_LEVEL = "INFO"
    _FILE_ENABLED = True
    _FILE_PATH = "yobi.log"
    _MAX_SIZE = 10 * 1024 * 1024
    _BACKUP_COUNT = 3
    _CONSOLE_COLORS = True
    _PERF_TRACKING = True


# ============================================================================
# Color definitions for Windows terminal
# ============================================================================
class _Colors:
    """ANSI color codes — gracefully disabled if terminal doesn't support."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Background
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"

    @classmethod
    def disable(cls):
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith("_"):
                setattr(cls, attr, "")


# Enable ANSI on Windows
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        _Colors.disable()

if not _CONSOLE_COLORS:
    _Colors.disable()

C = _Colors


# ============================================================================
# Custom formatter with colors and Arabic-friendly layout
# ============================================================================
class YobiFormatter(logging.Formatter):
    """Color-coded log formatter with emoji level indicators."""

    LEVEL_STYLES = {
        logging.DEBUG:    (C.GRAY,    "🔍"),
        logging.INFO:     (C.GREEN,   "✅"),
        logging.WARNING:  (C.YELLOW,  "⚠️"),
        logging.ERROR:    (C.RED,     "❌"),
        logging.CRITICAL: (C.BG_RED + C.WHITE, "🔥"),
    }

    def __init__(self, colored=True):
        super().__init__()
        self._colored = colored

    def format(self, record):
        color, emoji = self.LEVEL_STYLES.get(
            record.levelno, (C.WHITE, "📝")
        )

        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        if self._colored:
            msg = (
                f"{C.DIM}{timestamp}{C.RESET} "
                f"{color}{emoji} {record.levelname:<8}{C.RESET} "
                f"{C.CYAN}[{record.name}]{C.RESET} "
                f"{record.getMessage()}"
            )
        else:
            msg = (
                f"{timestamp} "
                f"{emoji} {record.levelname:<8} "
                f"[{record.name}] "
                f"{record.getMessage()}"
            )

        if record.exc_info and record.exc_info[1]:
            msg += f"\n{self.formatException(record.exc_info)}"

        return msg


class FileFormatter(logging.Formatter):
    """Plain text formatter for log files."""

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]
        msg = (
            f"{timestamp} | {record.levelname:<8} | "
            f"{record.name} | {record.getMessage()}"
        )
        if record.exc_info and record.exc_info[1]:
            msg += f"\n{self.formatException(record.exc_info)}"
        return msg


# ============================================================================
# Error Aggregator — groups repeated errors
# ============================================================================
class ErrorAggregator:
    """Tracks error frequency to avoid log spam."""

    def __init__(self, window_seconds=60):
        self._counts = defaultdict(int)
        self._first_seen = {}
        self._window = window_seconds
        self._lock = threading.Lock()

    def should_log(self, error_key):
        """Returns (should_log, count) — logs first occurrence and then
        every 10th repeated occurrence within the time window."""
        now = time.time()
        with self._lock:
            # Cleanup old entries
            expired = [
                k for k, t in self._first_seen.items()
                if now - t > self._window
            ]
            for k in expired:
                del self._counts[k]
                del self._first_seen[k]

            self._counts[error_key] += 1
            count = self._counts[error_key]

            if error_key not in self._first_seen:
                self._first_seen[error_key] = now

            # Log first, and then every 10th
            return (count == 1 or count % 10 == 0), count


_aggregator = ErrorAggregator()


# ============================================================================
# Performance tracking
# ============================================================================
class PerfTracker:
    """Tracks execution times for performance monitoring."""

    def __init__(self):
        self._timings = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, name, duration_ms):
        with self._lock:
            self._timings[name].append(duration_ms)
            # Keep last 100
            if len(self._timings[name]) > 100:
                self._timings[name] = self._timings[name][-100:]

    def stats(self, name=None):
        """Get timing stats. Returns dict with avg/min/max/count."""
        with self._lock:
            if name:
                data = self._timings.get(name, [])
                if not data:
                    return None
                return {
                    "name": name,
                    "avg_ms": sum(data) / len(data),
                    "min_ms": min(data),
                    "max_ms": max(data),
                    "count": len(data),
                }
            return {
                k: {
                    "avg_ms": sum(v) / len(v),
                    "min_ms": min(v),
                    "max_ms": max(v),
                    "count": len(v),
                }
                for k, v in self._timings.items()
                if v
            }

    def clear(self):
        with self._lock:
            self._timings.clear()


perf = PerfTracker()


# ============================================================================
# Timing decorator
# ============================================================================
def timed(name=None):
    """Decorator that logs execution time.

    Usage:
        @timed("app_scan")
        def scan_apps(): ...
    """
    def decorator(fn):
        label = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                if _PERF_TRACKING:
                    perf.record(label, elapsed)
                if elapsed > 1000:
                    log.info(f"⏱️ {label}: {elapsed:.0f}ms")
                else:
                    log.debug(f"⏱️ {label}: {elapsed:.1f}ms")
                return result
            except Exception:
                elapsed = (time.perf_counter() - start) * 1000
                if _PERF_TRACKING:
                    perf.record(f"{label}_error", elapsed)
                raise

        return wrapper
    return decorator


# ============================================================================
# Setup logger
# ============================================================================
def _setup_logger():
    """Create and configure the Yobi logger."""
    logger = logging.getLogger("yobi")
    logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))

    # Prevent duplicate handlers on reload
    logger.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(YobiFormatter(colored=_CONSOLE_COLORS))
    console.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    logger.addHandler(console)

    # File handler
    if _FILE_ENABLED:
        log_path = _FILE_PATH
        if not os.path.isabs(log_path):
            log_path = os.path.join(_HERE, log_path)

        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=int(_MAX_SIZE),
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(FileFormatter())
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"⚠️ Could not create log file: {e}")

    # Don't propagate to root logger
    logger.propagate = False

    return logger


# ============================================================================
# Module-level singleton
# ============================================================================
log = _setup_logger()


def get_logger(name):
    """Get a child logger for a specific module.

    Usage:
        from yobi_logger import get_logger
        log = get_logger("tts")
        log.info("TTS ready")
    """
    return log.getChild(name)


# ============================================================================
# Convenience: aggregated error logging
# ============================================================================
def log_error_aggregated(error_key, message, *args, **kwargs):
    """Log an error, but aggregate repeated occurrences to avoid spam."""
    should, count = _aggregator.should_log(error_key)
    if should:
        suffix = f" (×{count})" if count > 1 else ""
        log.error(f"{message}{suffix}", *args, **kwargs)


# ============================================================================
# Print replacement — preserves Arabic print_ar behavior
# ============================================================================
def print_ar(msg):
    """Drop-in replacement for the project's print_ar function with logging."""
    log.info(msg)
