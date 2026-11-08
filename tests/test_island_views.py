# -*- coding: utf-8 -*-
"""Renders every island view off-screen and checks the layout: python tests/test_island_views.py

Needs the Electron runtime (see electron_island.find_electron). Pictures land in
tests/island_views/out/ so you can look at them.
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from electron_island import find_electron  # noqa: E402


@unittest.skipIf(find_electron() is None, "Electron runtime not installed")
class TestIslandViews(unittest.TestCase):
    def test_every_view_fits_and_has_no_errors(self):
        env = dict(os.environ)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        r = subprocess.run([find_electron(), os.path.join(HERE, "island_views")], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=180, env=env)
        out = r.stdout + r.stderr
        self.assertIn("ALL OK", out, out[-3000:])
        self.assertEqual(r.returncode, 0, out[-3000:])


if __name__ == "__main__":
    unittest.main()
