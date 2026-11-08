# -*- coding: utf-8 -*-
"""
File Operations — عمليات الملفات والفولدرات ليوبي.

Commands handled:
  • "افتح (فولدر) التحميلات / المستندات / الديسكتوب / الصور" → open in Explorer
  • "اعمل فولدر اسمه X" → create on Desktop by default
  • "فين فايل اسمه X؟" / "دور على فايل X" → search common user folders
  • "افتح آخر ملف (في التحميلات)" → open most recently modified file
  • "روق / رتب / نظم (فولدر) التحميلات / الديسكتوب" → organize loose files by category
  • "ايه اللي في فولدر X؟" → list contents
  • "امسح فايل X" → delete file to Recycle Bin (with confirmation)

match_file_command(command) mirrors system_control.match_system_command:
returns (action_fn, description, needs_confirmation) or None.
"""

import os
import platform
import re
import shutil
import subprocess

CURRENT_OS = platform.system().lower()


# ---------------------------------------------------------------------------
# Common folder aliases → Windows shell folder names
# ---------------------------------------------------------------------------
_COMMON_FOLDERS = {
    "التحميلات": "Downloads", "التحميل": "Downloads", "تحميلات": "Downloads",
    "الداونلودز": "Downloads", "الداونلود": "Downloads",
    "داونلود": "Downloads", "داونلودز": "Downloads", "downloads": "Downloads",
    "المستندات": "Documents", "مستندات": "Documents", "documents": "Documents",
    "سطح المكتب": "Desktop", "الديسكتوب": "Desktop", "ديسكتوب": "Desktop",
    "ال desktop": "Desktop", "desktop": "Desktop",
    "الصور": "Pictures", "صور": "Pictures", "pictures": "Pictures",
    "الفيديوهات": "Videos", "فيديوهات": "Videos", "الفيديو": "Videos",
    "videos": "Videos",
    "الموسيقى": "Music", "موسيقى": "Music", "music": "Music",
    "الاغاني": "Music", "أغاني": "Music",
}

_SEARCH_ROOTS = [
    "Downloads", "Documents", "Desktop", "Pictures", "Videos", "Music",
]

_SEARCH_DEPTH = 5
_SEARCH_MAX_RESULTS = 3

_CATEGORY_EXTS = {
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"},
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".md"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".iso"},
    "Code": {".py", ".ipynb", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".cs", ".java", ".json", ".sql"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".webm"},
    "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
}


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------
def _user_home():
    return os.path.expanduser("~")


