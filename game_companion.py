# -*- coding: utf-8 -*-
"""
Game Companion — رفيق الألعاب ليوبي.

Features:
  • Process Monitor — يعرف أي لعبة شغالة دلوقتي
  • Session Timer — بيتتبع وقت اللعب
  • Break Reminder — يفكّرك تاخد راحة
  • Performance Monitor — CPU/RAM/FPS tracking
  • Game Tips — نصائح من الـ LLM عن اللعبة
  • Game Stats — إحصائيات اللعب (يومي/أسبوعي)
  • Smart Detection — يعرف الألعاب من العمليات

Usage:
    companion = GameCompanion(
        on_notify=lambda msg: print(msg),
        on_overlay_update=lambda data: overlay.show_perf_hud(**data),
    )
    companion.start()

    # Later...
    companion.get_current_game()       # → "Valorant"
    companion.get_session_time()       # → "ساعة و 23 دقيقة"
    companion.get_daily_stats()        # → {...}
"""

import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

try:
    from yobi_logger import get_logger
    log = get_logger("game_companion")
except ImportError:
    import logging
    log = logging.getLogger("game_companion")

try:
    from config import cfg
    _ENABLED = cfg.get("game_companion.enabled", True)
    _SESSION_TRACKING = cfg.get("game_companion.session_tracking", True)
    _BREAK_MINUTES = cfg.get("game_companion.break_reminder_minutes", 60)
    _PERF_MONITOR = cfg.get("game_companion.performance_monitor", True)
    _TIPS_ENABLED = cfg.get("game_companion.tips_enabled", True)
    _STATS_PATH = cfg.get("game_companion.stats_save_path", "game_stats.json")
except ImportError:
    _ENABLED = True
    _SESSION_TRACKING = True
    _BREAK_MINUTES = 60
    _PERF_MONITOR = True
    _TIPS_ENABLED = True
    _STATS_PATH = "game_stats.json"

_HERE = os.path.dirname(os.path.abspath(__file__))


# ============================================================================
# Known game processes → display names
# ============================================================================
KNOWN_GAMES = {
    # Riot (note: riotclientservices.exe is a background launcher, not a game)
    "valorant-win64-shipping.exe": "Valorant",
    "valorant.exe": "Valorant",
    "leagueclient.exe": "League of Legends",
    "league of legends.exe": "League of Legends",
    "tftclient.exe": "Teamfight Tactics",

    # Racing & Simulators
    "eurotrucks2.exe": "Euro Truck Simulator 2",
    "acc.exe": "Assetto Corsa Competizione",
    "ac2-win64-shipping.exe": "Assetto Corsa Competizione",
    "forzahorizon6.exe": "Forza Horizon 6",
    "f1_24.exe": "F1 24",
    "f1_25.exe": "F1 25",

    # Steam / Popular
    "csgo.exe": "CS:GO",
    "cs2.exe": "CS2",
    "dota2.exe": "Dota 2",
    "gta5.exe": "GTA V",
    "gtavlauncher.exe": "GTA V",
    "rdr2.exe": "Red Dead Redemption 2",
    "eldenring.exe": "Elden Ring",
    "sekiro.exe": "Sekiro: Shadows Die Twice",
    "celeste.exe": "Celeste",
    "tlou-i.exe": "The Last of Us Part I",
    "totclient-win64-shipping.exe": "The Outlast Trials",
    "alanwake2.exe": "Alan Wake 2",

    # Epic
    "fortnitelauncher.exe": "Fortnite",
    "fortniteclient-win64-shipping.exe": "Fortnite",
    "rocketleague.exe": "Rocket League",

    # Minecraft
    "javaw.exe": "Minecraft (Java)",
    "minecraft.windows.exe": "Minecraft (Bedrock)",

    # Battle.net
    "overwatch.exe": "Overwatch 2",
    "diablo iv.exe": "Diablo IV",
    "hearthstone.exe": "Hearthstone",
    "wow.exe": "World of Warcraft",

    # Other
    "fifa23.exe": "FIFA 23",
    "fc24.exe": "EA FC 24",
    "apex_r5apex.exe": "Apex Legends",
    "r5apex.exe": "Apex Legends",
    "pubg_launch.exe": "PUBG",
    "tslgame.exe": "PUBG",
    "genshinimpact.exe": "Genshin Impact",
    "yuanshen.exe": "Genshin Impact",
    "among us.exe": "Among Us",
    "terraria.exe": "Terraria",
    "stardewvalley.exe": "Stardew Valley",
    "cyberpunk2077.exe": "Cyberpunk 2077",
    "hogwartslegacy.exe": "Hogwarts Legacy",
    "witcher3.exe": "The Witcher 3",
    "palworld-win64-shipping.exe": "Palworld",
    "fallguys_client_game.exe": "Fall Guys",
}

