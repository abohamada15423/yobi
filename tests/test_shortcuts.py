# -*- coding: utf-8 -*-
"""packaging/shortcuts.py: shortcuts in a folder with Arabic letters and a space (a friend's Windows user name)."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packaging"))
try:
    import shortcuts
except ImportError:                                    # no pywin32 on this Python
    shortcuts = None


@unittest.skipUnless(shortcuts, "needs pywin32")
class Shortcuts(unittest.TestCase):
    def test_make_then_remove_only_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            user = os.path.join(tmp, "محمد علي")
            dest, desk, menu = os.path.join(user, "Yobi"), os.path.join(user, "سطح المكتب"), os.path.join(user, "Menu")
            os.makedirs(desk)
            shortcuts.make(dest, desk, menu)
            self.assertEqual(sorted(os.listdir(menu)), ["Uninstall Yobi.lnk", "Yobi - API keys.lnk", "Yobi.lnk"])
            started = shortcuts.starts(os.path.join(desk, "Yobi.lnk"))
            self.assertIn(os.path.join(dest, "runtime", "pythonw.exe"), started)
            self.assertIn(f'"{os.path.join(dest, "app", "launcher.pyw")}"', started)
            self.assertIn(os.path.join(dest, "app", "uninstall.ps1"), shortcuts.starts(os.path.join(menu, "Uninstall Yobi.lnk")))
            other = os.path.join(menu, "Other.lnk")       # another copy's shortcut stays
            shortcuts.make_link(other, sys.executable, "", tmp, sys.executable, "other")
            shortcuts.remove(dest, desk, menu)
            self.assertEqual(os.listdir(desk), [])
            self.assertEqual(os.listdir(menu), ["Other.lnk"])


if __name__ == "__main__":
    unittest.main()
