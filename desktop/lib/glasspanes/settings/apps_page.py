"""Apps: Installed apps (uninstall), Default apps, Startup apps, Windows apps (Wine)."""
import configparser
import os
import re
import subprocess

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QMenu, QMessageBox, QPushButton

from .. import apps as appdb
from .. import style
from ..widgets import ComboBox, SettingRow, ToggleSwitch, label
from .util import Page, TaskDialog, control_panel, in_background, run, spawn

# Removing these would break the desktop itself.
PROTECTED = {"plasma-workspace", "plasma-desktop", "kwin-x11", "sddm", "systemsettings", "python3",
             "python3-pyqt6", "konsole", "dolphin", "plasma-discover", "network-manager", "pipewire",
             "calamares", "wine", "wine64", "libwine", "kde-cli-tools", "kinfocenter", "breeze"}
ESSENTIAL_PREFIXES = ("glass-", "org.kde.plasma", "kcm_", "calamares")


class AppsPage(Page):
    title = "Apps"

    def build(self):
        self.row("apps_list", "Installed apps", "Uninstall and manage apps", open_key="installedapps")
        self.row("window_apps", "Windows apps", "Install and run programs made for Windows",
                 open_key="windowsapps")
        self.row("apps", "Default apps", "Defaults for file and link types, other defaults",
                 open_key="defaultapps")
        self.row("rocket", "Startup", "Apps that start automatically when you sign in", open_key="startup")
        self.row("arrow_download", "Get more apps", "Browse the Store",
                 on_click=lambda: spawn("plasma-discover"))


def uninstall_plan(pkg):
    """Packages apt would remove with `pkg`, or None if apt refuses."""
    out = run("apt-get", "-s", "remove", pkg, timeout=60)
    removed = re.findall(r"^Remv (\S+)", out, re.M)
    return removed or None


class InstalledAppsPage(Page):
    title = "Installed apps"
    parent_key = "apps"

    def build(self):
        bar = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search apps")
        self.filter.setFixedWidth(300)
        self.filter.textChanged.connect(self.apply_filter)
        bar.addWidget(self.filter)
        bar.addStretch(1)
        self.body.addLayout(bar)
        self.count_label = label("", "secondary")
        self.body.addWidget(self.count_label)
        self.rows = []

    def refresh(self):
        for r in self.rows:
            r.deleteLater()
        self.rows = []
        self.count_label.setText("Loading…")
        in_background(self, self.collect, self.show)

    def collect(self):
        items = []
        for app in appdb.sorted_apps(appdb.all_apps()):
            if app.id.startswith(ESSENTIAL_PREFIXES) or app.is_wine:
                continue
            fp = appdb.flatpak_id(app)
            items.append(dict(name=app.name, icon=app.icon, kind="flatpak" if fp else "deb",
                              ident=fp or app.id, app=app))
        for guid, name in appdb.wine_uninstall_entries():
            items.append(dict(name=name, icon="wine", kind="wine", ident=guid, app=None))
        items.sort(key=lambda x: x["name"].lower())
        return items

    def show(self, items):
        if isinstance(items, Exception):
            self.count_label.setText("Couldn't list apps.")
            return
        self.count_label.setText(f"{len(items)} apps found")
        for it in items:
            more = QPushButton()
            more.setIcon(style.icon("more_horizontal", self.t.text, 16))
            more.setProperty("flat", "true")
            more.setFixedSize(36, 32)
            more.clicked.connect(lambda _=False, i=it, b=more: self.item_menu(i, b))
            desc = {"wine": "Windows app", "flatpak": "Store app (Flatpak)", "deb": "Glass Panes app"}[it["kind"]]
            r = SettingRow(self.t, style.app_icon(it["icon"], 24), it["name"], desc, more)
            r.setProperty("search", it["name"].lower())
            self.body.insertWidget(self.body.count() - 1, r)
            self.rows.append(r)
        self.apply_filter(self.filter.text())

    def apply_filter(self, text):
        q = text.lower().strip()
        for r in self.rows:
            r.setVisible(not q or q in r.property("search"))

    def item_menu(self, it, button):
        m = QMenu(self)
        if it["kind"] != "wine":
            m.addAction("Open", lambda: it["app"].launch())
        m.addAction("Uninstall", lambda: self.uninstall(it))
        m.exec(button.mapToGlobal(QPoint(0, button.height())))

    def uninstall_desktop_id(self, did):
        app = appdb.find(did)
        if not app:
            return
        fp = appdb.flatpak_id(app)
        self.uninstall(dict(name=app.name, icon=app.icon, kind="flatpak" if fp else ("wine" if app.is_wine else "deb"),
                            ident=fp or app.id, app=app))

    def uninstall(self, it):
        if QMessageBox.question(self, "Uninstall", f"This app and its related info will be uninstalled.\n\n"
                                f"Uninstall {it['name']}?") != QMessageBox.StandardButton.Yes:
            return
        if it["kind"] == "wine":
            if it["app"] is not None:  # a Windows shortcut from Start: use Wine's own uninstaller
                spawn("glass-wine", "--uninstaller")
                return
            TaskDialog(self, f"Uninstalling {it['name']}", ["wine", "uninstaller", "--remove", it["ident"]]).exec()
        elif it["kind"] == "flatpak":
            TaskDialog(self, f"Uninstalling {it['name']}", ["flatpak", "uninstall", "-y", "--noninteractive",
                                                            it["ident"]]).exec()
        else:
            pkg = appdb.owning_package(it["app"])
            if not pkg:
                QMessageBox.information(self, "Uninstall", f"{it['name']} can't be uninstalled here.")
                return
            plan = uninstall_plan(pkg)
            if not plan or set(plan) & PROTECTED or len(plan) > 8:
                QMessageBox.warning(self, "Uninstall",
                                    f"{it['name']} is part of Glass Panes and can't be uninstalled.")
                return
            TaskDialog(self, f"Uninstalling {it['name']}",
                       ["pkexec", "apt-get", "remove", "-y", *plan]).exec()
        self.refresh()


