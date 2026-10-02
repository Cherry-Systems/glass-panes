"""Unit tests for the parts of the Glass Panes desktop that don't need a screen: make test"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop", "lib"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from glasspanes import apps, rundialog, settings_index, wine  # noqa: E402
from glasspanes.start import calculate  # noqa: E402


class RunDialogTest(unittest.TestCase):
    def test_windows_commands(self):
        self.assertEqual(rundialog.resolve("notepad"), ("argv", ["kwrite"]))
        self.assertEqual(rundialog.resolve("CMD.exe")[0], "argv")
        self.assertEqual(rundialog.resolve("appwiz.cpl"), ("argv", ["glass-settings", "--page", "installedapps"]))

    def test_ms_settings_links(self):
        self.assertEqual(rundialog.resolve("ms-settings:windowsupdate"),
                         ("argv", ["glass-settings", "--page", "update"]))
        self.assertEqual(rundialog.resolve("ms-settings:"), ("argv", ["glass-settings", "--page", "system"]))

    def test_urls_open_in_browser(self):
        self.assertEqual(rundialog.resolve("www.example.com"), ("open", "https://www.example.com"))

    def test_c_drive_maps_to_wine(self):
        self.assertEqual(rundialog.expand("C:\\Program Files"),
                         os.path.join(os.path.expanduser("~/.wine/drive_c"), "Program Files"))

    def test_unknown_command(self):
        self.assertEqual(rundialog.resolve("definitely-not-a-program-xyz")[0], "error")


class CalculatorTest(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(calculate("12*3+4"), "40")
        self.assertEqual(calculate("2^10"), "1,024")

    def test_not_arithmetic(self):
        self.assertIsNone(calculate("notepad"))
        self.assertIsNone(calculate("__import__('os')"))


class DesktopFileTest(unittest.TestCase):
    def test_field_codes(self):
        self.assertEqual(apps.exec_to_argv("kwrite %U", ["/tmp/a b.txt"]), ["kwrite", "/tmp/a b.txt"])
        self.assertEqual(apps.exec_to_argv("app %i --x", icon="ic"), ["app", "--icon", "ic", "--x"])
        self.assertEqual(apps.exec_to_argv('sh -c "echo 100%%"'), ["sh", "-c", "echo 100%"])

    def test_parse_and_hide(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.desktop")
            with open(p, "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Thing\nExec=thing\nOnlyShowIn=GNOME;\n")
            app = apps.parse(p)
            self.assertEqual(app.name, "Thing")
            self.assertTrue(app.no_display)


class SettingsSearchTest(unittest.TestCase):
    def test_finds_by_title_and_keyword(self):
        self.assertEqual(settings_index.search("display")[0][1], "display")
        self.assertIn("installedapps", [h[1] for h in settings_index.search("uninstall")])
        self.assertIn("update", [h[1] for h in settings_index.search("windows update")])

    def test_every_entry_has_a_page(self):
        from glasspanes.settings.app import page_classes
        pages = page_classes()
        for title, page, _icon, _kw in settings_index.ENTRIES:
            self.assertIn(page, pages, title)
        for page in rundialog.MS_SETTINGS.values():
            self.assertIn(page, pages, page)


class WineTest(unittest.TestCase):
    def test_installers_use_the_right_tool(self):
        self.assertEqual(wine.command_for("/d/Setup.MSI", []), ["wine", "msiexec", "/i", "/d/Setup.MSI"])
        self.assertEqual(wine.command_for("/d/run.bat", ["x"]), ["wine", "cmd", "/c", "/d/run.bat", "x"])
        self.assertEqual(wine.command_for("/d/app.exe", []), ["wine", "/d/app.exe"])


if __name__ == "__main__":
    unittest.main()
