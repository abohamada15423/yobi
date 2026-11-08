# -*- coding: utf-8 -*-
"""
App Scanner — finds installed programs on Windows via the registry,
plus Start Menu shortcuts, and resolves spoken targets to the best match.
"""

import difflib
import json
import os
import re

try:
    import winreg
except ImportError:
    winreg = None

from aliases import normalize_name


_UNWANTED_EXE_WORDS = {
    "uninstall", "unins000", "unins001", "setup", "installer", "update",
    "updater", "crashhandler", "crash_handler", "crashpad", "vcredist",
    "vc_redist", "helper", "log-uploader",
}

_UNWANTED_PATH_PARTS = (
    "\\package cache\\",
)

_UNWANTED_NAME_RE = re.compile(
    r"(^uninstall\b|\buninstall\b|\bmanual\b|\bhelp\b|release notes|"
    r"documentation|what is new|visit developer homepage|visit product homepage|"
    r"check for updates|about java|reset settings|reset options|reset keymapper|"
    r"unload kernel module|telemetry log|install additional tools|install movie codec|"
    r"video instructions|sample desktop apps|sample uwp apps|tools for desktop apps|"
    r"tools for uwp apps)",
    re.I,
)


def _is_unwanted_exe(path_or_name):
    p_low = str(path_or_name or "").lower()
    if any(part in p_low for part in _UNWANTED_PATH_PARTS):
        return True
    name = re.split(r"[\\/]", p_low)[-1]
    return any(w in name for w in _UNWANTED_EXE_WORDS)


def _is_unwanted_app_name(name):
    n = (name or "").strip().lower()
    if not n or len(n) < 2:
        return True
    return bool(_UNWANTED_NAME_RE.search(n))


def _clean_apps_dict(apps):
    """Purge empty keys, uninstallers, manuals, and package-cache stubs."""
    cleaned = {}
    for k, v in (apps or {}).items():
        k_str = (k or "").strip().lower()
        v_str = str(v or "").strip()
        if not k_str and "playgtav.exe" in v_str.lower():
            k_str = "grand theft auto v"
        if _is_unwanted_app_name(k_str) or _is_unwanted_exe(v_str):
            continue
        cleaned[k_str] = v
    return cleaned


def _find_best_exe_in_dir(install_loc, display_name):
    """Search install_loc (and 1 level deep) for the best executable."""
    if not install_loc or not os.path.isdir(install_loc):
        return None

    clean_disp = "".join(c for c in display_name.lower() if c.isalnum())
    candidates = []

    try:
        for fname in os.listdir(install_loc):
            if fname.lower().endswith(".exe"):
                candidates.append(os.path.join(install_loc, fname))

        for entry in os.listdir(install_loc):
            sub = os.path.join(install_loc, entry)
            if os.path.isdir(sub) and entry.lower() in ("game", "bin", "binaries", "app", "application", "client"):
                for subfile in os.listdir(sub):
                    if subfile.lower().endswith(".exe"):
                        candidates.append(os.path.join(sub, subfile))
    except (OSError, PermissionError):
        return None

    if not candidates:
        return None

    for c in candidates:
        base = os.path.splitext(os.path.basename(c))[0].lower()
        clean_base = "".join(ch for ch in base if ch.isalnum())
        if not _is_unwanted_exe(c) and (clean_base in clean_disp or clean_disp in clean_base):
            return c

    for c in candidates:
        if not _is_unwanted_exe(c):
            return c

    return None


def get_installed_apps_registry():
    apps = {}
    if winreg is None:
        return apps

    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for root_key, reg_path in registry_paths:
        try:
            with winreg.OpenKey(root_key, reg_path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_key_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub_key_name) as sub_key:
                            display_name = str(winreg.QueryValueEx(sub_key, "DisplayName")[0]).strip()
                            if _is_unwanted_app_name(display_name):
                                continue

                            try:
                                display_icon = winreg.QueryValueEx(sub_key, "DisplayIcon")[0]
                                exe_path = display_icon.split(",")[0].strip('"')
                                if (exe_path.lower().endswith(".exe")
                                        and os.path.exists(exe_path)
                                        and not _is_unwanted_exe(exe_path)):
                                    apps[display_name.lower()] = exe_path
                                    continue
                            except (OSError, ValueError):
                                pass

                            try:
                                install_loc = winreg.QueryValueEx(sub_key, "InstallLocation")[0]
                                best_exe = _find_best_exe_in_dir(install_loc, display_name)
                                if best_exe:
                                    apps[display_name.lower()] = best_exe
                                    continue
                            except (OSError, ValueError):
                                pass
                    except (OSError, ValueError):
                        continue
        except OSError:
            continue

    return apps


