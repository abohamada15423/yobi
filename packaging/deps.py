# -*- coding: utf-8 -*-
"""Which installed distributions Yobi needs: requirements.txt + whatever the app's
own .py files import, plus everything those depend on.

    python packaging/deps.py            → prints the list and sizes
"""
import ast
import os
import re
import sys
from importlib import metadata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# never shipped: dev/test tools, and things only the old UIs or experiments use
SKIP = {"pip", "wheel", "pytest", "pyinstaller", "black", "mypy", "ipython", "jupyter"}


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names():
    out = []
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(norm(re.split(r"[<>=!~;\[ ]", line, 1)[0]))
    return out


def imported_top_modules(files):
    mods = set()
    for p in files:
        try:
            tree = ast.parse(open(p, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods.update(a.name.split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                mods.add(n.module.split(".")[0])
    return mods


def closure(names):
    dists = {norm(d.metadata["Name"]): d for d in metadata.distributions()}
    todo, seen = list(names), {}
    while todo:
        n = norm(todo.pop())
        if n in seen or n in SKIP or n not in dists:
            continue
        d = dists[n]
        seen[n] = d
        for req in d.requires or []:
            if "extra ==" in req:
                continue
            m = req.split(";", 1)
            if len(m) > 1 and "sys_platform" in m[1] and "win32" not in m[1] and "!=" not in m[1]:
                continue
            todo.append(re.split(r"[<>=!~;\[ (]", m[0].strip(), 1)[0])
    return seen


def needed(app_files):
    by_module = metadata.packages_distributions()
    names = requirement_names()
    names.append("setuptools")         # GPUtil imports distutils, gone from Python 3.12 (setuptools brings it back)
    missing = [n for n in names if n not in {norm(d.metadata["Name"]) for d in metadata.distributions()}]
    for m in imported_top_modules(app_files):
        for d in by_module.get(m, []):
            names.append(norm(d))
    return closure(names), missing


def size(d):
    total = 0
    for f in d.files or []:
        p = d.locate_file(f)
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return total


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    from manifest import app_files
    ds, missing = needed([os.path.join(ROOT, f) for f in app_files() if f.endswith(".py")])
    rows = sorted(((size(d), n) for n, d in ds.items()), reverse=True)
    for s, n in rows:
        print(f"{s / 2**20:8.1f} MB  {n}")
    print(f"{sum(s for s, _ in rows) / 2**20:8.1f} MB  total, {len(rows)} packages")
    if missing:
        print("not installed (skipped):", ", ".join(missing))
