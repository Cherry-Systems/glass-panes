"""Personalisation: Background, Colours (light/dark, accent, transparency), Taskbar, Start, Lock screen."""
import os
import shutil

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QToolButton,
                             QVBoxLayout, QWidget)

from .. import appearance, paths, prefs, style
from ..widgets import Card, label
from .util import Page, control_panel, spawn


def preview_pixmap(wallpaper, mode, accent, w=320, h=200):
    """Small picture of the desktop: background, a window and the taskbar."""
    px = QPixmap(w, h)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, 8, 8)
    p.setClipPath(path)
    bg = QPixmap(wallpaper).scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap(0, 0, bg)
    dark = mode == "dark"
    win = QColor("#202020" if dark else "#f3f3f3")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(win)
    p.drawRoundedRect(int(w * 0.22), int(h * 0.18), int(w * 0.56), int(h * 0.5), 5, 5)
    p.setBrush(QColor(accent))
    p.drawRoundedRect(int(w * 0.28), int(h * 0.52), int(w * 0.14), int(h * 0.08), 3, 3)
    p.setBrush(QColor("#d0d0d0" if not dark else "#3a3a3a"))
    p.drawRoundedRect(int(w * 0.28), int(h * 0.28), int(w * 0.40), int(h * 0.05), 2, 2)
    p.drawRoundedRect(int(w * 0.28), int(h * 0.37), int(w * 0.30), int(h * 0.05), 2, 2)
    bar = QColor(243, 243, 243, 235) if not dark else QColor(32, 32, 32, 235)
    p.setBrush(bar)
    p.drawRect(0, h - 20, w, 20)
    p.setBrush(QColor(accent))
    for i in range(5):
        p.drawRoundedRect(int(w / 2 - 50 + i * 21), h - 15, 12, 10, 2, 2)
    p.end()
    return px


def list_wallpapers():
    found = []
    for d in (paths.WALLPAPERS, "/usr/share/wallpapers", os.path.expanduser("~/Pictures/Wallpapers")):
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in sorted(files):
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and "screenshot" not in f \
                        and "contents/screenshot" not in root:
                    found.append(os.path.join(root, f))
    return found[:24]


class PersonalisationPage(Page):
    title = "Personalisation"

    def build(self):
        p = prefs.load()
        top = Card()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 18, 20, 18)
        self.preview = QLabel()
        self.preview.setFixedSize(320, 200)
        tl.addWidget(self.preview)
        tl.addSpacing(16)
        col = QVBoxLayout()
        col.addWidget(label("Select a theme to apply", "section"))
        themes = QHBoxLayout()
        for mode, wp in (("light", prefs.default_wallpaper("light")), ("dark", prefs.default_wallpaper("dark"))):
            b = QToolButton()
            b.setIcon(QIcon(preview_pixmap(wp, mode, p["accent"], 120, 76)))
            b.setIconSize(QSize(120, 76))
            b.setToolTip(f"Glass Panes ({mode})")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QToolButton { border: 2px solid transparent; border-radius: 8px; padding: 2px; }"
                            f"QToolButton:hover {{ border-color: {self.t.accent_fill}; }}")
            b.clicked.connect(lambda _=False, m=mode: self.apply_theme(m))
            themes.addWidget(b)
        themes.addStretch(1)
        col.addLayout(themes)
        col.addStretch(1)
        tl.addLayout(col, 1)
        self.add(top)
        self.body.addSpacing(8)
        self.row("image", "Background", "Background image, colour, slideshow", open_key="background")
        self.row("color", "Colours", "Accent colour, transparency effects, colour theme", open_key="colors")
        self.row("paint_brush", "Themes", "Install, create, manage",
                 on_click=lambda: control_panel("kcm_lookandfeel"))
        self.row("lock_closed", "Lock screen", "Lock screen images, apps, animations", open_key="lockscreen")
        self.row("text_font", "Fonts", "Install, manage", on_click=lambda: control_panel("kcm_fonts"))
        self.row("grid", "Start", "Recent apps and items, folders", open_key="start")
        self.row("window_apps", "Taskbar", "Taskbar behaviours, system pins", open_key="taskbar")

    def refresh(self):
        p = prefs.load()
        self.preview.setPixmap(preview_pixmap(prefs.wallpaper(p), p["mode"], p["accent"]))

    def apply_theme(self, mode):
        appearance.apply({"mode": mode, "wallpaper": ""})
        self.window.restyle()


