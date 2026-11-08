# -*- coding: utf-8 -*-
"""
Retry Handler — حماية يوبي من الأخطاء.

Features:
  • Exponential Backoff with jitter
  • Circuit Breaker — يوقف لو API فشل كتير
  • Fallback Chain — Groq → Offline cache → default response
  • Health Monitor — يراقب latency ويحذّر
  • Offline Mode — يشتغل بدون internet للأوامر المحلية
  • Decorator API — @with_retry على أي function

Usage:
    from retry_handler import with_retry, api_call, health

    @with_retry(max_retries=3, fallback="حصل مشكلة")
    def my_api_call():
        return client.chat.completions.create(...)

    result = api_call(lambda: client.chat(...), fallback="...")

    if health.is_healthy("groq"):
        # safe to call
"""

import hashlib
import json
import os
import random
import threading
import time
import functools
from collections import defaultdict

try:
    from yobi_logger import get_logger, perf
    log = get_logger("retry")
except ImportError:
    import logging
    log = logging.getLogger("retry")
    perf = None

try:
    from config import cfg
    _MAX_RETRIES = cfg.get("retry.max_retries", 3)
    _BASE_DELAY = cfg.get("retry.base_delay", 1.0)
    _MAX_DELAY = cfg.get("retry.max_delay", 30.0)
    _BACKOFF_FACTOR = cfg.get("retry.backoff_factor", 2.0)
    _JITTER = cfg.get("retry.jitter", True)
    _CB_THRESHOLD = cfg.get("retry.circuit_breaker_threshold", 5)
    _CB_TIMEOUT = cfg.get("retry.circuit_breaker_timeout", 60)
    _FALLBACK_OFFLINE = cfg.get("retry.fallback_to_offline", True)
    _HEALTH_INTERVAL = cfg.get("retry.health_check_interval", 30)
except ImportError:
    _MAX_RETRIES = 3
    _BASE_DELAY = 1.0
    _MAX_DELAY = 30.0
    _BACKOFF_FACTOR = 2.0
    _JITTER = True
    _CB_THRESHOLD = 5
    _CB_TIMEOUT = 60
    _FALLBACK_OFFLINE = True
    _HEALTH_INTERVAL = 30


_HERE = os.path.dirname(os.path.abspath(__file__))
_RESPONSE_CACHE_PATH = os.path.join(_HERE, "response_cache.json")


# ============================================================================
# Circuit Breaker
# ============================================================================
class CircuitBreaker:
    """Prevents repeated calls to a failing service.

    States:
      CLOSED  — normal operation, requests pass through
      OPEN    — service is down, requests are rejected immediately
      HALF_OPEN — testing if service recovered (1 request allowed)
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, name, threshold=_CB_THRESHOLD, timeout=_CB_TIMEOUT):
        self.name = name
        self._threshold = threshold
        self._timeout = timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self):
        with self._lock:
            if self._state == self.OPEN:
                # Check if timeout elapsed → transition to HALF_OPEN
                if time.time() - self._last_failure_time >= self._timeout:
                    self._state = self.HALF_OPEN
                    log.info(f"🔄 Circuit breaker [{self.name}]: HALF_OPEN — بنجرب تاني")
            return self._state

    def allow_request(self):
        """Returns True if a request should be attempted."""
        state = self.state
        return state != self.OPEN

    def record_success(self):
        """Record a successful call — resets the breaker."""
        with self._lock:
            if self._state == self.HALF_OPEN:
                log.info(f"✅ Circuit breaker [{self.name}]: CLOSED — الخدمة رجعت")
            self._state = self.CLOSED
            self._failure_count = 0

    def record_failure(self):
        """Record a failed call — may trip the breaker."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self._threshold:
                self._state = self.OPEN
                log.warning(
                    f"🔴 Circuit breaker [{self.name}]: OPEN — "
                    f"{self._failure_count} فشل متتالي، بوقف {self._timeout}s"
                )

    def reset(self):
        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0


