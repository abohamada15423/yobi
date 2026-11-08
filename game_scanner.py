# -*- coding: utf-8 -*-
"""
Finds installed games without crawling the whole disk.

Steam and Epic both keep their own manifest files listing every game
they've installed and where — reading those directly is instant and
100% accurate, versus walking every file on every drive.
"""

import glob
import json
import os
import platform
import re

from aliases import ARABIC_TO_CANONICAL, normalize_name

_IGNORE_SHORTCUT_WORDS = (
    "adventure guide", "artbook", "soundtrack", " ost", "manual",
    "uninstall", "server", "editor", "sdk", "tools", "redistribution",
)

_IGNORE_EXE_WORDS = (
    "uninstall", "unins000", "crash", "report", "setup", "update",
    "helper", "dxsetup", "vcredist", "unitycrashhandler", " launcher",
)


def _get_steam_install_path():
    if platform.system().lower() != "windows":
        return None
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        return path
    except OSError:
        pass
    default = r"C:\Program Files (x86)\Steam"
    return default if os.path.isdir(default) else None


def _parse_vdf_library_paths(vdf_path):
    if not os.path.exists(vdf_path):
        return []
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return []
    return [m.group(1).replace("\\\\", "\\") for m in re.finditer(r'"path"\s+"([^"]+)"', content)]


def scan_steam_games():
    """Returns {game_name_lower: 'steam://rungameid/<appid>'}."""
    games = {}
    steam_path = _get_steam_install_path()
    if not steam_path:
        return games

    steamapps = os.path.join(steam_path, "steamapps")
    extra_libraries = [os.path.join(p, "steamapps") for p in _parse_vdf_library_paths(os.path.join(steamapps, "libraryfolders.vdf"))]

    for lib in [steamapps] + extra_libraries:
        if not os.path.isdir(lib):
            continue
        for acf_path in glob.glob(os.path.join(lib, "appmanifest_*.acf")):
            try:
                with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                name_match = re.search(r'"name"\s+"([^"]+)"', content)
                appid_match = re.search(r'"appid"\s+"([^"]+)"', content)
                if name_match and appid_match:
                    name = name_match.group(1).strip().lower()
                    if "steamworks common" in name:
                        continue
                    games[name] = f"steam://rungameid/{appid_match.group(1).strip()}"
            except OSError:
                continue
    return games