DEFAULT_TYPES = [
    ("Web browser", "globe", ["x-scheme-handler/http", "x-scheme-handler/https", "text/html"]),
    ("Email", "mail", ["x-scheme-handler/mailto"]),
    ("Music player", "music_note_2", ["audio/mpeg", "audio/flac", "audio/ogg", "audio/x-wav"]),
    ("Video player", "video", ["video/mp4", "video/x-matroska", "video/webm", "video/x-msvideo"]),
    ("Photo viewer", "image", ["image/jpeg", "image/png", "image/gif", "image/webp"]),
    ("PDF reader", "document", ["application/pdf"]),
    ("Text editor", "edit", ["text/plain"]),
    ("Windows programs", "window_apps", ["application/x-ms-dos-executable", "application/x-msi"]),
]


def apps_for_mime(mime):
    out = []
    for app in appdb.all_apps(include_hidden=True).values():
        try:
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.read(app.path, encoding="utf-8")
            types = cp.get("Desktop Entry", "MimeType", fallback="")
        except configparser.Error:
            continue
        if mime in types.split(";"):
            out.append(app)
    return sorted(out, key=lambda a: a.name.lower())


class DefaultAppsPage(Page):
    title = "Default apps"
    parent_key = "apps"

    def build(self):
        self.note("Choose the apps Glass Panes uses to open files and links.")
        for title, icon, mimes in DEFAULT_TYPES:
            choices = apps_for_mime(mimes[0])
            if not choices:
                continue
            current = run("xdg-mime", "query", "default", mimes[0], timeout=5).strip()
            self.combo(icon, title, "", [(a.name, a.id) for a in choices], current,
                       lambda did, ms=mimes: subprocess.run(["xdg-mime", "default", did, *ms]))
        self.section("Related settings")
        self.row("options", "Choose defaults by file type", "",
                 on_click=lambda: control_panel("kcm_filetypes"))


