"""System: Display, Sound, Notifications, Power & battery, Storage, Multitasking, About."""
import json
import os
import platform
import re
import shutil
import socket
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QGuiApplication, QPixmap
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QProgressBar,
                             QPushButton, QSlider, QVBoxLayout, QWidget)

from .. import appearance, paths, prefs, style
from ..widgets import Card, ToggleSwitch, label
from .util import Page, TaskDialog, control_panel, in_background, ok, run, spawn


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def cpu_name():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return re.sub(r"\s+", " ", line.split(":", 1)[1]).strip()
    except OSError:
        pass
    return platform.processor() or "Unknown processor"


def ram_total():
    try:
        with open("/proc/meminfo") as f:
            kb = int(f.readline().split()[1])
        return kb * 1024
    except (OSError, ValueError, IndexError):
        return 0


def installed_on():
    for p in ("/var/log/installer", "/var/log/calamares", "/etc/hostname"):
        if os.path.exists(p):
            return time.strftime("%-d/%m/%Y", time.localtime(os.stat(p).st_mtime))
    return "Today"


def os_info():
    rel = paths.os_release()
    return dict(name=rel.get("NAME", "Glass Panes"), version=rel.get("VERSION_ID", "1.0"),
                edition=rel.get("VARIANT", "Home"), build=rel.get("BUILD_ID", ""),
                debian=_read("/etc/debian_version").strip(), kernel=platform.release())


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def device_name():
    return socket.gethostname()


# ----------------------------------------------------------------------------- System home

class SystemPage(Page):
    title = "System"

    def build(self):
        hero = Card()
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(20, 18, 20, 18)
        hl.setSpacing(20)
        thumb = QLabel()
        px = QPixmap(prefs.wallpaper()).scaled(200, 125, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                               Qt.TransformationMode.SmoothTransformation)
        thumb.setPixmap(px.copy(0, 0, 200, 125))
        thumb.setFixedSize(200, 125)
        thumb.setStyleSheet(f"border: 6px solid {'#1c1c1c' if not self.t.dark else '#0e0e0e'}; border-radius: 8px;")
        hl.addWidget(thumb)
        names = QVBoxLayout()
        self.name_label = QLabel(device_name())
        self.name_label.setFont(style.font(15, QFont.Weight.DemiBold))
        names.addWidget(self.name_label)
        names.addWidget(label(f"{os_info()['name']} {os_info()['edition']}", "secondary"))
        rename = QPushButton("Rename")
        rename.setProperty("link", "true")
        rename.setCursor(Qt.CursorShape.PointingHandCursor)
        rename.clicked.connect(lambda: rename_pc(self))
        names.addWidget(rename, 0, Qt.AlignmentFlag.AlignLeft)
        names.addStretch(1)
        hl.addLayout(names, 1)
        upd = QVBoxLayout()
        upd_btn = QPushButton("  Glass Update")
        upd_btn.setIcon(style.icon("arrow_sync_circle", self.t.accent_text, 20))
        upd_btn.setProperty("flat", "true")
        upd_btn.clicked.connect(lambda: self.window.open("update", reset=True))
        upd.addWidget(upd_btn)
        upd.addWidget(label("Check for updates", "secondary"))
        upd.addStretch(1)
        hl.addLayout(upd)
        self.add(hero)
        self.body.addSpacing(8)
        self.row("desktop", "Display", "Monitors, brightness, night light, display profile", open_key="display")
        self.row("speaker_2", "Sound", "Volume levels, output, input, sound devices", open_key="sound")
        self.row("alert", "Notifications", "Alerts from apps and system, do not disturb", open_key="notifications")
        self.row("battery_10", "Power & battery", "Sleep, battery usage, power mode", open_key="power")
        self.row("hard_drive", "Storage", "Storage space, drives, configuration rules", open_key="storage")
        self.row("window_multiple", "Multitasking", "Snap windows, desktops, task switching",
                 open_key="multitasking")
        self.row("print", "Printers & scanners", "Preferences, troubleshoot", open_key="printers")
        self.row("info", "About", "Device specifications, rename PC, Glass Panes specifications",
                 open_key="about")

    def refresh(self):
        self.name_label.setText(device_name())