# Game tips by genre/game
GAME_TIPS = {
    "Valorant": [
        "💡 حاول تلعب Deathmatch قبل الراندد عشان تسخن الأيم",
        "💡 استخدم الـ Phantom لو بتلعب في مابات قريبة",
        "💡 الـ Crosshair Placement مهم أكتر من الأيم نفسه",
        "💡 متنساش تستخدم الـ utility بتاعت الـ Agent بتاعك",
        "💡 حاول تلعب مع تيم — الـ solo queue صعب",
    ],
    "League of Legends": [
        "💡 وارد الماب كتير — الـ vision بتكسب games",
        "💡 حاول تتعلم 2-3 champions كويس بدل ما تلعب كل حاجة",
        "💡 متلعبش وانت عصبي — tilt بيودي لـ losses أكتر",
        "💡 CS أهم من الـ kills في الـ laning phase",
    ],
    "CS2": [
        "💡 الـ Spray Control مهم — روح workshop maps وتمرن",
        "💡 اسمع صوت الخطوات — Sound بيفرق في CS",
        "💡 حاول تتعلم smokes مهمة لكل ماب",
    ],
    "Minecraft": [
        "💡 دايماً خد معاك Bucket of Water — بينقذك من السقوط",
        "💡 الـ Fortune enchantment على الـ pickaxe بيزود الـ diamonds",
        "💡 اعمل bed قبل ما تنزل الـ caves",
    ],
    "Minecraft (Java)": [
        "💡 دايماً خد معاك Bucket of Water — بينقذك من السقوط",
        "💡 الـ Fortune enchantment على الـ pickaxe بيزود الـ diamonds",
        "💡 اعمل bed قبل ما تنزل الـ caves",
    ],
    "Minecraft (Bedrock)": [
        "💡 دايماً خد معاك Bucket of Water — بينقذك من السقوط",
        "💡 الـ Fortune enchantment على الـ pickaxe بيزود الـ diamonds",
        "💡 اعمل bed قبل ما تنزل الـ caves",
    ],
    "Fortnite": [
        "💡 الـ building مهم — تمرن في الـ Creative mode",
        "💡 النزول في أماكن هادية أحسن لو بتتعلم",
        "💡 دايماً خد معاك healing items",
    ],
    "__default__": [
        "💡 خد بريك كل ساعة — عينيك وضهرك محتاجين راحة",
        "💡 اشرب مية — الترطيب بيحسن الأداء",
        "💡 متلعبش وانت تعبان — النوم أهم",
        "💡 حاول تلعب مع أصحابك — المتعة بتزيد",
    ],
}


