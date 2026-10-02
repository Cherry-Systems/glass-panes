"""Accessibility: text size, visual effects, mouse pointer, magnifier, keyboard."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from .. import appearance
from .util import Page, control_panel


class AccessibilityPage(Page):
    title = "Accessibility"

    def build(self):
        self.section("Vision")
        dpi = appearance.kread("kcmfonts", ["General"], "forceFontDPI", "0")
        try:
            pct = int(round(int(dpi) / 96 * 100)) if int(dpi) > 0 else 100
        except ValueError:
            pct = 100
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(100, 225)
        s.setSingleStep(25)
        s.setPageStep(25)
        s.setValue(pct)
        s.setFixedWidth(200)
        val = QLabel(f"{pct}%")
        val.setFixedWidth(40)
        s.valueChanged.connect(lambda v: val.setText(f"{v}%"))
        s.sliderReleased.connect(lambda: self.set_text_size(s.value()))
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(val)
        h.addWidget(s)
        self.row("text_font", "Text size", "Takes full effect after you sign out", w)
        anim = appearance.kread("kdeglobals", ["KDE"], "AnimationDurationFactor", "1") != "0"
        self.toggle("flash", "Animation effects", "", anim, self.set_animations)
        zoom = appearance.kread("kwinrc", ["Plugins"], "zoomEnabled", "true") == "true"
        self.toggle("zoom_in", "Magnifier", "Press Windows logo key + Plus (+) to zoom in", zoom,
                    lambda on: self.kwin_plugin("zoom", on))
        self.row("cursor", "Mouse pointer and touch", "Pointer size and colour", open_key="mouse")
        self.row("color", "Contrast themes", "Colour themes for low vision, light sensitivity",
                 on_click=lambda: control_panel("kcm_colors"))
        self.section("Interaction")
        sticky = appearance.kread("kaccessrc", ["Keyboard"], "StickyKeys", "false") == "true"
        self.toggle("keyboard", "Sticky keys", "Press one key at a time for keyboard shortcuts", sticky,
                    lambda on: self.set_kaccess("StickyKeys", on))
        self.row("options", "More accessibility options", "Screen reader, keyboard filters, activation gestures",
                 on_click=lambda: control_panel("kcm_access"))

    def set_text_size(self, pct):
        appearance.kwrite("kcmfonts", ["General"], "forceFontDPI", int(96 * pct / 100) if pct != 100 else 0)

    def set_animations(self, on):
        appearance.kwrite("kdeglobals", ["KDE"], "AnimationDurationFactor", "1" if on else "0")
        appearance.qdbus("org.kde.KWin", "/KWin", "reconfigure")

    def kwin_plugin(self, name, on):
        appearance.kwrite("kwinrc", ["Plugins"], f"{name}Enabled", "true" if on else "false")
        appearance.qdbus("org.kde.KWin", "/KWin", "reconfigure")

    def set_kaccess(self, key, on):
        appearance.kwrite("kaccessrc", ["Keyboard"], key, "true" if on else "false")
        appearance._run("kaccess")


PAGES = {"accessibility": AccessibilityPage}