class BackgroundPage(Page):
    title = "Background"
    parent_key = "personalisation"

    def build(self):
        self.preview = QLabel()
        self.preview.setFixedSize(320, 200)
        h = QHBoxLayout()
        h.addWidget(self.preview)
        h.addStretch(1)
        self.body.addLayout(h)
        self.body.addSpacing(10)
        c, lay = self.card()
        lay.addWidget(label("Recent images"))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, wp in enumerate(list_wallpapers()):
            b = QToolButton()
            px = QPixmap(wp).scaled(112, 70, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                    Qt.TransformationMode.SmoothTransformation).copy(0, 0, 112, 70)
            b.setIcon(QIcon(px))
            b.setIconSize(QSize(112, 70))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(os.path.basename(wp))
            b.setStyleSheet("QToolButton { border: 2px solid transparent; border-radius: 6px; }"
                            f"QToolButton:hover {{ border-color: {self.t.accent_fill}; }}")
            b.clicked.connect(lambda _=False, w=wp: self.set_wallpaper(w))
            grid.addWidget(b, i // 5, i % 5)
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(label("Choose a photo"))
        row.addStretch(1)
        row.addWidget(self.button("Browse photos", self.browse))
        lay.addLayout(row)

    def refresh(self):
        p = prefs.load()
        self.preview.setPixmap(preview_pixmap(prefs.wallpaper(p), p["mode"], p["accent"]))

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a photo", os.path.expanduser("~/Pictures"),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            dest_dir = os.path.expanduser("~/.local/share/wallpapers")
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(path))
            if os.path.abspath(path) != dest:
                shutil.copy2(path, dest)
            self.set_wallpaper(dest)

    def set_wallpaper(self, path):
        appearance.apply({"wallpaper": path})
        self.refresh()


class ColorsPage(Page):
    title = "Colours"
    parent_key = "personalisation"

    def build(self):
        p = prefs.load()
        self.combo("dark_theme", "Choose your mode",
                   "Change the colours that appear in Glass Panes and your apps",
                   [("Light", "light"), ("Dark", "dark")], p["mode"], self.set_mode)
        self.toggle("square_multiple", "Transparency effects",
                    "Windows and surfaces appear translucent", p.get("transparency", True),
                    lambda on: appearance.apply({"transparency": on}))
        c, lay = self.card()
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(style.icon_pixmap("color", self.t.text, 20, 2.0))
        head.addWidget(ic)
        head.addSpacing(8)
        head.addWidget(label("Accent colour"))
        head.addStretch(1)
        lay.addLayout(head)
        lay.addWidget(label("Recent and Windows colours", "secondary"))
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, col in enumerate(prefs.ACCENTS):
            b = QPushButton()
            b.setFixedSize(44, 44)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            sel = col.lower() == p["accent"].lower()
            b.setStyleSheet(f"QPushButton {{ background: {col}; border-radius: 4px;"
                            f" border: {'3px solid ' + self.t.text if sel else '1px solid transparent'}; }}"
                            f"QPushButton:hover {{ border: 2px solid {self.t.text_secondary}; }}")
            b.clicked.connect(lambda _=False, c=col: self.set_accent(c))
            grid.addWidget(b, i // 10, i % 10)
        lay.addLayout(grid)
        self.section("Related settings")
        self.row("paint_brush", "Contrast themes", "Colour themes for low vision, light sensitivity",
                 on_click=lambda: control_panel("kcm_colors"))

    def set_mode(self, mode):
        appearance.apply({"mode": mode, "wallpaper": ""})
        self.window.restyle()

    def set_accent(self, color):
        appearance.apply({"accent": color})
        self.window.restyle()


class TaskbarPage(Page):
    title = "Taskbar"
    parent_key = "personalisation"

    def build(self):
        p = prefs.load()
        self.section("Taskbar behaviours")
        self.combo("window_apps", "Taskbar alignment", "", [("Center", "center"), ("Left", "left")],
                   p.get("taskbar_align", "center"), lambda v: appearance.apply({"taskbar_align": v}))
        self.section("Other system tray icons")
        self.row("options", "Taskbar and system tray", "Choose which icons appear, auto-hide, size",
                 on_click=lambda: spawn("qdbus6", "org.kde.plasmashell", "/PlasmaShell",
                                        "org.kde.PlasmaShell.evaluateScript",
                                        "panels()[0].showConfigurationInterface && panels()[0].showConfigurationInterface()"))


class StartPage(Page):
    title = "Start"
    parent_key = "personalisation"

    def build(self):
        p = prefs.load()
        self.toggle("history", "Show recently opened items in Start, Jump Lists, and File Explorer", "",
                    p.get("show_recommended", True), lambda on: prefs.update(show_recommended=on))
        self.combo("search", "Search the web with", "Used by Start when you search for something online",
                   [("Bing", "bing"), ("Google", "google"), ("DuckDuckGo", "duckduckgo")],
                   p.get("search_engine", "bing"), lambda v: prefs.update(search_engine=v))
        self.row("arrow_reset", "Reset pinned apps", "Put the original pinned apps back in Start",
                 on_click=lambda: prefs.update(pinned=list(prefs.DEFAULT_PINNED)))


class LockScreenPage(Page):
    title = "Lock screen"
    parent_key = "personalisation"

    def build(self):
        self.note("Your lock screen uses the same picture as your desktop background.")
        self.row("image", "Change background", "", open_key="background")
        self.row("lock_closed", "Screen lock timeout", "Lock automatically after a period of inactivity",
                 on_click=lambda: control_panel("kcm_screenlocker"))


PAGES = {"personalisation": PersonalisationPage, "background": BackgroundPage, "colors": ColorsPage,
         "taskbar": TaskbarPage, "start": StartPage, "lockscreen": LockScreenPage}