# ============================================================================
# Game Stats Storage
# ============================================================================
class GameStats:
    """Tracks and persists game play statistics."""

    def __init__(self, path=None):
        self._path = path or os.path.join(_HERE, _STATS_PATH)
        self._data = self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"sessions": [], "daily": {}, "totals": {}}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def record_session(self, game, duration_minutes):
        """Record a completed game session."""
        today = datetime.now().strftime("%Y-%m-%d")
        session = {
            "game": game,
            "date": today,
            "duration_minutes": round(duration_minutes, 1),
            "timestamp": time.time(),
        }

        self._data["sessions"].append(session)
        # Keep last 200 sessions
        self._data["sessions"] = self._data["sessions"][-200:]

        # Daily tracking
        if today not in self._data["daily"]:
            self._data["daily"][today] = {}
        daily = self._data["daily"][today]
        daily[game] = daily.get(game, 0) + duration_minutes

        # Totals
        totals = self._data["totals"]
        totals[game] = totals.get(game, 0) + duration_minutes

        # Cleanup old daily data (keep 30 days)
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        self._data["daily"] = {
            k: v for k, v in self._data["daily"].items() if k >= cutoff
        }

        self._save()

    def get_daily(self, date=None):
        """Get play time for a specific date."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self._data["daily"].get(date, {})

    def get_weekly(self):
        """Get play time for the last 7 days."""
        result = defaultdict(float)
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            for game, minutes in self._data["daily"].get(date, {}).items():
                result[game] += minutes
        return dict(result)

    def get_total(self, game=None):
        """Get total play time."""
        if game:
            return self._data["totals"].get(game, 0)
        return self._data["totals"]

    def get_most_played(self, n=5):
        """Get top n most-played games."""
        totals = self._data["totals"]
        sorted_games = sorted(totals.items(), key=lambda x: -x[1])
        return sorted_games[:n]

    def summary_text(self):
        """Generate Arabic summary of play stats."""
        daily = self.get_daily()
        weekly = self.get_weekly()

        lines = []

        # Today
        if daily:
            total_today = sum(daily.values())
            games_today = ", ".join(
                f"{g} ({m:.0f}د)" for g, m in daily.items()
            )
            lines.append(f"📊 النهارده: {total_today:.0f} دقيقة — {games_today}")

        # This week
        if weekly:
            total_week = sum(weekly.values())
            hours = total_week / 60
            top_game = max(weekly, key=weekly.get)
            lines.append(
                f"📅 الأسبوع ده: {hours:.1f} ساعة | "
                f"أكتر لعبة: {top_game}"
            )

        # All time top
        most = self.get_most_played(3)
        if most:
            top_str = ", ".join(
                f"{g} ({m/60:.0f}س)" for g, m in most
            )
            lines.append(f"🏆 الأكتر لعباً: {top_str}")

        return "\n".join(lines) if lines else "مفيش إحصائيات لعب لسه"


# ============================================================================
# Game Companion
# ============================================================================
class GameCompanion:
    """Monitors games, tracks sessions, and provides companion features."""

    CHECK_INTERVAL = 10  # seconds between game detection checks

    def __init__(self, on_notify=None, on_overlay_update=None, llm_client=None):
        """
        Args:
            on_notify: callback(message) for break reminders etc.
            on_overlay_update: callback(perf_data) for overlay HUD
            llm_client: Groq client for game tips (optional)
        """
        self._on_notify = on_notify or (lambda m: None)
        self._on_overlay = on_overlay_update
        self._client = llm_client
        self._stats = GameStats()

        self._current_game = None
        self._session_start = None
        self._last_break_reminder = None
        self._running = False
        self._timer = None

        log.info("🎮 Game Companion initialized")

    # ── Public API ─────────────────────────────────────────────

    def start(self):
        """Start background monitoring."""
        if not _ENABLED or not _HAS_PSUTIL:
            log.warning("Game Companion disabled or psutil not installed")
            return
        self._running = True
        self._loop()
        log.info("🎮 Game Companion monitoring started")

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._timer:
            self._timer.cancel()
        # Save final session
        if self._current_game and self._session_start:
            self._end_session()

    def get_current_game(self):
        """Return the name of the currently running game, or None."""
        return self._current_game

    def get_session_time(self):
        """Return formatted session duration."""
        if not self._session_start:
            return None
        elapsed = time.time() - self._session_start
        return self._format_duration(elapsed)

    def get_session_minutes(self):
        """Return raw session minutes."""
        if not self._session_start:
            return 0
        return (time.time() - self._session_start) / 60

    def get_daily_stats(self):
        """Return today's play stats."""
        return self._stats.get_daily()

    def get_weekly_stats(self):
        """Return this week's play stats."""
        return self._stats.get_weekly()

    def get_stats_summary(self):
        """Return formatted stats summary."""
        return self._stats.summary_text()

    def get_tip(self, game=None):
        """Get a random tip for the current or specified game."""
        import random
        game = game or self._current_game
        tips = GAME_TIPS.get(game, GAME_TIPS["__default__"])
        return random.choice(tips)

    def get_smart_tip(self, game=None):
        """Get an AI-generated tip (requires LLM client)."""
        game = game or self._current_game
        if not game or not self._client or not _TIPS_ENABLED:
            return self.get_tip(game)

        try:
            session_min = self.get_session_minutes()
            prompt = (
                f"أنت مساعد ألعاب خبير. اللاعب بيلعب {game} "
                f"من {session_min:.0f} دقيقة. "
                f"أعطيه نصيحة واحدة مفيدة ومختصرة بالعامية المصرية "
                f"(جملة أو اتنين بس). ابدأ بـ 💡"
            )

            from retry_handler import api_call
            response = api_call(
                lambda: self._client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.8,
                ),
                fallback=None,
                service_name="groq_tips",
            )

            if response:
                return response.choices[0].message.content.strip()
        except Exception as e:
            log.debug(f"Smart tip failed: {e}")

        return self.get_tip(game)

    def get_performance(self):
        """Get current system performance metrics."""
        if not _HAS_PSUTIL:
            return None
        try:
            cpu = psutil.cpu_percent(interval=0)
            ram = psutil.virtual_memory().percent

            # Try to get GPU usage (optional)
            gpu = None
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0].load * 100
            except ImportError:
                pass

            return {
                "cpu": round(cpu, 1),
                "ram": round(ram, 1),
                "gpu": round(gpu, 1) if gpu else None,
            }
        except Exception:
            return None

    # ── Internal Loop ──────────────────────────────────────────

    def _loop(self):
        if not self._running:
            return

        try:
            self._check_games()
            self._check_break_reminder()
            self._update_performance()
        except Exception as e:
            log.error(f"Game companion loop error: {e}")

        self._timer = threading.Timer(self.CHECK_INTERVAL, self._loop)
        self._timer.daemon = True
        self._timer.start()

    def _check_games(self):
        """Detect which game is currently running."""
        detected = None

        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in KNOWN_GAMES:
                    if name == "javaw.exe":
                        try:
                            cmdline = " ".join(proc.cmdline() or []).lower()
                            if "minecraft" not in cmdline and "net.minecraft" not in cmdline:
                                continue
                        except Exception:
                            pass
                    detected = KNOWN_GAMES[name]
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if detected and detected != self._current_game:
            # New game started
            if self._current_game:
                self._end_session()
            self._start_session(detected)

        elif not detected and self._current_game:
            # Game closed
            self._end_session()

    def _start_session(self, game):
        """Start tracking a new game session."""
        self._current_game = game
        self._session_start = time.time()
        self._last_break_reminder = time.time()

        self._on_notify(f"🎮 {game} شغال — يوبي معاك! هفضل أتتبع الجلسة.")
        log.info(f"Game session started: {game}")

    def _end_session(self):
        """End current game session and save stats."""
        if not self._current_game or not self._session_start:
            return

        duration_min = (time.time() - self._session_start) / 60
        self._stats.record_session(self._current_game, duration_min)

        formatted = self._format_duration(time.time() - self._session_start)
        self._on_notify(
            f"🎮 خلصت جلسة {self._current_game}\n"
            f"⏱️ المدة: {formatted}\n"
            f"{self.get_tip(self._current_game)}"
        )
        log.info(
            f"Game session ended: {self._current_game} "
            f"({duration_min:.1f} min)"
        )

        self._current_game = None
        self._session_start = None

    def _check_break_reminder(self):
        """Remind the user to take a break."""
        if not self._current_game or not self._session_start:
            return
        if not self._last_break_reminder:
            return

        elapsed = time.time() - self._last_break_reminder
        if elapsed >= _BREAK_MINUTES * 60:
            session_time = self._format_duration(
                time.time() - self._session_start
            )
            self._on_notify(
                f"⏰ إنت بتلعب {self._current_game} من {session_time}\n"
                f"خد بريك شوية — عينيك وضهرك محتاجين راحة! 🧘"
            )
            self._last_break_reminder = time.time()

    def _update_performance(self):
        """Send performance data to overlay if available."""
        if not _PERF_MONITOR or not self._on_overlay:
            return
        if not self._current_game:
            return

        perf_data = self.get_performance()
        if perf_data:
            self._on_overlay(perf_data)

    @staticmethod
    def _format_duration(seconds):
        """Format seconds to Arabic duration string."""
        minutes = int(seconds / 60)
        if minutes >= 60:
            hours = minutes // 60
            mins = minutes % 60
            if mins:
                return f"{hours} ساعة و {mins} دقيقة"
            return f"{hours} ساعة"
        return f"{minutes} دقيقة"


