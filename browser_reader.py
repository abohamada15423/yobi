# -*- coding: utf-8 -*-
"""
Browser Reader — يقرا bookmarks والـ history من المتصفحات.

Chrome/Edge/Brave بيخزنوا البيانات في JSON + SQLite. Firefox في SQLite.
لما المتصفح شغال، بيقفل ملفات الـ SQLite، فبناخد نسخة مؤقتة قبل القراءة.
(Recovered from bytecode.)
"""

import json
import os
import shutil
import sqlite3
import tempfile


def _chrome_like_bookmarks(user_data_dir):
    path = os.path.join(user_data_dir, "Default", "Bookmarks")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    out = []

    def _walk(node):
        if node.get("type") == "url":
            out.append({"name": node.get("name", ""), "url": node.get("url", "")})
        for child in node.get("children", []) or []:
            _walk(child)

    roots = data.get("roots", {})
    for key in ("bookmark_bar", "other", "synced"):
        if key in roots:
            _walk(roots[key])
    return out


def _chrome_like_history(user_data_dir, limit=500):
    src = os.path.join(user_data_dir, "Default", "History")
    if not os.path.exists(src):
        return []
    tmp = os.path.join(tempfile.gettempdir(), f"yobi_hist_{os.getpid()}.db")
    try:
        shutil.copy2(src, tmp)
    except Exception:
        return []
    rows = []
    try:
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        cur.execute(
            "SELECT url, title, visit_count FROM urls ORDER BY last_visit_time DESC LIMIT ?",
            (limit,),
        )
        rows = [{"url": r[0], "title": r[1], "visits": r[2]} for r in cur.fetchall()]
        conn.close()
    except Exception:
        rows = []
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return rows


def _firefox_bookmarks():
    base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
    if not os.path.isdir(base):
        return []
    out = []
    for prof in os.listdir(base):
        db = os.path.join(base, prof, "places.sqlite")
        if not os.path.exists(db):
            continue
        tmp = os.path.join(tempfile.gettempdir(), f"yobi_ff_{os.getpid()}.db")
        try:
            shutil.copy2(db, tmp)
            conn = sqlite3.connect(tmp)
            cur = conn.cursor()
            cur.execute(
                "SELECT b.title, p.url FROM moz_bookmarks b JOIN moz_places p "
                "ON b.fk = p.id WHERE b.type = 1 LIMIT 500"
            )
            for title, url in cur.fetchall():
                out.append({"name": title or "", "url": url})
            conn.close()
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return out


_CHROMIUM_DIRS = (
    ("chrome", r"Google\Chrome\User Data"),
    ("edge", r"Microsoft\Edge\User Data"),
    ("brave", r"BraveSoftware\Brave-Browser\User Data"),
)


def get_all_bookmarks():
    local = os.environ.get("LOCALAPPDATA", "")
    result = {"chrome": [], "edge": [], "firefox": [], "brave": []}
    for key, sub in _CHROMIUM_DIRS:
        d = os.path.join(local, sub)
        if not os.path.isdir(d):
            continue
        result[key] = _chrome_like_bookmarks(d)
    result["firefox"] = _firefox_bookmarks()
    return result


def get_all_history(limit_per_browser=300):
    local = os.environ.get("LOCALAPPDATA", "")
    result = {}
    for key, sub in _CHROMIUM_DIRS[:2]:
        d = os.path.join(local, sub)
        if os.path.isdir(d):
            result[key] = _chrome_like_history(d, limit_per_browser)
    return result


def search_bookmarks(query):
    q = (query or "").lower().strip()
    if not q:
        return []
    hits = []
    for browser, items in get_all_bookmarks().items():
        for b in items:
            if q in (b.get("name") or "").lower() or q in (b.get("url") or "").lower():
                hits.append({**b, "browser": browser})
    return hits[:5]


def search_history(query, limit=5):
    q = (query or "").lower().strip()
    if not q:
        return []
    hits = []
    for browser, items in get_all_history().items():
        for h in items:
            if q in (h.get("url") or "").lower() or q in (h.get("title") or "").lower():
                hits.append({**h, "browser": browser})
                if len(hits) >= limit:
                    return hits
    return hits