def scan_epic_games():
    """Returns {game_name_lower: 'com.epicgames.launcher://apps/<AppName>?action=launch&silent=true'}."""
    games = {}
    manifests_dir = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    if not os.path.isdir(manifests_dir):
        return games

    for item_path in glob.glob(os.path.join(manifests_dir, "*.item")):
        try:
            with open(item_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            name = (data.get("DisplayName") or "").strip().lower()
            app_name = data.get("AppName") or data.get("MainGameAppName")
            if name and app_name:
                games[name] = f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true"
        except (OSError, json.JSONDecodeError):
            continue
    return games


def _get_riot_installs_info():
    installs_path = r"C:\ProgramData\Riot Games\RiotClientInstalls.json"
    if not os.path.exists(installs_path):
        return None
    try:
        with open(installs_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


KNOWN_RIOT_PRODUCTS = {
    "league_of_legends": "league of legends",
    "valorant": "valorant",
    "bacon": "legends of runeterra",
}


def scan_riot_games():
    games = {}
    installs = _get_riot_installs_info()
    if not installs:
        return games

    riot_client_exe = installs.get("rc_live") or installs.get("rc_default")
    if not riot_client_exe or not os.path.exists(riot_client_exe):
        return games

    metadata_dir = r"C:\ProgramData\Riot Games\Metadata"
    for product_id, display_name in KNOWN_RIOT_PRODUCTS.items():
        product_dir = os.path.join(metadata_dir, f"{product_id}.live")
        if os.path.isdir(product_dir):
            games[display_name] = [
                riot_client_exe,
                f"--launch-product={product_id}",
                "--launch-patchline=live",
            ]
    return games


def scan_desktop_and_standalone_games():
    """Detect games from desktop shortcuts and common standalone folders."""
    games = {}
    user_prof = os.environ.get("USERPROFILE", "")
    public_prof = os.environ.get("PUBLIC", r"C:\Users\Public")
    desktops = [
        os.path.join(user_prof, "Desktop"),
        os.path.join(user_prof, "OneDrive", "Desktop"),
        os.path.join(public_prof, "Desktop"),
    ]

    KNOWN_GAME_KEYWORDS = {
        "euro truck simulator 2", "euro truck", "forza horizon 6", "forza horizon",
        "sekiro", "alan wake 2", "alan wake", "f1 24", "f1 25", "the last of us",
        "elden ring", "overwatch", "minecraft", "tlauncher", "celeste",
        "assetto corsa competizione", "assetto corsa", "gta", "grand theft auto",
        "cyberpunk", "fifa", "ea fc", "witcher", "red dead", "god of war",
        "resident evil", "battlefield", "call of duty", "pubg", "apex",
        "fortnite", "rocket league", "roblox", "dota", "cs2", "counter-strike",
        "outlast", "among us", "fall guys", "teamfight tactics", "arc raiders",
    }

    for d in desktops:
        if not os.path.isdir(d):
            continue
        try:
            for fname in os.listdir(d):
                if fname.lower().endswith((".lnk", ".url")):
                    clean = re.sub(r"\.(lnk|url)$", "", fname, flags=re.I).lower().replace(" - shortcut", "").strip()
                    if any(bad in clean for bad in _IGNORE_SHORTCUT_WORDS):
                        continue
                    for kw in sorted(KNOWN_GAME_KEYWORDS, key=len, reverse=True):
                        if kw in clean:
                            canonical = kw if kw != "tlauncher" else "minecraft"
                            full_p = os.path.join(d, fname)
                            if canonical not in games:
                                games[canonical] = full_p
                            if clean != canonical and clean not in games:
                                games[clean] = full_p
                            break
        except Exception:
            continue

    # Standalone game root folders on common drives
    for drive in ["C", "D", "E", "F", "G"]:
        root = f"{drive}:\\"
        if not os.path.isdir(root):
            continue
        try:
            for folder in ["ELDEN RING", "Games", "Overwatch", "Euro Truck Simulator 2", "Forza Horizon 6"]:
                fpath = os.path.join(root, folder)
                if os.path.isdir(fpath):
                    fl = folder.lower()
                    if fl == "elden ring":
                        exe = os.path.join(fpath, "Game", "eldenring.exe")
                        if os.path.exists(exe):
                            games["elden ring"] = exe
                    elif fl == "euro truck simulator 2":
                        for arch in ("win_x64", "win_x86"):
                            exe = os.path.join(fpath, "bin", arch, "eurotrucks2.exe")
                            if os.path.exists(exe):
                                games["euro truck simulator 2"] = exe
                                break
        except Exception:
            continue

    return games


def scan_all_games():
    """Scan every launcher + desktop and return a normalized dict."""
    raw = {}
    raw.update(scan_steam_games())
    raw.update(scan_epic_games())
    raw.update(scan_riot_games())
    raw.update(scan_desktop_and_standalone_games())

    games = {}
    for k, v in raw.items():
        nk = normalize_name(k)
        if nk and not any(bad in nk for bad in _IGNORE_SHORTCUT_WORDS) and nk not in games:
            games[nk] = v

    for alias, canonical in ARABIC_TO_CANONICAL.items():
        canon_norm = normalize_name(canonical)
        alias_norm = normalize_name(alias)
        if canon_norm in games and alias_norm not in games:
            games[alias_norm] = games[canon_norm]

    return games


COMMON_GAME_DIRS = [
    r"C:\Program Files (x86)\Steam\steamapps\common",
    r"C:\Program Files\Epic Games",
]
for _drive in "cdefgh":
    COMMON_GAME_DIRS += [
        rf"{_drive}:\Games",
        rf"{_drive}:\SteamLibrary\steamapps\common",
        rf"{_drive}:\Epic Games",
    ]


def bounded_game_search(name, max_depth=3):
    """Search common game directories up to depth 3 (covers bin/win_x64/game.exe)."""
    name_clean = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if len(name_clean) < 3:
        return None
    words = [w for w in re.split(r"\W+", (name or "").lower()) if len(w) >= 3 and w not in ("simulator", "edition", "game", "the", "part")]
    acronym = "".join(w[0] for w in re.split(r"\W+", (name or "").lower()) if w)

    for base in COMMON_GAME_DIRS:
        if not os.path.isdir(base):
            continue
        base_depth = base.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(base):
            depth = root.rstrip(os.sep).count(os.sep) - base_depth
            if depth >= max_depth:
                dirs[:] = []
                continue
            folder_clean = re.sub(r"[^a-z0-9]", "", os.path.basename(root).lower())
            folder_hit = (name_clean in folder_clean) or (words and all(w in folder_clean for w in words[:2]))
            for fname in files:
                if not fname.lower().endswith(".exe"):
                    continue
                fl = fname.lower()
                if any(bad in fl for bad in _IGNORE_EXE_WORDS):
                    continue
                stem = re.sub(r"[^a-z0-9]", "", os.path.splitext(fl)[0])
                if not stem:
                    continue
                if name_clean in stem or stem in name_clean:
                    return os.path.join(root, fname)
                if len(acronym) >= 3 and stem.startswith(acronym):
                    return os.path.join(root, fname)
                if folder_hit and words and any(w in stem for w in words):
                    return os.path.join(root, fname)
    return None