def rename_pc(page):
    name, accepted = QInputDialog.getText(page, "Rename your PC",
                                          "You can use a combination of letters, hyphens and numbers.",
                                          text=device_name())
    name = name.strip()
    if not accepted or not name:
        return
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", name):
        QMessageBox.warning(page, "Rename your PC", "Use only letters, numbers and hyphens.")
        return
    if ok("hostnamectl", "set-hostname", name, timeout=120):
        QMessageBox.information(page, "Rename your PC",
                                "Your PC will use its new name after you restart.")
        page.refresh()


# ----------------------------------------------------------------------------- Display

def kscreen_outputs():
    out = run("kscreen-doctor", "-j", timeout=10)
    try:
        return [o for o in json.loads(out).get("outputs", []) if o.get("connected")]
    except ValueError:
        return []


ROTATIONS = [("Landscape", "normal", 1), ("Portrait", "left", 2), ("Landscape (flipped)", "inverted", 4),
             ("Portrait (flipped)", "right", 8)]


class DisplayPage(Page):
    title = "Display"
    parent_key = "system"

    def build(self):
        outs = kscreen_outputs()
        self.output = outs[0] if outs else None
        self.section("Brightness & colour")
        self.brightness_row()
        night = appearance.kread("kwinrc", ["NightColor"], "Active", "false") == "true"
        self.toggle("weather_moon", "Night light", "Use warmer colours to help block blue light",
                    night, self.set_night)
        self.section("Scale & layout")
        if self.output:
            name = self.output["name"]
            scale = float(self.output.get("scale", 1))
            scales = [(f"{int(s * 100)}%" + (" (Recommended)" if s == 1 else ""), s)
                      for s in (1.0, 1.25, 1.5, 1.75, 2.0)]
            self.combo("zoom_in", "Scale", "Change the size of text, apps, and other items", scales,
                       min(scales, key=lambda x: abs(x[1] - scale))[1],
                       lambda v: self.apply(f"output.{name}.scale.{v:g}"))
            modes = {}
            for m in self.output.get("modes", []):
                size = m.get("size", {})
                key = (size.get("width", 0), size.get("height", 0))
                if key not in modes or m.get("refreshRate", 0) > modes[key].get("refreshRate", 0):
                    modes[key] = m
            items = sorted(modes.items(), key=lambda kv: -(kv[0][0] * kv[0][1]))
            pref = self.output.get("preferredModes", [None])[0] if self.output.get("preferredModes") else None
            choices = []
            for (w, h), m in items:
                rec = " (Recommended)" if m.get("id") == pref else ""
                choices.append((f"{w} × {h}{rec}", f"{w}x{h}@{round(m.get('refreshRate', 60))}"))
            cur = next((m for m in self.output.get("modes", []) if m.get("id") == self.output.get("currentModeId")), None)
            cur_val = None
            if cur:
                s = cur.get("size", {})
                best = modes.get((s.get("width"), s.get("height")), cur)
                cur_val = f"{s.get('width')}x{s.get('height')}@{round(best.get('refreshRate', 60))}"
            self.combo("desktop", "Display resolution", "Adjust the resolution to fit your connected display",
                       choices, cur_val, lambda v: self.apply(f"output.{name}.mode.{v}"))
            rot = self.output.get("rotation", 1)
            self.combo("arrow_clockwise", "Display orientation", "", [(a, b) for a, b, _ in ROTATIONS],
                       next((b for _a, b, n in ROTATIONS if n == rot), "normal"),
                       lambda v: self.apply(f"output.{name}.rotation.{v}"))
        else:
            self.note("Display settings aren't available right now.")
        self.section("Related settings")
        self.row("desktop_mac", "Advanced display", "Multiple displays, refresh rate, display arrangement",
                 on_click=lambda: control_panel("kcm_kscreen"))

    def brightness_row(self):
        val = run("qdbus6", "org.kde.Solid.PowerManagement",
                  "/org/kde/Solid/PowerManagement/Actions/BrightnessControl", "brightness").strip()
        mx = run("qdbus6", "org.kde.Solid.PowerManagement",
                 "/org/kde/Solid/PowerManagement/Actions/BrightnessControl", "brightnessMax").strip()
        if not (val.isdigit() and mx.isdigit() and int(mx) > 0):
            return
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, int(mx))
        s.setValue(int(val))
        s.setFixedWidth(220)
        s.valueChanged.connect(lambda v: spawn(
            "qdbus6", "org.kde.Solid.PowerManagement",
            "/org/kde/Solid/PowerManagement/Actions/BrightnessControl", "setBrightness", str(v)))
        self.row("brightness_high", "Brightness", "Adjust the brightness of the built-in display", s)

    def set_night(self, on):
        appearance.kwrite("kwinrc", ["NightColor"], "Active", "true" if on else "false")
        appearance.qdbus("org.kde.KWin", "/KWin", "reconfigure")

    def apply(self, arg):
        in_background(self, lambda: ok("kscreen-doctor", arg, timeout=20), lambda _r: None)