def _resolve_common_folder(name):
    """Resolve a folder alias ('Downloads', 'المستندات', ...) to an absolute
    path, checking both the user profile and OneDrive redirects."""
    home = _user_home()
    candidates = [
        os.path.join(home, name),
        os.path.join(home, "OneDrive", name),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def _desktop_path():
    return _resolve_common_folder("Desktop") or os.path.join(_user_home(), "Desktop")


def _open_path(path):
    """Open a file or folder with the default OS handler."""
    try:
        if CURRENT_OS == "windows":
            os.startfile(path)
        elif CURRENT_OS == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
def open_folder(path):
    if not os.path.isdir(path):
        return f"مش لاقي الفولدر: {path}"
    if _open_path(path):
        return f"فتحت فولدر {os.path.basename(path)} 📁"
    return "معرفتش أفتح الفولدر"


def create_folder(name):
    """Create a folder on the Desktop."""
    name = name.strip().strip('"').strip("'")
    if not name:
        return "مفيش اسم للفولدر"

    name = re.sub(r"^(?:اسمه|اسمها|باسم|called)\s+", "", name).strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    if not name:
        return "الاسم مش صالح"

    target = os.path.join(_desktop_path(), name)
    if os.path.exists(target):
        return f"الفولدر '{name}' موجود بالفعل"
    try:
        os.makedirs(target)
        return f"عملت فولدر '{name}' على الديسكتوب ✅"
    except OSError as e:
        return f"معرفتش أعمل الفولدر: {e}"


def open_latest_file(folder_hint=None):
    """Find and open the most recently modified file in Downloads/Desktop/Documents."""
    roots = []
    if folder_hint:
        for alias, folder in _COMMON_FOLDERS.items():
            if alias in folder_hint.lower():
                p = _resolve_common_folder(folder)
                if p:
                    roots.append(p)
                break
    if not roots:
        for r in ("Downloads", "Desktop", "Documents"):
            p = _resolve_common_folder(r)
            if p:
                roots.append(p)

    latest_path = None
    latest_mtime = 0.0
    for root in roots:
        try:
            for entry in os.scandir(root):
                if entry.is_file() and not entry.name.startswith(".") and not entry.name.lower().endswith((".ini", ".lnk", ".tmp", ".crdownload")):
                    st = entry.stat()
                    if st.st_mtime > latest_mtime:
                        latest_mtime = st.st_mtime
                        latest_path = entry.path
        except (OSError, PermissionError):
            continue

    if not latest_path:
        return "مش لاقي ملفات حديثة"
    if _open_path(latest_path):
        return f"فتحت آخر ملف: {os.path.basename(latest_path)} ✅"
    return f"آخر ملف هو: {os.path.basename(latest_path)}"


def organize_folder(path, confirmed=False):
    """Organize loose files in `path` into categorized subfolders (skips .lnk shortcuts)."""
    if not confirmed:
        return "محتاج تأكيد قبل ترتيب الملفات"
    if not path or not os.path.isdir(path):
        return "مش لاقي الفولدر المطلوب"

    moved = 0
    try:
        for entry in os.scandir(path):
            if not entry.is_file():
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            # Never move Desktop shortcuts or system ini files
            if ext in (".lnk", ".url", ".ini") or entry.name.startswith("."):
                continue
            target_cat = None
            for cat, exts in _CATEGORY_EXTS.items():
                if ext in exts:
                    target_cat = cat
                    break
            if not target_cat:
                continue
            cat_dir = os.path.join(path, target_cat)
            os.makedirs(cat_dir, exist_ok=True)
            dst = os.path.join(cat_dir, entry.name)
            if os.path.exists(dst):
                continue
            shutil.move(entry.path, dst)
            moved += 1
    except Exception as e:
        return f"حصلت مشكلة أثناء الترتيب: {e}"

    if moved == 0:
        return f"فولدر {os.path.basename(path)} مترتب وجاهز أصلاً ✨"
    return f"رتبت ونظمت {moved} ملف في فولدر {os.path.basename(path)} ✅"


def list_folder(name):
    """List contents of a folder (alias or absolute path)."""
    name = name.strip().strip('"').strip("'")
    path = None

    for alias, folder in _COMMON_FOLDERS.items():
        if alias in name.lower():
            path = _resolve_common_folder(folder)
            break

    if not path:
        for base in ("Desktop", "Documents", "Downloads"):
            base_path = _resolve_common_folder(base)
            if not base_path:
                continue
            candidate = os.path.join(base_path, name)
            if os.path.isdir(candidate):
                path = candidate
                break

    if not path or not os.path.isdir(path):
        return f"مش لاقي فولدر اسمه '{name}'"

    try:
        entries = os.listdir(path)
    except OSError as e:
        return f"معرفتش أقرا الفولدر: {e}"

    if not entries:
        return f"فولدر '{os.path.basename(path)}' فاضي"

    folders = [e for e in entries if os.path.isdir(os.path.join(path, e))]
    files = [e for e in entries if not os.path.isdir(os.path.join(path, e))]

    summary = f"فولدر '{os.path.basename(path)}' فيه {len(folders)} فولدر و {len(files)} فايل."
    preview = files[:5]
    if preview:
        summary += " أول فايلات: " + ", ".join(preview)
    return summary


def search_files(name):
    """Search common user folders for a file matching `name`. Depth-limited."""
    name = name.strip().strip('"').strip("'")
    if not name:
        return "مفيش اسم للفايل"

    name_l = name.lower()
    roots = []
    for r in _SEARCH_ROOTS:
        p = _resolve_common_folder(r)
        if p:
            roots.append(p)

    if not roots:
        return "مفيش فولدرات للبحث فيها"

    matches = []

    def _walk(root, depth=0):
        if depth > _SEARCH_DEPTH or len(matches) >= _SEARCH_MAX_RESULTS:
            return
        try:
            for entry in os.scandir(root):
                if len(matches) >= _SEARCH_MAX_RESULTS:
                    return
                try:
                    if name_l in entry.name.lower():
                        matches.append(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        _walk(entry.path, depth + 1)
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            return

    for root in roots:
        _walk(root)
        if len(matches) >= _SEARCH_MAX_RESULTS:
            break

    if not matches:
        return f"مش لاقي فايل فيه '{name}'"

    if len(matches) == 1:
        if _open_path(matches[0]):
            return f"لقيت الفايل: {os.path.basename(matches[0])} — فتحته ✅"
        return f"لقيت الفايل في: {matches[0]}"

    names = [os.path.basename(m) for m in matches]
    return f"لقيت {len(matches)} ملفات: " + ", ".join(names)


def delete_file(name, confirmed=False):
    """Delete a file by name (searches common folders first)."""
    if not confirmed:
        return "محتاج تأكيد قبل المسح"

    name = name.strip().strip('"').strip("'")
    if not name:
        return "مفيش اسم للفايل"

    roots = [_resolve_common_folder(r) for r in _SEARCH_ROOTS]
    roots = [r for r in roots if r]

    target = None
    name_l = name.lower()

    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            for f in filenames:
                if name_l in f.lower():
                    target = os.path.join(dirpath, f)
                    break
            if target:
                break
        if target:
            break

    if not target:
        return f"مش لاقي فايل اسمه '{name}'"

    try:
        if CURRENT_OS == "windows":
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_uint16),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR),
                ]

            FO_DELETE = 3
            FOF_ALLOWUNDO = 0x40
            FOF_NOCONFIRMATION = 0x10
            FOF_SILENT = 0x04
            FOF_NOERRORUI = 0x0400

            op = SHFILEOPSTRUCTW()
            op.hwnd = None
            op.wFunc = FO_DELETE
            op.pFrom = target + "\0\0"
            op.pTo = None
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
            op.fAnyOperationsAborted = False
            op.hNameMappings = None
            op.lpszProgressTitle = None

            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if result != 0:
                return f"معرفتش أمسح الملف (كود {result})"
        else:
            os.remove(target)

        return f"مسحت '{os.path.basename(target)}' 🗑️ (راح للسلة)"
    except Exception as e:
        return f"معرفتش أمسح الملف: {e}"


