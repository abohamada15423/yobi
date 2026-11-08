# -*- coding: utf-8 -*-
"""
Media & Search Handler — ذكاء تشغيل الأغاني، الأفلام، والبحث على الويب ليوبي.

يتعامل مع:
  1. تشغيل الأغاني والتراكات والقرآن والبلاي ليست ("شغل اغنية عمرو دياب", "شغل سورة الكهف", "شغل تراك بيانو هادي")
  2. مشاهدة الأفلام والمسلسلات والأنمي ("شغل فيلم Interstellar", "عايز اتفرج على مسلسل ...")
  3. البحث في جوجل ويوتيوب ("ابحث عن أفضل لابتوب 2026", "دور في يوتيوب على شرح بايثون")
  4. فتح المواقع الذكي ("افتح موقع كورة", "روح موقع حاسوب")
"""

import re
import urllib.parse
import webbrowser


def _matches_known_target(query, agent):
    """True if `query` actually names something the agent already knows how
    to open (using v7 Catalog resolver when available)."""
    if hasattr(agent, "resolve"):
        try:
            r = agent.resolve(query)
            return r.status == "ok" and r.score >= 0.88
        except Exception:
            pass
    try:
        from app_scanner import resolve_target
        all_known = (
            list(agent.websites.keys())
            + list(getattr(agent, "local_apps", {}).keys())
            + list(getattr(agent, "installed_apps", {}).keys())
            + list(getattr(agent, "games", {}).keys())
        )
        return resolve_target(query, all_known) is not None
    except Exception:
        return False


def handle_media_or_search(command, agent):
    """
    Checks if command is a music, movie, web search, or website intent.
    Returns (handled: bool, message: str)
    """
    cmd = (command or "").strip().lower()
    if not cmd:
        return False, ""

    # ─────────────────────────────────────────────────────────────
    # 1. Music & Songs & Audio
    # ─────────────────────────────────────────────────────────────
    if cmd in [
        "شغل اغاني", "شغل أغاني", "شغل مزيكا", "شغل ميوزك",
        "play music", "شغل موسيقى", "عايز اسمع اغاني", "شغل بلاي ليست",
    ]:
        res = agent.open_target("spotify")
        if "مش لاقي" not in res:
            return True, "شغلتلك سبوتيفاي 🎵"
        webbrowser.open("https://open.spotify.com")
        return True, "فتحتلك سبوتيفاي ويب 🎵"

    # Specific track / artist / song / quran / playlist
    music_patterns = [
        (r"(?:شغل|اسمع|عايز اسمع|سمعني|play)\s+(?:سورة|قرآن|قران)\s+(.+)", "سورة "),
        (r"(?:شغل|اسمع|عايز اسمع|سمعني|play)\s+(?:بلاي ليست|playlist)\s+(.+)", "playlist "),
        (r"(?:شغل|اسمع|عايز اسمع|سمعني|play)\s+(?:موسيقى|مزيكا)\s+(.+)", "موسيقى "),
        (r"(?:شغل|اسمع|عايز اسمع|سمعني|play)\s+(?:اغنية|أغنية|تراك|track|song)\s+(.+)", ""),
        (r"(?:شغل|اسمع|عايز اسمع|سمعني)\s+اغاني\s+(.+)", "أغاني "),
    ]
    for pat, prefix in music_patterns:
        m = re.match(pat, cmd)
        if m:
            query = m.group(1).strip()
            if len(query) < 2:
                continue
            full_q = f"{prefix}{query}".strip()
            encoded = urllib.parse.quote_plus(full_q)
            url = f"https://www.youtube.com/results?search_query={encoded}"
            webbrowser.open(url)
            return True, f"شغلتلك '{full_q}' على يوتيوب 🎵"

    # ─────────────────────────────────────────────────────────────
    # 2. Movies & Series & Anime
    # ─────────────────────────────────────────────────────────────
    if cmd in [
        "افتح فيلم", "شغل فيلم", "عايز اتفرج على فيلم",
        "عايز اتفرج على حاجة", "عايز اشوف فيلم", "watch movie",
    ]:
        webbrowser.open("https://www.netflix.com")
        return True, "فتحتلك نتفليكس للمشاهدة 🍿"

    movie_patterns = [
        r"(?:شغل|افتح|عايز اتفرج على|وريني|عايز اشوف|watch)\s+(?:فيلم|مسلسل|انمي|أنمي)\s+(.+)",
        r"^(?:فيلم|مسلسل|انمي|أنمي)\s+(.+)",
    ]
    for pat in movie_patterns:
        m = re.match(pat, cmd)
        if m:
            target_name = m.group(1).strip()
            if len(target_name) < 2:
                continue

            is_anime = any(w in cmd for w in ["انمي", "أنمي"])
            is_series = "مسلسل" in cmd
            search_prefix = (
                "مشاهدة انمي " if is_anime
                else "مشاهدة مسلسل " if is_series
                else "مشاهدة فيلم "
            )
            encoded = urllib.parse.quote_plus(f"{search_prefix}{target_name}")
            url = f"https://www.google.com/search?q={encoded}"
            webbrowser.open(url)
            return True, f"فتحتلك البحث عن '{target_name}' 🎬"

    # ─────────────────────────────────────────────────────────────
    # 3. Web Search (Google / YouTube)
    # ─────────────────────────────────────────────────────────────
    if any(cmd.startswith(prefix) for prefix in ["ابحث في يوتيوب عن", "دور في يوتيوب على", "سيرش يوتيوب على"]):
        q = re.sub(r"^(?:ابحث في يوتيوب عن|دور في يوتيوب على|سيرش يوتيوب على)\s*", "", cmd).strip()
        if q and not _matches_known_target(q, agent):
            encoded = urllib.parse.quote_plus(q)
            webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
            return True, f"بحثتلك في يوتيوب عن '{q}' 🔍"

    search_patterns = [
        r"^(?:ابحث|سيرش|دور|search)\s+(?:عن|في جوجل عن|في جوجل|على|جوجل)?\s*(.+)",
        r"^جوجل\s+(.+)",
    ]
    for pat in search_patterns:
        m = re.match(pat, cmd)
        if m:
            q = m.group(1).strip()
            if len(q) > 1 and not _matches_known_target(q, agent):
                encoded = urllib.parse.quote_plus(q)
                webbrowser.open(f"https://www.google.com/search?q={encoded}")
                return True, f"بحثتلك في جوجل عن '{q}' 🔍"

    # ─────────────────────────────────────────────────────────────
    # 4. Explicit Website Intent ("افتح موقع X")
    # ─────────────────────────────────────────────────────────────
    site_match = re.match(r"^(?:افتح|روح|ادخل|شغل)\s+(?:موقع|ويب سايت|لينك)\s+(.+)", cmd)
    if site_match:
        site_name = site_match.group(1).strip()
        res = agent.open_target(site_name)
        if "مش لاقي" not in res:
            return True, res
        encoded = urllib.parse.quote_plus(f"موقع {site_name}")
        webbrowser.open(f"https://www.google.com/search?q={encoded}")
        return True, f"فتحتلك البحث عن موقع {site_name} 🌐"

    return False, ""