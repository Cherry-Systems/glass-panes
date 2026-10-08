"""Unit tests for the parts of the Glass Panes desktop that don't need a screen: make test"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop", "lib"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from glasspanes import appearance, apps, rundialog, settings_index, wine  # noqa: E402
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

    def test_desktop_lnk_twins_removed(self):
        with tempfile.TemporaryDirectory() as d:
            for fn in ("App.lnk", "App.desktop", "Lone.lnk", "Old.lnk", "Old.desktop"):
                open(os.path.join(d, fn), "w").close()
            os.utime(os.path.join(d, "Old.lnk"), (1, 1))
            wine.remove_lnk_twins(d, os.path.getmtime(os.path.join(d, "App.lnk")))
            self.assertEqual(sorted(os.listdir(d)), ["App.desktop", "Lone.lnk", "Old.desktop", "Old.lnk"])

    def test_dead_shortcuts(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "drive_c", "Program Files", "App"))
            open(os.path.join(d, "drive_c", "Program Files", "App", "app.exe"), "w").close()
            os.makedirs(os.path.join(d, "dosdevices"))
            os.symlink("../drive_c", os.path.join(d, "dosdevices", "c:"))
            old, wine.PREFIX = wine.PREFIX, d
            try:
                run = ["env", "WINEPREFIX=" + d, "wine"]
                self.assertFalse(wine.shortcut_is_dead(run + ["C:\\PROGRAM FILES\\app\\APP.EXE"]))
                self.assertTrue(wine.shortcut_is_dead(run + ["C:\\Program Files\\Gone\\gone.exe"]))
                self.assertFalse(wine.shortcut_is_dead(run + ["E:\\stick\\tool.exe"]))
                self.assertFalse(wine.shortcut_is_dead(["dolphin", "C:\\Program Files\\Gone\\gone.exe"]))
            finally:
                wine.PREFIX = old


class TaskbarTest(unittest.TestCase):
    S, T, TRAY, CLOCK = ("org.kde.plasma.panelspacer", "org.kde.plasma.icontasks",
                         "org.kde.plasma.systemtray", "org.kde.plasma.digitalclock")

    def test_intact_layout(self):
        w = [[3, self.S], [4, self.T], [5, self.S], [6, self.TRAY], [17, self.CLOCK]]
        self.assertEqual(appearance.taskbar_plan(w), 3)

    def test_damaged_layout(self):
        # Left, Center, Left with the old code: tray and clock pushed up against the apps.
        w = [[4, self.T], [6, self.TRAY], [17, self.CLOCK], [21, self.S], [22, self.S]]
        self.assertIsNone(appearance.taskbar_plan(w))
        self.assertEqual(appearance.taskbar_repair_order(w), ([21, 4, 22, 6, 17], []))

    def test_extra_spacers_removed(self):
        w = [[4, self.T], [5, self.S], [6, self.TRAY], [7, self.S], [8, self.S]]
        self.assertEqual(appearance.taskbar_repair_order(w), ([5, 4, 7, 6], [8]))


class LastCheckedTest(unittest.TestCase):
    def test_days_by_calendar_not_hours(self):
        from glasspanes.settings.update import checked_text
        import time
        now = time.mktime((2026, 10, 6, 8, 49, 0, 0, 0, -1))
        evening = time.mktime((2026, 10, 5, 20, 21, 0, 0, 0, -1))
        self.assertEqual(checked_text(now - 600, now), "Last checked: today, 8:39 AM")
        self.assertEqual(checked_text(evening, now), "Last checked: yesterday, 8:21 PM")
        older = time.mktime((2026, 10, 3, 20, 21, 0, 0, 0, -1))
        self.assertEqual(checked_text(older, now), "Last checked: 3 October, 8:21 PM")


class WallpaperListTest(unittest.TestCase):
    def test_one_picture_per_kde_package(self):
        from glasspanes.settings import personal
        sizes = ["1024x768", "1080x1920", "1920x1080", "2560x1440", "440x247", "7680x2160"]
        with tempfile.TemporaryDirectory() as d:
            for sub in ("images", "images_dark", "screenshot"):
                os.makedirs(os.path.join(d, "Next", "contents", sub))
                for s in sizes:
                    open(os.path.join(d, "Next", "contents", sub, s + ".png"), "w").close()
            open(os.path.join(d, "glass.jpg"), "w").close()
            old, personal.paths.WALLPAPERS = personal.paths.WALLPAPERS, d
            try:
                found = [os.path.relpath(p, d) for p in personal.list_wallpapers() if p.startswith(d)]
            finally:
                personal.paths.WALLPAPERS = old
        self.assertEqual(found, ["glass.jpg", "Next/contents/images/1920x1080.png",
                                 "Next/contents/images_dark/1920x1080.png"])


class PatchQmlTest(unittest.TestCase):
    """Every Plasma QML patch still applies to the stock files of the last build."""
    ROOT = os.path.join(os.path.dirname(__file__), "..")
    PLASMOIDS = os.path.join(ROOT, "build/rootfs/usr/share/plasma/plasmoids")
    PARTS = {"taskmanager-menu": "org.kde.plasma.taskmanager/contents/ui/ContextMenu.qml",
             "folderview": "org.kde.desktopcontainment/contents/ui/FolderView.qml",
             "folderitem": "org.kde.desktopcontainment/contents/ui/FolderItemDelegate.qml",
             "trayitem": "org.kde.plasma.private.systemtray/contents/ui/items/PlasmoidItem.qml",
             "panel": "org.kde.panel/contents/ui/main.qml"}

    def test_parts_apply(self):
        import subprocess
        if not os.path.isdir(self.PLASMOIDS):
            self.skipTest("no build/rootfs")
        script = os.path.join(self.ROOT, "overlay/usr/share/glasspanes/plasma/patch-qml.py")
        for part, rel in self.PARTS.items():
            stock = os.path.join(self.PLASMOIDS, rel)
            if os.path.exists(stock + ".plasma"):
                stock += ".plasma"
            with tempfile.NamedTemporaryFile(suffix=".qml") as out:
                r = subprocess.run([sys.executable, script, part, stock, out.name], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, f"{part}: {r.stderr}")
                self.assertNotEqual(open(out.name).read(), open(stock).read(), part)


class TranslationTest(unittest.TestCase):
    """The MB/GB catalogues compile to .qm files that Qt reads."""
    ROOT = os.path.join(os.path.dirname(__file__), "..")
    DIR = os.path.join(ROOT, "overlay/usr/share/glasspanes/translations")

    def compile(self, ts, *extra):
        import subprocess
        from PyQt6.QtCore import QCoreApplication, QTranslator
        self.app = QCoreApplication.instance() or QCoreApplication([])
        with tempfile.NamedTemporaryFile(suffix=".qm") as out:
            subprocess.run([sys.executable, os.path.join(self.DIR, "ts2qm.py"), os.path.join(self.DIR, ts),
                            out.name, *extra], check=True)
            t = QTranslator()
            self.assertTrue(t.load(out.name))
            return t

    def test_kcoreaddons_merge(self):
        base = os.path.join(self.ROOT, "build/rootfs/usr/share/locale/en/LC_MESSAGES/kcoreaddons6_qt.qm")
        if os.path.exists(base + ".debian"):
            base += ".debian"
        if not os.path.exists(base):
            self.skipTest("no build/rootfs")
        t = self.compile("kcoreaddons6_qt.ts", "--base", base)
        self.assertEqual(t.translate("KFormat", "%1 GiB", "IECBinaryDialect"), "%1 GB")
        self.assertEqual(t.translate("KFormat", "Ki", "IEC binary prefix for 2^10"), "K")
        self.assertEqual(t.translate("KFormat", "%n day(s)", "", 1), "%n day")
        self.assertEqual(t.translate("KFormat", "%n day(s)", "", 2), "%n days")

    def test_installer(self):
        t = self.compile("calamares_en.ts")
        self.assertEqual(t.translate("CreatePartitionJob", "Create new %1MiB partition on %3 (%2)", "@title"),
                         "Create new %1MB partition on %3 (%2)")
        self.assertEqual(t.translate("CreatePartitionDialog", " MiB"), " MB")
        checker = "Calamares::RequirementsChecker"
        self.assertEqual(t.translate(checker, "(%n second(s))", "@status", 1), "(%n second)")
        self.assertEqual(t.translate(checker, "(%n second(s))", "@status", 3), "(%n seconds)")


if __name__ == "__main__":
    unittest.main()
