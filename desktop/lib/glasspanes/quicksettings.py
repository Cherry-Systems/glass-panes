"""Quick Settings: the Windows 11 flyout behind the network, volume and battery icons on the taskbar.
Tiles for the radios and night light, volume and brightness sliders, the battery and a way into Settings."""
import os
import subprocess
import time

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QStackedWidget,
                             QVBoxLayout, QWidget)

from . import appearance, prefs, style, x11
from .settings.system import battery, pactl_json, volume_percent
from .settings.util import run
from .start import start_colors

W = 360
BAR = 48
PAD = 20
BRIGHTNESS = ["qdbus6", "org.kde.Solid.PowerManagement", "/org/kde/Solid/PowerManagement/Actions/BrightnessControl"]


def spawn(*argv):
    subprocess.Popen(list(argv), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# -- what the PC has and how it's set --------------------------------------------------------------------

def wifi_on():
    """None when there's no Wi-Fi adapter."""
    if "wifi" not in run("nmcli", "-t", "-f", "TYPE", "device", timeout=5).split():
        return None
    return run("nmcli", "radio", "wifi", timeout=5).strip() == "enabled"


def bluetooth_on():
    """None when there's no Bluetooth adapter (bluetoothctl would wait for one, so check the kernel first)."""
    try:
        if not os.listdir("/sys/class/bluetooth"):
            return None
    except OSError:
        return None
    return "Powered: yes" in run("bluetoothctl", "show", timeout=5)


def airplane_on():
    return run("nmcli", "radio", "all", timeout=5).count("disabled") >= 2


def power_profile():
    """None when the PC can't switch power profiles."""
    return run("powerprofilesctl", "get", timeout=5).strip() or None


def night_light_on():
    return appearance.kread("kwinrc", ["NightColor"], "Active", "false") == "true"


def brightness():
    val = run(*BRIGHTNESS, "brightness", timeout=5).strip()
    mx = run(*BRIGHTNESS, "brightnessMax", timeout=5).strip()
    if val.isdigit() and mx.isdigit() and int(mx) > 0:
        return int(val), int(mx)
    return None


def sinks():
    found = [s for s in pactl_json("list", "sinks") if isinstance(s, dict)]
    default = run("pactl", "get-default-sink", timeout=5).strip()
    return found, next((s for s in found if s.get("name") == default), found[0] if found else None)


# -- the flyout ----------------------------------------------------------------------------------------------

class Tile(QWidget):
    """A Quick Settings tile: an on/off button (optionally split with a '>' for more) and its name below."""

    def __init__(self, t, icon, text, on, toggle=None, more=None):
        super().__init__()
        self.t, self.icon_name, self.on, self.toggle = t, icon, on, toggle
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(1)
        self.main = QPushButton()
        self.main.setFixedHeight(48)
        self.main.setAccessibleName(text)
        self.main.setObjectName("tileLeft" if more and toggle else "tile")
        self.main.clicked.connect(self.clicked)
        row.addWidget(self.main, 1)
        self.more = None
        if more and toggle:
            self.more = QPushButton()
            self.more.setObjectName("tileRight")
            self.more.setFixedSize(32, 48)
            self.more.setAccessibleName(f"{text} settings")
            self.more.clicked.connect(more)
            row.addWidget(self.more)
        elif more:
            self.main.clicked.disconnect()
            self.main.clicked.connect(more)
        v.addLayout(row)
        name = QLabel(text)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setFont(style.font(9))
        v.addWidget(name)
        self.paint_state()

    def clicked(self):
        if self.toggle is None:
            return
        self.on = not self.on
        self.paint_state()
        self.toggle(self.on)

    def paint_state(self):
        color = self.t.on_accent if self.on else self.t.text
        self.main.setIcon(style.icon(self.icon_name, color, 16))
        for b in (self.main, self.more):
            if b is None:
                continue
            b.setProperty("active", bool(self.on))
            b.style().unpolish(b)
            b.style().polish(b)
        if self.more:
            self.more.setIcon(style.icon("chevron_right", color, 12))


class QuickSettings(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Quick Settings")
        self.setFixedWidth(W)
        self._hidden_at = 0.0
        self._anim = self._fade = None
        self.stack = None

    # -- building ------------------------------------------------------------------------------------------
    def build(self):
        self.p = prefs.load()
        self.t = t = style.make_theme()
        self.c = start_colors(t)
        if self.layout():
            QWidget().setLayout(self.layout())
        for child in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.deleteLater()
        tile_bg = "rgba(255,255,255,0.06)" if t.dark else "rgba(255,255,255,0.7)"
        tile_hover = "rgba(255,255,255,0.09)" if t.dark else "rgba(249,249,249,0.5)"
        tile_border = "rgba(255,255,255,0.08)" if t.dark else "rgba(0,0,0,0.07)"
        self.setStyleSheet(f"""
            * {{ color: {t.text}; }}
            QLabel {{ background: transparent; }}
            QPushButton#tile, QPushButton#tileLeft, QPushButton#tileRight {{ background: {tile_bg};
                border: 1px solid {tile_border}; border-radius: 4px; }}
            QPushButton#tileLeft {{ border-top-right-radius: 0; border-bottom-right-radius: 0; }}
            QPushButton#tileRight {{ border-top-left-radius: 0; border-bottom-left-radius: 0; }}
            QPushButton#tile:hover, QPushButton#tileLeft:hover, QPushButton#tileRight:hover {{
                background: {tile_hover}; }}
            QPushButton#tile[active="true"], QPushButton#tileLeft[active="true"],
            QPushButton#tileRight[active="true"] {{ background: {t.accent_fill}; border-color: {t.accent_fill}; }}
            QPushButton#tile[active="true"]:hover, QPushButton#tileLeft[active="true"]:hover,
            QPushButton#tileRight[active="true"]:hover {{ background: {t.accent_hover}; }}
            QPushButton#flat {{ background: transparent; border: none; border-radius: 4px; padding: 6px; }}
            QPushButton#flat:hover {{ background: {self.c['hover']}; }}
            QPushButton#device {{ background: transparent; border: none; border-radius: 4px; padding: 10px 12px;
                text-align: left; }}
            QPushButton#device:hover {{ background: {self.c['hover']}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {t.text_disabled}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {t.accent_fill}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {t.accent_fill}; width: 12px; margin: -8px 0;
                border-radius: 10px; border: 4px solid {t.card}; }}
            QSlider::handle:horizontal:hover {{ border-width: 3px; }}
        """)
        self.setFont(style.font())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_main())
        outer.addWidget(self.stack)
        outer.addWidget(self.build_bar())

    def flat_button(self, icon, name, cb, size=16):
        b = QPushButton()
        b.setObjectName("flat")
        b.setIcon(style.icon(icon, self.t.text, size))
        b.setAccessibleName(name)
        b.setToolTip(name)
        b.clicked.connect(cb)
        return b

    def build_main(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(PAD, PAD + 4, PAD, PAD)
        v.setSpacing(18)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(14)
        tiles = []
        wifi = wifi_on()
        if wifi is not None:
            tiles.append(Tile(self.t, "wifi_1", "Wi-Fi", wifi,
                              lambda on: spawn("nmcli", "radio", "wifi", "on" if on else "off"),
                              lambda: self.open_settings("network")))
        bt = bluetooth_on()
        if bt is not None:
            tiles.append(Tile(self.t, "bluetooth", "Bluetooth", bt,
                              lambda on: spawn("bluetoothctl", "power", "on" if on else "off"),
                              lambda: self.open_settings("bluetooth")))
        tiles.append(Tile(self.t, "airplane", "Airplane mode", airplane_on(),
                          lambda on: spawn("nmcli", "radio", "all", "off" if on else "on")))
        profile = power_profile()
        if profile is not None:
            tiles.append(Tile(self.t, "leaf_one", "Energy saver", profile == "power-saver",
                              lambda on: spawn("powerprofilesctl", "set", "power-saver" if on else "balanced")))
        tiles.append(Tile(self.t, "weather_moon", "Night light", night_light_on(), appearance.set_night_light))
        tiles.append(Tile(self.t, "accessibility", "Accessibility", False, None,
                          lambda: self.open_settings("accessibility")))
        for i, tile in enumerate(tiles):
            grid.addWidget(tile, i // 3, i % 3)
        v.addLayout(grid)

        level = brightness()
        if level is not None:
            v.addLayout(self.slider_row("brightness_high", "Brightness", level[0], level[1],
                                        lambda val: spawn(*BRIGHTNESS, "setBrightness", str(val))))
        found, sink = sinks()
        if sink is not None:
            self.muted = bool(sink.get("mute"))
            self.mute_button = self.flat_button(self.speaker_icon(volume_percent(sink)), "Mute", self.toggle_mute)
            row = self.slider_row(None, "Volume", volume_percent(sink), 100, self.set_volume, self.mute_button)
            row.addWidget(self.flat_button("chevron_right", "Select a sound output",
                                           lambda: self.show_outputs(found, sink), 12))
            v.addLayout(row)
        return page

    def slider_row(self, icon, name, value, maximum, cb, lead=None):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(lead or self.flat_button(icon, name, lambda: None))
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, maximum)
        s.setValue(value)
        s.setAccessibleName(name)
        s.valueChanged.connect(cb)
        row.addWidget(s, 1)
        return row

    def build_bar(self):
        bar = QWidget()
        bar.setFixedHeight(BAR)
        h = QHBoxLayout(bar)
        h.setContentsMargins(PAD - 4, 0, PAD - 8, 0)
        h.setSpacing(4)
        bat = battery()
        if bat is not None:
            pct, status = bat
            icon = QLabel()
            icon.setPixmap(style.icon_pixmap("battery_charge" if status == "Charging" else "battery_10",
                                             self.t.text, 16, 2.0))
            h.addWidget(icon)
            h.addWidget(QLabel(f"{pct}%"))
        h.addStretch(1)
        h.addWidget(self.flat_button("settings", "All settings", lambda: self.open_settings(None)))
        return bar

    def show_outputs(self, found, current):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(PAD - 6, PAD - 6, PAD - 6, PAD)
        v.setSpacing(2)
        head = QHBoxLayout()
        head.addWidget(self.flat_button("arrow_left", "Back", lambda: self.go_back(page)))
        title = QLabel("Sound output")
        title.setFont(style.font(11, QFont.Weight.DemiBold))
        head.addWidget(title, 1)
        v.addLayout(head)
        v.addSpacing(8)
        for s in found:
            b = QPushButton(s.get("description") or s.get("name"))
            b.setObjectName("device")
            if s is current:
                b.setIcon(style.icon("checkmark", self.t.accent_text, 16))
            b.clicked.connect(lambda _c=False, name=s.get("name"): (spawn("pactl", "set-default-sink", name),
                                                                    self.hide_menu()))
            v.addWidget(b)
        v.addSpacing(8)
        more = QPushButton("More volume settings")
        more.setObjectName("device")
        more.setStyleSheet(f"color: {self.t.accent_text};")
        more.clicked.connect(lambda: self.open_settings("sound"))
        v.addWidget(more)
        v.addStretch(1)
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def go_back(self, page):
        self.stack.setCurrentIndex(0)
        self.stack.removeWidget(page)
        page.deleteLater()

    # -- actions ---------------------------------------------------------------------------------------------
    @staticmethod
    def speaker_icon(pct, muted=False):
        if muted or pct == 0:
            return "speaker_mute"
        return "speaker_0" if pct < 34 else "speaker_1" if pct < 67 else "speaker_2"

    def set_volume(self, pct):
        spawn("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%")
        if self.muted and pct > 0:
            self.muted = False
            spawn("pactl", "set-sink-mute", "@DEFAULT_SINK@", "0")
        self.mute_button.setIcon(style.icon(self.speaker_icon(pct, self.muted), self.t.text, 16))

    def toggle_mute(self):
        self.muted = not self.muted
        spawn("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if self.muted else "0")
        _found, sink = sinks()
        pct = volume_percent(sink) if sink else 0
        self.mute_button.setIcon(style.icon(self.speaker_icon(pct, self.muted), self.t.text, 16))

    def open_settings(self, page):
        self.hide_menu()
        spawn("glass-settings", *(["--page", page] if page else []))

    # -- showing -----------------------------------------------------------------------------------------------
    def toggle(self):
        if self.isVisible():
            self.hide_menu()
        elif time.monotonic() - self._hidden_at > 0.3:
            self.show_menu()

    def show_menu(self):
        self.build()
        self.adjustSize()
        screen = QGuiApplication.screenAt(QGuiApplication.primaryScreen().geometry().center()) \
            or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        end = QPoint(avail.right() - W - 11, avail.bottom() - self.height() - 11)
        self.move(end + QPoint(0, 40))
        self.setWindowOpacity(0.0)
        self.show()
        x11.enable_blur(int(self.winId()), self.p.get("transparency", True))
        self.raise_()
        self.activateWindow()
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(end + QPoint(0, 40))
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._anim.start()
        self._fade.start()

    def hide_menu(self):
        if self.isVisible():
            self.hide()

    def hideEvent(self, e):
        self._hidden_at = time.monotonic()
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            if self.stack is not None and self.stack.currentIndex() > 0:
                self.go_back(self.stack.currentWidget())
            else:
                self.hide_menu()
            return
        super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(self.c["bg"])
        if not self.p.get("transparency", True):
            bg.setAlpha(255)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.fillPath(path, bg)
        p.save()
        p.setClipPath(path)
        bar = QRectF(r.left(), r.bottom() - BAR, r.width(), BAR)
        p.fillRect(bar, self.c["bar"])
        p.setPen(QPen(self.c["border"], 1))
        p.drawLine(bar.topLeft(), bar.topRight())
        p.restore()
        p.setPen(QPen(self.c["border"], 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 8, 8)


def main():
    import sys
    app = QApplication(sys.argv)
    style.apply_app_style(app)
    qs = QuickSettings()
    qs.show_menu()
    if "--screenshot" in sys.argv:
        from PyQt6.QtCore import QTimer
        out = sys.argv[sys.argv.index("--screenshot") + 1]
        QTimer.singleShot(900, lambda: (qs.grab().save(out), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
