# -*- coding: utf-8 -*-
"""
Launcher Discovery — يلاقي ألعاب Battle.net / GOG / Ubisoft / EA / itch.io.

كل launcher بيخزن ألعابه في مكان مختلف (registry أو فولدر)، فبنقرا كل
واحد من مصدره مباشرة — بدون ما نعمل crawl للقرص.
"""

import os
import platform
import winreg

CURRENT_OS = platform.system().lower()


def _read_registry_subkeys(root, path):
    try:
        with winreg.OpenKey(root, path) as key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        values = {}
                        j = 0
                        while True:
                            try:
                                name, val, _ = winreg.EnumValue(subkey, j)
                                values[name] = val
                                j += 1
                            except OSError:
                                break
                        yield subkey_name, values
                except OSError:
                    continue
    except OSError:
        return


def scan_battlenet_games():
    """Battle.net stores games under HKLM\\SOFTWARE\\WOW6432Node\\Blizzard Entertainment\\*"""
    games = {}
    path = r"SOFTWARE\WOW6432Node\Blizzard Entertainment"
    for subkey, values in _read_registry_subkeys(winreg.HKEY_LOCAL_MACHINE, path):
        loc = values.get("InstallLocation")
        if loc and os.path.isdir(loc):
            try:
                for f in os.listdir(loc):
                    if f.lower().endswith(".exe") and "launcher" not in f.lower():
                        games[subkey.lower()] = os.path.join(loc, f)
                        break
            except OSError:
                pass
    return games


def scan_gog_games():
    """GOG games in HKLM\\SOFTWARE\\WOW6432Node\\GOG.com\\Games\\<id>"""
    games = {}
    path = r"SOFTWARE\WOW6432Node\GOG.com\Games"
    for subkey, values in _read_registry_subkeys(winreg.HKEY_LOCAL_MACHINE, path):
        name = values.get("gameName")
        p = values.get("path")
        exe = values.get("exe")
        if name and p and exe:
            full = os.path.join(p, exe)
            if os.path.exists(full):
                games[name.lower()] = full
    return games


def scan_ubisoft_games():
    """Ubisoft Connect: HKLM\\SOFTWARE\\WOW6432Node\\Ubisoft\\Launcher\\Installs\\<id>"""
    games = {}
    path = r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"
    for subkey, values in _read_registry_subkeys(winreg.HKEY_LOCAL_MACHINE, path):
        loc = values.get("InstallDir")
        if loc and os.path.isdir(loc):
            try:
                for f in os.listdir(loc):
                    if f.lower().endswith(".exe") and "uplay" not in f.lower():
                        games[subkey.lower()] = os.path.join(loc, f)
                        break
            except OSError:
                pass
    return games


def scan_ea_games():
    """EA/Origin: HKLM\\SOFTWARE\\WOW6432Node\\EA Games\\* and Origin Games\\*"""
    games = {}
    for reg_path in (
        r"SOFTWARE\WOW6432Node\EA Games",
        r"SOFTWARE\WOW6432Node\Electronic Arts\EA Games",
        r"SOFTWARE\WOW6432Node\Origin Games",
    ):
        for subkey, values in _read_registry_subkeys(winreg.HKEY_LOCAL_MACHINE, reg_path):
            loc = (values.get("Install Dir")
                   or values.get("InstallDir")
                   or values.get("InstallLocation"))
            if loc and os.path.isdir(loc):
                try:
                    for f in os.listdir(loc):
                        if f.lower().endswith(".exe"):
                            games[subkey.lower()] = os.path.join(loc, f)
                            break
                except OSError:
                    pass
    return games


def scan_itch_games():
    """itch.io: %APPDATA%\\itch\\apps\\<game>\\<game>.exe"""
    games = {}
    appdata = os.environ.get("APPDATA", "")
    itch_dir = os.path.join(appdata, "itch", "apps")
    if not os.path.isdir(itch_dir):
        return games
    try:
        for entry in os.listdir(itch_dir):
            full = os.path.join(itch_dir, entry)
            if not os.path.isdir(full):
                continue
            for f in os.listdir(full):
                if f.lower().endswith(".exe"):
                    games[entry.lower()] = os.path.join(full, f)
                    break
    except OSError:
        pass
    return games


def scan_all_other_launchers():
    games = {}
    for fn in (scan_battlenet_games, scan_gog_games,
               scan_ubisoft_games, scan_ea_games, scan_itch_games):
        try:
            games.update(fn())
        except Exception:
            pass
    return games