# ----------------------------------------------------------------------------- Sound

def pactl_json(*args):
    out = run("pactl", "-f", "json", *args, timeout=10)
    try:
        return json.loads(out)
    except ValueError:
        return []


def volume_percent(dev):
    vols = dev.get("volume", {})
    for ch in vols.values():
        p = str(ch.get("value_percent", "0%")).rstrip("%")
        try:
            return int(p)
        except ValueError:
            pass
    return 0


class SoundPage(Page):
    title = "Sound"
    parent_key = "system"

    def build(self):
        self.section("Output")
        sinks = [s for s in pactl_json("list", "sinks") if isinstance(s, dict)]
        default = run("pactl", "get-default-sink").strip()
        if sinks:
            items = [(s.get("description") or s.get("name"), s.get("name")) for s in sinks]
            self.combo("speaker_2", "Choose where to play sound",
                       "Apps might have their own settings", items, default,
                       lambda v: ok("pactl", "set-default-sink", v))
            cur = next((s for s in sinks if s.get("name") == default), sinks[0])
            self.slider_row("speaker_2", "Volume", volume_percent(cur),
                            lambda v: ok("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%"))
            muted = bool(cur.get("mute"))
            self.toggle("speaker_mute", "Mute", "", muted,
                        lambda on: ok("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if on else "0"))
        else:
            self.note("No output devices found.")
        self.section("Input")
        sources = [s for s in pactl_json("list", "sources") if isinstance(s, dict)
                   and not str(s.get("name", "")).endswith(".monitor")]
        if sources:
            default_in = run("pactl", "get-default-source").strip()
            items = [(s.get("description") or s.get("name"), s.get("name")) for s in sources]
            self.combo("mic", "Choose a device for speaking or recording",
                       "Apps might have their own settings", items, default_in,
                       lambda v: ok("pactl", "set-default-source", v))
            cur = next((s for s in sources if s.get("name") == default_in), sources[0])
            self.slider_row("mic", "Volume", volume_percent(cur),
                            lambda v: ok("pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{v}%"))
        else:
            self.note("No input devices found.")
        self.section("Advanced")
        self.row("options", "More sound settings", "Per-app volume, device profiles",
                 on_click=lambda: control_panel("kcm_pulseaudio"))

    def slider_row(self, icon, title, value, cb):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(value)
        s.setFixedWidth(220)
        val = QLabel(str(value))
        val.setFixedWidth(28)
        s.valueChanged.connect(lambda v: (val.setText(str(v)), cb(v)))
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(val)
        h.addWidget(s)
        self.row(icon, title, "", w)


# ----------------------------------------------------------------------------- Notifications

class NotificationsPage(Page):
    title = "Notifications"
    parent_key = "system"

    def build(self):
        dnd = appearance.kread("plasmanotifyrc", ["DoNotDisturb"], "WhenScreensMirrored", "true")
        popups = appearance.kread("plasmanotifyrc", ["Notifications"], "PopupPosition", "") != "Hidden"
        self.toggle("alert", "Notifications", "Get notifications from apps and other senders", popups,
                    self.set_popups)
        self.toggle("alert", "Do not disturb when sharing my screen",
                    "Notifications stay silent while you present", dnd == "true",
                    lambda on: appearance.kwrite("plasmanotifyrc", ["DoNotDisturb"], "WhenScreensMirrored",
                                                 "true" if on else "false"))
        self.section("Related settings")
        self.row("options", "Notifications from apps and other senders", "Choose which apps can notify you",
                 on_click=lambda: control_panel("kcm_notifications"))

    def set_popups(self, on):
        appearance.kwrite("plasmanotifyrc", ["Notifications"], "PopupPosition",
                          "CloseToWidget" if on else "Hidden")


# ----------------------------------------------------------------------------- Power

POWER_MODES = [("Best power efficiency", "power-saver"), ("Balanced", "balanced"),
               ("Best performance", "performance")]
TIMEOUTS = [("1 minute", 60), ("2 minutes", 120), ("3 minutes", 180), ("5 minutes", 300),
            ("10 minutes", 600), ("15 minutes", 900), ("20 minutes", 1200), ("25 minutes", 1500),
            ("30 minutes", 1800), ("45 minutes", 2700), ("1 hour", 3600), ("2 hours", 7200),
            ("5 hours", 18000), ("Never", 0)]


def battery():
    base = "/sys/class/power_supply"
    try:
        for name in os.listdir(base):
            if _read(os.path.join(base, name, "type")).strip() == "Battery":
                cap = _read(os.path.join(base, name, "capacity")).strip()
                status = _read(os.path.join(base, name, "status")).strip()
                return int(cap or 0), status
    except OSError:
        pass
    return None


class PowerPage(Page):
    title = "Power & battery"
    parent_key = "system"

    def build(self):
        b = battery()
        if b:
            c, lay = self.card()
            big = QLabel(f"{b[0]}%")
            big.setFont(style.font(22, QFont.Weight.DemiBold))
            lay.addWidget(big)
            lay.addWidget(label(b[1], "secondary"))
        self.section("Power")
        sources = [("AC", "When plugged in")] + ([("Battery", "On battery power")] if b else [])
        for group, words in sources:
            display = appearance.kread("powerdevilrc", [group, "Display"], "TurnOffDisplayIdleTimeoutSec",
                                       "600" if group == "AC" else "300")
            sleep = appearance.kread("powerdevilrc", [group, "SuspendAndShutdown"],
                                     "AutoSuspendIdleTimeoutSec", "0" if group == "AC" else "900")
            self.combo("desktop", f"{words}, turn off my screen after", "", TIMEOUTS,
                       int(display or 0) if display.lstrip("-").isdigit() else 600,
                       lambda v, g=group: self.set_display(g, v))
            self.combo("weather_moon", f"{words}, put my device to sleep after", "", TIMEOUTS,
                       int(sleep or 0) if sleep.lstrip("-").isdigit() else 0,
                       lambda v, g=group: self.set_sleep(g, v))
        mode = run("powerprofilesctl", "get").strip()
        if mode:
            self.combo("top_speed", "Power mode", "Optimise your device based on power use and performance",
                       POWER_MODES, mode, lambda v: ok("powerprofilesctl", "set", v))
        self.section("Related settings")
        self.row("options", "Advanced power settings", "Lid, power button, energy saving",
                 on_click=lambda: control_panel("kcm_powerdevilprofilesconfig"))

    def _reload(self):
        appearance.qdbus("org.kde.Solid.PowerManagement", "/org/kde/Solid/PowerManagement",
                         "org.kde.Solid.PowerManagement.refreshStatus")

    def set_display(self, group, secs):
        appearance.kwrite("powerdevilrc", [group, "Display"], "TurnOffDisplayWhenIdle",
                          "true" if secs else "false")
        if secs:
            appearance.kwrite("powerdevilrc", [group, "Display"], "TurnOffDisplayIdleTimeoutSec", secs)
        self._reload()

    def set_sleep(self, group, secs):
        appearance.kwrite("powerdevilrc", [group, "SuspendAndShutdown"], "AutoSuspendAction",
                          "1" if secs else "0")
        if secs:
            appearance.kwrite("powerdevilrc", [group, "SuspendAndShutdown"], "AutoSuspendIdleTimeoutSec", secs)
        self._reload()


# ----------------------------------------------------------------------------- Storage

def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


class StoragePage(Page):
    title = "Storage"
    parent_key = "system"

    def build(self):
        du = shutil.disk_usage("/")
        c, lay = self.card()
        head = QHBoxLayout()
        head.addWidget(label("Local Disk (C:)"))
        head.addStretch(1)
        head.addWidget(label(f"{human(du.used)} used", "secondary"))
        lay.addLayout(head)
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(int(du.used / du.total * 1000))
        bar.setStyleSheet("QProgressBar { max-height: 8px; min-height: 8px; border-radius: 4px; }"
                          "QProgressBar::chunk { border-radius: 4px; }")
        lay.addWidget(bar)
        lay.addWidget(label(f"{human(du.free)} free of {human(du.total)}", "secondary"))
        self.section("Show more categories")
        home = os.path.expanduser("~")
        self.cat_rows = {}
        cats = [("Documents", "document", os.path.join(home, "Documents")),
                ("Pictures", "image", os.path.join(home, "Pictures")),
                ("Music", "music_note_2", os.path.join(home, "Music")),
                ("Videos", "video", os.path.join(home, "Videos")),
                ("Downloads", "arrow_download", os.path.join(home, "Downloads")),
                ("Windows apps (C: drive)", "window_apps", os.path.join(home, ".wine")),
                ("Temporary files", "delete", os.path.join(home, ".cache")),
                ("Recycle Bin", "bin_recycle", os.path.join(home, ".local/share/Trash"))]
        for name, icon, path in cats:
            r = self.row(icon, name, "Calculating…")
            self.cat_rows[name] = (r, path)
        self.section("Storage management")
        self.row("broom", "Cleanup recommendations", "Empty the Recycle Bin and remove temporary files",
                 on_click=self.cleanup)
        self.row("hard_drive", "Disks & volumes", "Manage partitions and drives",
                 on_click=lambda: spawn("partitionmanager"))

    def refresh(self):
        for name, (r, path) in self.cat_rows.items():
            in_background(self, lambda p=path: dir_size(p) if os.path.exists(p) else 0,
                          lambda size, rr=r: rr.set_description(human(size) if isinstance(size, int) else ""))

    def cleanup(self):
        if QMessageBox.question(self, "Cleanup recommendations",
                                "Empty the Recycle Bin and delete temporary files and thumbnails?") \
                != QMessageBox.StandardButton.Yes:
            return
        home = os.path.expanduser("~")
        for p in (os.path.join(home, ".local/share/Trash/files"), os.path.join(home, ".local/share/Trash/info"),
                  os.path.join(home, ".cache/thumbnails")):
            shutil.rmtree(p, ignore_errors=True)
        TaskDialog(self, "Removing downloaded update files", ["pkexec", "apt-get", "clean"]).exec()
        self.refresh()


# ----------------------------------------------------------------------------- Multitasking

class MultitaskingPage(Page):
    title = "Multitasking"
    parent_key = "system"

    def build(self):
        snap = appearance.kread("kwinrc", ["Windows"], "ElectricBorderTiling", "true") != "false"
        self.toggle("window_multiple", "Snap windows",
                    "Drag a window to the side or corner of the screen to snap it", snap, self.set_snap)
        shake = appearance.kread("kwinrc", ["Plugins"], "shakecursorEnabled", "false") == "true"
        self.toggle("cursor", "Shake the mouse to find the pointer", "", shake,
                    lambda on: self.kwin_plugin("shakecursor", on))
        self.section("Desktops")
        self.row("desktop", "Virtual desktops", "Add, remove and rename desktops",
                 on_click=lambda: control_panel("kcm_kwin_virtualdesktops"))
        self.row("window_apps", "Alt + Tab", "Choose how open windows are shown",
                 on_click=lambda: control_panel("kcm_kwintabbox"))

    def set_snap(self, on):
        v = "true" if on else "false"
        appearance.kwrite("kwinrc", ["Windows"], "ElectricBorderTiling", v)
        appearance.kwrite("kwinrc", ["Windows"], "ElectricBorderMaximize", v)
        appearance.qdbus("org.kde.KWin", "/KWin", "reconfigure")

    def kwin_plugin(self, name, on):
        appearance.kwrite("kwinrc", ["Plugins"], f"{name}Enabled", "true" if on else "false")
        appearance.qdbus("org.kde.KWin", "/KWin", "reconfigure")


# ----------------------------------------------------------------------------- About

class AboutPage(Page):
    title = "About"
    parent_key = "system"

    def build(self):
        hero = Card()
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(20, 16, 20, 16)
        logo = QLabel()
        logo.setPixmap(QPixmap(paths.artwork("logo-64.png")))
        logo.setFixedSize(64, 64)
        hl.addWidget(logo)
        col = QVBoxLayout()
        self.hero_name = QLabel(device_name())
        self.hero_name.setFont(style.font(13, QFont.Weight.DemiBold))
        col.addWidget(self.hero_name)
        col.addWidget(label(platform.node() and "Glass Panes PC", "secondary"))
        hl.addLayout(col, 1)
        hl.addWidget(self.button("Rename this PC", lambda: rename_pc(self)))
        self.add(hero)
        info = os_info()
        mem = ram_total()
        specs = [("Device name", device_name()), ("Processor", cpu_name()),
                 ("Installed RAM", f"{mem / 1024 ** 3:.1f} GB"),
                 ("Device ID", _read("/etc/machine-id").strip()[:32] or "—"),
                 ("System type", f"64-bit operating system, {platform.machine()} processor")]
        self.spec_card("desktop", "Device specifications", specs)
        ossp = [("Edition", f"{info['name']} {info['edition']}"), ("Version", info["version"]),
                ("Installed on", installed_on()), ("OS build", info["build"] or info["version"]),
                ("Based on", f"Debian {info['debian']} · Linux {info['kernel']}"),
                ("Experience", "No ads, no tracking, no bloatware")]
        self.spec_card("window_apps", "Glass Panes specifications", ossp)
        self.section("Related")
        self.row("info", "System information", "Hardware details and drivers (Device Manager)",
                 on_click=lambda: spawn("kinfocenter"))

    def spec_card(self, icon, title, rows):
        c = Card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(16, 14, 16, 14)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(style.icon_pixmap(icon, self.t.text, 20, 2.0))
        head.addWidget(ic)
        head.addWidget(label(title, "section"))
        head.addStretch(1)
        text = "\n".join(f"{k}\t{v}" for k, v in rows)
        copy = self.button("Copy", lambda: QGuiApplication.clipboard().setText(text))
        head.addWidget(copy)
        lay.addLayout(head)
        for k, v in rows:
            r = QHBoxLayout()
            kl = label(k, "secondary")
            kl.setFixedWidth(160)
            r.addWidget(kl)
            vl = QLabel(v)
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            vl.setWordWrap(True)
            r.addWidget(vl, 1)
            lay.addLayout(r)
        self.add(c)

    def refresh(self):
        self.hero_name.setText(device_name())


def show_winver():
    info = os_info()
    d = QDialog()
    d.setWindowTitle(f"About {info['name']}")
    d.setFixedSize(460, 300)
    lay = QVBoxLayout(d)
    lay.setContentsMargins(28, 24, 28, 20)
    head = QHBoxLayout()
    logo = QLabel()
    logo.setPixmap(QPixmap(paths.artwork("logo-64.png")))
    head.addWidget(logo)
    t = QLabel(info["name"])
    t.setFont(style.font(24, QFont.Weight.Light))
    head.addWidget(t)
    head.addStretch(1)
    lay.addLayout(head)
    lay.addSpacing(10)
    for line in (f"Version {info['version']} (OS Build {info['build'] or info['version']})",
                 f"Based on Debian {info['debian']} and Linux {info['kernel']}.",
                 "",
                 f"The {info['name']} {info['edition']} operating system and its user interface are",
                 "free software. Windows apps run through Wine.",
                 "", f"This product is licensed to: {os.environ.get('USER', 'user')}"):
        lay.addWidget(QLabel(line))
    lay.addStretch(1)
    row = QHBoxLayout()
    row.addStretch(1)
    b = QPushButton("OK")
    b.setProperty("accent", "true")
    b.clicked.connect(d.accept)
    row.addWidget(b)
    lay.addLayout(row)
    d.exec()


# ----------------------------------------------------------------------------- Printers

class PrintersPage(Page):
    title = "Printers & scanners"
    parent_key = "bluetooth"

    def build(self):
        c, lay = self.card()
        row = QHBoxLayout()
        row.addWidget(label("Add a printer or scanner"))
        row.addStretch(1)
        row.addWidget(self.button("Add device", lambda: spawn("kde-add-printer", "--add-printer")
                                  or control_panel("kcm_printer_manager"), accent=True))
        lay.addLayout(row)
        self.list_host = QVBoxLayout()
        self.body.addLayout(self.list_host)
        self.section("Printer preferences")
        self.row("print", "Print queues and options", "Default printer, sharing, print jobs",
                 on_click=lambda: control_panel("kcm_printer_manager"))

    def refresh(self):
        while self.list_host.count():
            w = self.list_host.takeAt(0).widget()
            if w:
                w.deleteLater()
        out = run("lpstat", "-p", timeout=5)
        printers = [line.split()[1] for line in out.splitlines() if line.startswith("printer ")]
        if not printers:
            self.list_host.addWidget(label("No printers yet. Printers on your network usually appear "
                                           "here automatically.", "secondary", wrap=True))
        from ..widgets import SettingRow
        for p in printers:
            self.list_host.addWidget(SettingRow(self.t, "print", p.replace("_", " "), "Ready"))


PAGES = {"system": SystemPage, "display": DisplayPage, "sound": SoundPage,
         "notifications": NotificationsPage, "power": PowerPage, "storage": StoragePage,
         "multitasking": MultitaskingPage, "about": AboutPage, "printers": PrintersPage}
