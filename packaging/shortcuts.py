# -*- coding: utf-8 -*-
"""Yobi's shortcuts, made and removed by the installed Python (install.ps1 / uninstall.ps1 call this).

PowerShell's usual way (WScript.Shell) fails on any path with letters outside the PC's ANSI code
page, e.g. an Arabic Windows user name on an English Windows. IShellLinkW takes any path.

    python shortcuts.py make   <install folder> <desktop folder> <start-menu folder>
    python shortcuts.py remove <install folder> <desktop folder> <start-menu folder>
"""
import os
import sys

import pythoncom
from win32com.shell import shell


def _link(load=None):
    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    if load:
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(load)
    return link


def make_link(path, target, arguments, workdir, icon, description):
    link = _link()
    link.SetPath(target)
    link.SetArguments(arguments)
    link.SetWorkingDirectory(workdir)
    link.SetIconLocation(icon, 0)
    link.SetDescription(description)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(path, 0)


def starts(path):
    """What a shortcut runs: 'target arguments'."""
    link = _link(path)
    return f"{link.GetPath(shell.SLGP_RAWPATH)[0]} {link.GetArguments()}"


def uninstall_arguments(dest):
    return f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{os.path.join(dest, "app", "uninstall.ps1")}"'


def make(dest, desktop, menu):
    app = os.path.join(dest, "app")
    pyw, icon = os.path.join(dest, "runtime", "pythonw.exe"), os.path.join(app, "yobi.ico")
    run = f'-s -E "{os.path.join(app, "launcher.pyw")}"'
    powershell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    os.makedirs(menu, exist_ok=True)
    make_link(os.path.join(desktop, "Yobi.lnk"), pyw, run, app, icon, "Yobi voice assistant")
    make_link(os.path.join(menu, "Yobi.lnk"), pyw, run, app, icon, "Yobi voice assistant")
    make_link(os.path.join(menu, "Yobi - API keys.lnk"), pyw, run + " --keys", app, icon, "Change the Gemini / Groq keys")
    make_link(os.path.join(menu, "Uninstall Yobi.lnk"), powershell, uninstall_arguments(dest), app, icon, "Remove Yobi")


def remove(dest, desktop, menu):
    """Only the shortcuts that start this install: another copy's shortcuts stay."""
    links = [os.path.join(desktop, "Yobi.lnk")]
    if os.path.isdir(menu):
        links += [os.path.join(menu, f) for f in os.listdir(menu) if f.lower().endswith(".lnk")]
    for path in links:
        try:
            if os.path.exists(path) and dest.lower() in starts(path).lower():
                os.remove(path)
        except Exception as e:                  # a broken shortcut: leave it
            print(f"skip {path}: {e}")
    if os.path.isdir(menu) and not os.listdir(menu):
        os.rmdir(menu)


if __name__ == "__main__":
    {"make": make, "remove": remove}[sys.argv[1]](*(a.rstrip("\\") for a in sys.argv[2:5]))