# ---------------------------------------------------------------------------
# Phrase matching — returns (action_fn, description, needs_confirm) or None
# ---------------------------------------------------------------------------
def match_file_command(command):
    """Match a spoken command against known file operations."""
    cmd = (command or "").lower().strip()
    cmd_clean = re.sub(r"\s+", " ", cmd)

    # ── Organize / clean up folder ("روق الديسكتوب", "رتب فولدر التحميلات") ──
    if any(v in cmd_clean for v in ["روق", "رتب", "نظم", "نضف"]):
        for alias in sorted(_COMMON_FOLDERS, key=len, reverse=True):
            if alias in cmd_clean:
                path = _resolve_common_folder(_COMMON_FOLDERS[alias])
                if path:
                    return (
                        lambda p=path: organize_folder(p, confirmed=True),
                        f"ترتيب وتنظيم فولدر {alias}",
                        True,
                    )

    # ── Open latest file ("افتح آخر ملف كنت شغال عليه", "افتح آخر ملف في التحميلات") ──
    if any(p in cmd_clean for p in ["آخر ملف", "اخر ملف", "آخر فايل", "اخر فايل"]):
        return (
            lambda c=cmd_clean: open_latest_file(c),
            "فتح آخر ملف",
            False,
        )

    # ── Open common folder ("افتح فولدر التحميلات" OR "افتح التحميلات" / "افتح الداونلودز") ──
    open_verbs = ["افتح", "افتحلي", "روح", "خدني", "عايز", "وريني", "شوف",
                  "open", "go to", "show me"]
    if any(v in cmd_clean for v in open_verbs):
        has_folder_word = any(w in cmd_clean for w in ["فولدر", "مجلد", "folder"])
        for alias in sorted(_COMMON_FOLDERS, key=len, reverse=True):
            if has_folder_word and alias in cmd_clean:
                path = _resolve_common_folder(_COMMON_FOLDERS[alias])
                if path:
                    return (lambda p=path: open_folder(p), f"فتح فولدر {alias}", False)
            elif re.search(rf"(?:^|\s){re.escape(alias)}(?:\s|$)", cmd_clean) and len(cmd_clean.split()) <= 4:
                path = _resolve_common_folder(_COMMON_FOLDERS[alias])
                if path:
                    return (lambda p=path: open_folder(p), f"فتح فولدر {alias}", False)

    # ── Create folder ─────────────────────────────────────────
    m = re.search(
        r"(?:اعمل|اضف|أضف|انشئ|أنشئ|اضيف|أضيف|create|make)\s+"
        r"(?:لي\s+)?(?:فولدر|مجلد|folder)\s+"
        r"(?:اسمه|اسمها|باسم|called|سميه|سميها)?\s*(.+)",
        cmd_clean,
    )
    if m:
        name = m.group(1).strip()
        if name:
            return (
                lambda n=name: create_folder(n),
                f"إنشاء فولدر '{name}'",
                True,
            )

    # ── Search for file ──────────────────────────────────────
    m = re.search(
        r"(?:فين|دور على|دورلي على|ابحث عن|هاتلي|عايز|find|search)\s+"
        r"(?:فايل|ملف|file)\s+"
        r"(?:اسمه|اسمها|باسم|called)?\s*(.+)",
        cmd_clean,
    )
    if m:
        name = m.group(1).strip()
        if name:
            return (
                lambda n=name: search_files(n),
                f"البحث عن ملف '{name}'",
                False,
            )

    # ── List folder contents ─────────────────────────────────
    m = re.search(
        r"(?:ايه|إيه|whats|what's)\s+(?:اللي\s+)?في\s+"
        r"(?:فولدر|مجلد|folder)?\s*(.+)",
        cmd_clean,
    )
    if m:
        name = m.group(1).strip()
        if name:
            return (
                lambda n=name: list_folder(n),
                f"محتويات فولدر '{name}'",
                False,
            )

    # ── Delete file ──────────────────────────────────────────
    m = re.search(
        r"(?:امسح|احذف|delete|remove)\s+"
        r"(?:فايل|ملف|file)\s+"
        r"(?:اسمه|اسمها|باسم|called)?\s*(.+)",
        cmd_clean,
    )
    if m:
        name = m.group(1).strip()
        if name:
            return (
                lambda n=name: delete_file(n, confirmed=True),
                f"مسح ملف '{name}'",
                True,
            )

    return None