# ============================================================================
# Health Monitor
# ============================================================================
class HealthMonitor:
    """Tracks API health: latency, error rates, availability."""

    def __init__(self):
        self._services = {}  # name -> CircuitBreaker
        self._latencies = defaultdict(list)  # name -> [ms, ...]
        self._lock = threading.Lock()

    def get_breaker(self, name):
        """Get or create a circuit breaker for a service."""
        if name not in self._services:
            self._services[name] = CircuitBreaker(name)
        return self._services[name]

    def is_healthy(self, name):
        """Check if a service is healthy (circuit breaker closed)."""
        breaker = self.get_breaker(name)
        return breaker.allow_request()

    def record_call(self, name, duration_ms, success=True):
        """Record a call result."""
        breaker = self.get_breaker(name)
        if success:
            breaker.record_success()
        else:
            breaker.record_failure()

        with self._lock:
            self._latencies[name].append(duration_ms)
            if len(self._latencies[name]) > 50:
                self._latencies[name] = self._latencies[name][-50:]

    def get_stats(self, name=None):
        """Get health stats for a service or all services."""
        with self._lock:
            if name:
                lats = self._latencies.get(name, [])
                breaker = self._services.get(name)
                return {
                    "name": name,
                    "state": breaker.state if breaker else "unknown",
                    "avg_latency_ms": sum(lats) / len(lats) if lats else 0,
                    "p95_latency_ms": sorted(lats)[int(len(lats) * 0.95)] if lats else 0,
                    "call_count": len(lats),
                }
            return {
                svc: self.get_stats(svc)
                for svc in self._services
            }

    def summary(self):
        """Human-readable health summary."""
        stats = self.get_stats()
        if not stats:
            return "مفيش بيانات عن صحة الخدمات"
        lines = []
        for name, s in stats.items():
            state_icon = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}.get(
                s["state"], "⚪"
            )
            lines.append(
                f"{state_icon} {name}: {s['state']} | "
                f"avg {s['avg_latency_ms']:.0f}ms | "
                f"{s['call_count']} calls"
            )
        return "\n".join(lines)


health = HealthMonitor()


# ============================================================================
# Response Cache — offline fallback
# ============================================================================
class ResponseCache:
    """Caches successful API responses so offline mode can reuse them."""

    def __init__(self, path=_RESPONSE_CACHE_PATH, max_entries=200):
        self._path = path
        self._max = max_entries
        self._data = self._load()
        self._lock = threading.Lock()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _key(prompt):
        """Create a hash key from the prompt."""
        return hashlib.md5(prompt.encode("utf-8")).hexdigest()[:12]

    def get(self, prompt):
        """Get a cached response for a prompt."""
        with self._lock:
            entry = self._data.get(self._key(prompt))
            if entry:
                return entry.get("response")
        return None

    def store(self, prompt, response):
        """Cache a successful response."""
        with self._lock:
            key = self._key(prompt)
            self._data[key] = {
                "prompt": prompt[:200],
                "response": response,
                "timestamp": time.time(),
            }
            # Evict oldest if over limit
            if len(self._data) > self._max:
                oldest = sorted(
                    self._data.items(),
                    key=lambda x: x[1].get("timestamp", 0)
                )
                for k, _ in oldest[:len(self._data) - self._max]:
                    del self._data[k]
            self._save()


_cache = ResponseCache()