# ============================================================================
# Query handler — for voice commands about games
# ============================================================================
def handle_game_query(command, companion):
    """Handle voice commands related to games.

    Returns response text or None if not a game query.
    """
    cmd = command.lower().strip()

    # Current game
    if any(w in cmd for w in ["بلعب ايه", "بلعب إيه", "اي لعبة", "أي لعبة",
                               "what am i playing", "current game"]):
        game = companion.get_current_game()
        if game:
            session = companion.get_session_time()
            return f"🎮 إنت بتلعب {game} من {session}"
        return "مش لاقي أي لعبة شغالة دلوقتي 🤷"

    # Session time (require game-specific phrasing so general "قد ايه" questions aren't hijacked)
    if any(w in cmd for w in ["بلعب من امتى", "بلعب من إمتى", "بلعب بقالي قد ايه", "بلعب بقالي قد إيه",
                               "بقالي قد ايه بلعب", "بقالي قد إيه بلعب", "وقت اللعب",
                               "how long have i been playing", "session time"]):
        game = companion.get_current_game()
        if game:
            session = companion.get_session_time()
            return f"⏱️ إنت بتلعب {game} من {session}"
        return "مش بتلعب حاجة دلوقتي"

    # Stats
    if any(w in cmd for w in ["احصائيات اللعب", "إحصائيات اللعب", "احصائيات الالعاب", "إحصائيات الألعاب",
                               "game stats", "ستاتس اللعب", "لعبت قد ايه", "لعبت قد إيه"]):
        return companion.get_stats_summary()

    # Tips
    if any(w in cmd for w in ["نصيحة للعبة", "نصيحه للعبه", "نصيحة لعب", "game tip", "game tips"]):
        return companion.get_smart_tip()

    # Performance
    if any(w in cmd for w in ["أداء اللعبة", "اداء اللعبة", "أداء اللعبه", "اداء اللعبه",
                               "game performance", "fps"]):
        perf_data = companion.get_performance()
        if perf_data:
            lines = [f"📊 أداء الجهاز:"]
            lines.append(f"  CPU: {perf_data['cpu']}%")
            lines.append(f"  RAM: {perf_data['ram']}%")
            if perf_data.get("gpu") is not None:
                lines.append(f"  GPU: {perf_data['gpu']}%")
            return "\n".join(lines)
        return "مش قادر أقرأ أداء الجهاز"

    return None