def _scan_start_menu():
    """Scan Start Menu and Desktop shortcuts (.lnk) for apps and games."""
    apps = {}
    user_prof = os.environ.get("USERPROFILE", "")
    public_prof = os.environ.get("PUBLIC", r"C:\Users\Public")

    search_dirs = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.join(user_prof, "Desktop"),
        os.path.join(user_prof, "OneDrive", "Desktop"),
        os.path.join(public_prof, "Desktop"),
    ]

    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
    except ImportError:
        shell = None

    for sdir in search_dirs:
        if not os.path.isdir(sdir):
            continue
        for root, _, files in os.walk(sdir):
            for fname in files:
                if not fname.lower().endswith(".lnk"):
                    continue
                lnk_path = os.path.join(root, fname)
                try:
                    name = fname[:-4].lower().replace(" - shortcut", "").strip()
                    if _is_unwanted_app_name(name):
                        continue

                    target_path = None
                    if shell:
                        try:
                            shortcut = shell.CreateShortCut(lnk_path)
                            target_path = shortcut.Targetpath
                        except Exception:
                            pass

                    if target_path and target_path.lower().endswith(".exe") and os.path.exists(target_path):
                        if not _is_unwanted_exe(target_path):
                            apps[name] = target_path
                    elif os.path.exists(lnk_path) and not _is_unwanted_exe(target_path or ""):
                        if name not in apps:
                            apps[name] = lnk_path
                except Exception:
                    continue

    return apps


_AUTO_ALIASES = {
    "visual studio code": "vscode",
    "google chrome": "chrome",
    "mozilla firefox": "firefox",
    "microsoft edge": "edge",
    "obs studio": "obs",
    "vlc media player": "vlc",
    "windows terminal": "terminal",
    "file explorer": "explorer",
    "task manager": "taskmgr",
    "microsoft word": "word",
    "microsoft excel": "excel",
    "microsoft powerpoint": "powerpoint",
    "adobe photoshop": "photoshop",
    "adobe premiere pro": "premiere",
    "epic games launcher": "epic games",
    "tlauncher": "minecraft",
    "personal - edge": "edge",
    "rockstar games launcher": "rockstar",
    "wand (wemod)": "wemod",
}


def _add_auto_aliases(apps):
    extra = {}
    for long_name, short_name in _AUTO_ALIASES.items():
        for app_key in list(apps.keys()):
            if long_name in app_key and short_name not in apps:
                extra[short_name] = apps[app_key]
                break
    apps.update(extra)


def _safe_print(text):
    try:
        print(text)
    except Exception:
        pass


def load_or_scan_installed_apps(cache_path, os_name, force_rescan=False):
    if not force_rescan and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cleaned = _clean_apps_dict(raw)
            if len(cleaned) != len(raw):
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned, f, ensure_ascii=False, indent=2)
            return cleaned
        except (OSError, json.JSONDecodeError):
            pass

    _safe_print("🔍 جاري فحص الريجستري والـ Start Menu وسطح المكتب للبحث عن البرامج...")
    apps = {}
    if os_name == "windows":
        apps = get_installed_apps_registry()
        start_apps = _scan_start_menu()
        for name, path in start_apps.items():
            if name not in apps or _is_unwanted_exe(apps.get(name, "")):
                apps[name] = path
        _add_auto_aliases(apps)
        apps = _clean_apps_dict(apps)

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(apps, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return apps


def resolve_target(target, known_keys):
    if not target:
        return None

    target_norm = normalize_name(target)
    if not target_norm:
        return None

    keys_list = [k for k in known_keys if k]
    keys_norm = [normalize_name(k) for k in keys_list]

    # 1. Exact match
    if target_norm in keys_norm:
        return keys_list[keys_norm.index(target_norm)]

    # 2. Substring match (both directions)
    for k_norm, k_orig in zip(keys_norm, keys_list):
        short = min(len(target_norm), len(k_norm))
        if short >= 4 and (target_norm in k_norm or k_norm in target_norm):
            return k_orig

    # 3. Acronym — "gta v" → "grand theft auto v"
    t_compact = target_norm.replace(" ", "")
    if 2 <= len(t_compact) <= 6:
        for k_norm, k_orig in zip(keys_norm, keys_list):
            words = k_norm.split()
            if len(words) >= 2 and "".join(w[0] for w in words) == t_compact:
                return k_orig

    # 4. Word-level match
    _stop = {"the", "of", "and", "a", "an", "to", "for", "in", "on", "my",
             "app", "game", "launcher", "client", "online"}
    target_words = {w for w in target_norm.split() if len(w) >= 4 and w not in _stop}
    for k_norm, k_orig in zip(keys_norm, keys_list):
        if target_words & {w for w in k_norm.split() if len(w) >= 4 and w not in _stop}:
            return k_orig

    # 5. Fuzzy match
    close = difflib.get_close_matches(target_norm, keys_norm, n=1, cutoff=0.78)
    if close:
        return keys_list[keys_norm.index(close[0])]

    return None