class StartupPage(Page):
    title = "Startup"
    parent_key = "apps"
    HIDDEN = ("glass-", "org.kde.", "polkit", "xdg-user-dirs", "at-spi", "pipewire", "geoclue",
              "kde", "baloo", "plasma", "powerdevil", "gmenudbusmenuproxy", "spice", "print-applet",
              "calamares", "klipper", "xembed")

    def build(self):
        self.note("Apps can be configured to start when you sign in. In most cases, they'll start "
                  "minimised or might only start a background task.")
        user_dir = os.path.expanduser("~/.config/autostart")
        entries = {}
        for d in ("/etc/xdg/autostart", user_dir):
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".desktop"):
                        entries[f] = os.path.join(d, f)
        shown = 0
        for fid, path in sorted(entries.items()):
            if fid.startswith(self.HIDDEN):
                continue
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            try:
                cp.read(path, encoding="utf-8")
                name = cp.get("Desktop Entry", "Name", fallback=fid)
                hidden = cp.get("Desktop Entry", "Hidden", fallback="false").lower() == "true"
                icon = cp.get("Desktop Entry", "Icon", fallback="")
            except configparser.Error:
                continue
            sw = ToggleSwitch(self.t, not hidden)
            sw.toggled.connect(lambda on, f=fid, p=path: self.set_enabled(f, p, on))
            self.add(SettingRow(self.t, style.app_icon(icon, 24), name, "", sw))
            shown += 1
        if not shown:
            self.note("No startup apps yet.")

    def set_enabled(self, fid, path, on):
        user = os.path.expanduser(f"~/.config/autostart/{fid}")
        os.makedirs(os.path.dirname(user), exist_ok=True)
        cp = configparser.RawConfigParser(strict=False, interpolation=None)
        cp.optionxform = str
        cp.read(path if not os.path.exists(user) else user, encoding="utf-8")
        if not cp.has_section("Desktop Entry"):
            cp.add_section("Desktop Entry")
        cp.set("Desktop Entry", "Hidden", "false" if on else "true")
        with open(user, "w") as f:
            cp.write(f, space_around_delimiters=False)


class WindowsAppsPage(Page):
    title = "Windows apps"
    parent_key = "apps"

    def build(self):
        from .. import wine
        c, lay = self.card()
        ready = wine.prefix_ready()
        lay.addWidget(label("Windows app support", "subtitle"))
        self.status = label("Ready — double-click any .exe or .msi file to install or run it."
                            if ready else "Not set up yet. It's set up automatically the first time you "
                            "open a Windows program, or you can do it now.", "secondary", wrap=True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addWidget(self.button("Install a Windows app…", self.install, accent=True))
        if not ready:
            row.addWidget(self.button("Set up now", lambda: (spawn("glass-wine", "--prepare"))))
        row.addStretch(1)
        lay.addLayout(row)
        self.section("Manage")
        self.row("folder", "Open the C: drive", "Program Files, Windows folders and app data",
                 on_click=lambda: spawn("glass-wine", "--drive"))
        self.row("apps_list", "Uninstall Windows apps", "Programs you installed from .exe or .msi files",
                 on_click=lambda: spawn("glass-wine", "--uninstaller"))
        self.row("options", "Windows compatibility settings", "Windows version, graphics, drives, audio",
                 on_click=lambda: spawn("glass-wine", "--config"))
        self.row("apps_add_in", "Install extra Windows components", "Visual C++ runtimes, .NET, DirectX, fonts",
                 on_click=lambda: spawn("winetricks", "--gui"))
        self.note("Windows apps run through Wine. Most everyday programs and many games work; some "
                  "anti-cheat games and apps that need special drivers don't.")

    def install(self):
        path, _ = QFileDialog.getOpenFileName(self, "Install a Windows app", os.path.expanduser("~/Downloads"),
                                              "Windows programs (*.exe *.msi);;All files (*)")
        if path:
            spawn("glass-wine", path)


PAGES = {"apps": AppsPage, "installedapps": InstalledAppsPage, "defaultapps": DefaultAppsPage,
         "startup": StartupPage, "windowsapps": WindowsAppsPage}