# ============================================================================
# Retry decorator
# ============================================================================
def with_retry(max_retries=None, fallback=None, service_name="groq",
               cache_key=None, retryable_exceptions=(Exception,)):
    """Decorator: retries a function with exponential backoff.

    Args:
        max_retries: number of retry attempts (default from config)
        fallback: value to return if all retries fail
        service_name: name for the circuit breaker
        cache_key: if set, cache successful results with this key
        retryable_exceptions: tuple of exception types to retry on
    """
    _retries = max_retries if max_retries is not None else _MAX_RETRIES

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            breaker = health.get_breaker(service_name)

            # Circuit breaker check
            if not breaker.allow_request():
                log.warning(f"⛔ [{service_name}] Circuit breaker مفتوح — بستخدم fallback")
                # Try cache
                if cache_key:
                    cached = _cache.get(cache_key)
                    if cached is not None:
                        log.info(f"📦 [{service_name}] لقيت رد محفوظ في الكاش")
                        return cached
                return fallback

            last_exception = None
            for attempt in range(_retries + 1):
                try:
                    start = time.perf_counter()
                    result = fn(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start) * 1000

                    # Record success
                    health.record_call(service_name, elapsed_ms, success=True)

                    if perf:
                        perf.record(f"{service_name}_call", elapsed_ms)

                    # Cache if requested
                    if cache_key and result is not None:
                        _cache.store(cache_key, result)

                    return result

                except retryable_exceptions as e:
                    last_exception = e
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    health.record_call(service_name, elapsed_ms, success=False)

                    if attempt < _retries:
                        delay = _calculate_delay(attempt)
                        log.warning(
                            f"⚠️ [{service_name}] محاولة {attempt + 1}/{_retries + 1} "
                            f"فشلت: {e} — بنعيد بعد {delay:.1f}s"
                        )
                        time.sleep(delay)
                    else:
                        log.error(
                            f"❌ [{service_name}] كل المحاولات فشلت بعد "
                            f"{_retries + 1} محاولة: {e}"
                        )

            # All retries exhausted — try cache, then fallback
            if cache_key:
                cached = _cache.get(cache_key)
                if cached is not None:
                    log.info(f"📦 [{service_name}] بستخدم رد محفوظ من الكاش")
                    return cached

            if fallback is not None:
                return fallback

            # Re-raise last exception if no fallback
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def _calculate_delay(attempt):
    """Calculate delay with exponential backoff and optional jitter."""
    delay = _BASE_DELAY * (_BACKOFF_FACTOR ** attempt)
    delay = min(delay, _MAX_DELAY)
    if _JITTER:
        delay *= (0.5 + random.random())  # 50%–150% of calculated delay
    return delay


# ============================================================================
# Convenience function for one-off API calls
# ============================================================================
def api_call(fn, fallback=None, service_name="groq", cache_key=None,
             max_retries=None):
    """Execute a function with retry logic (non-decorator API).

    Usage:
        result = api_call(
            lambda: client.chat.completions.create(...),
            fallback="حصل مشكلة",
            cache_key="greeting",
        )
    """
    @with_retry(
        max_retries=max_retries,
        fallback=fallback,
        service_name=service_name,
        cache_key=cache_key,
    )
    def _call():
        return fn()

    return _call()


# ============================================================================
# Offline mode detection
# ============================================================================
def is_online():
    """Quick check: can we reach the internet?"""
    import socket
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
            ("8.8.8.8", 53)
        )
        return True
    except (socket.error, OSError):
        return False


def get_offline_response(command):
    """Generate a response without API access — for basic system commands."""
    cmd_l = command.lower().strip()

    # System commands work offline
    try:
        from system_control import match_system_command
        match = match_system_command(cmd_l)
        if match:
            fn, desc, needs_confirm = match
            if not needs_confirm:
                return fn()
            return f"⚠️ '{desc}' محتاج تأكيد — قول 'أيوه' لو متأكد"
    except ImportError:
        pass

    # File ops work offline
    basic_responses = {
        "الساعة كام": lambda: f"الساعة {time.strftime('%I:%M %p')}",
        "النهارده كام": lambda: f"النهارده {time.strftime('%Y-%m-%d')}",
    }
    for trigger, response_fn in basic_responses.items():
        if trigger in cmd_l:
            return response_fn()

    return "⚠️ مفيش اتصال بالإنترنت — بس أقدر أنفذ أوامر النظام والملفات"


# ============================================================================
# Batch retry — for multiple calls
# ============================================================================
def batch_retry(calls, service_name="groq", max_workers=3):
    """Execute multiple API calls with retry, in parallel.

    Args:
        calls: list of (fn, fallback) tuples
        service_name: circuit breaker name
        max_workers: max parallel threads

    Returns:
        list of results (in order)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = [None] * len(calls)

    def _run(index, fn, fb):
        return index, api_call(fn, fallback=fb, service_name=service_name)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run, i, fn, fb): i
            for i, (fn, fb) in enumerate(calls)
        }
        for future in as_completed(futures):
            try:
                idx, result = future.result()
                results[idx] = result
            except Exception as e:
                idx = futures[future]
                log.error(f"Batch call {idx} failed: {e}")

    return results
