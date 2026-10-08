"""Snap layouts (Win+Z): the Windows 11 flyout of screen layouts. Clicking a zone snaps the active
window into that part of the screen. Number keys work too: the layout first, then the zone."""
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGridLayout, QPushButton, QWidget

from . import prefs, style, x11
from .start import start_colors

H, T = 1 / 2, 1 / 3
LAYOUTS = [
    [("Left half", (0, 0, H, 1)), ("Right half", (H, 0, H, 1))],
    [("Left two-thirds", (0, 0, 2 * T, 1)), ("Right third", (2 * T, 0, T, 1))],
    [("Left third", (0, 0, T, 1)), ("Middle third", (T, 0, T, 1)), ("Right third", (2 * T, 0, T, 1))],
    [("Left half", (0, 0, H, 1)), ("Top right quarter", (H, 0, H, H)), ("Bottom right quarter", (H, H, H, H))],
    [("Top left quarter", (0, 0, H, H)), ("Top right quarter", (H, 0, H, H)),
     ("Bottom left quarter", (0, H, H, H)), ("Bottom right quarter", (H, H, H, H))],
    [("Left quarter", (0, 0, 1 / 4, 1)), ("Middle half", (1 / 4, 0, H, 1)), ("Right quarter", (3 / 4, 0, 1 / 4, 1))],
]
BOX_W, BOX_H, GAP, PAD = 112, 70, 3, 12


def zone_rect(area, frac):
    """The part of `area` (a QRect) that a zone covers; neighbouring zones share their edges exactly."""
    fx, fy, fw, fh = frac
    x0 = area.x() + round(fx * area.width())
    y0 = area.y() + round(fy * area.height())
    x1 = area.x() + round((fx + fw) * area.width())
    y1 = area.y() + round((fy + fh) * area.height())
    return QRect(x0, y0, x1 - x0, y1 - y0)


class SnapLayouts(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Snap layouts")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.target = 0
        self.screen_area = QRect()
        self.chosen = None
        self.zones = []

    def build(self):
        self.p = prefs.load()
        self.t = t = style.make_theme()
        self.c = start_colors(t)
        if self.layout():
            QWidget().setLayout(self.layout())
        for child in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.deleteLater()
        zone_bg = "rgba(255,255,255,0.10)" if t.dark else "rgba(255,255,255,0.85)"
        zone_border = "rgba(255,255,255,0.18)" if t.dark else "rgba(0,0,0,0.18)"
        self.setStyleSheet(f"""
            QPushButton {{ background: {zone_bg}; border: 1px solid {zone_border}; border-radius: 3px; }}
            QPushButton:hover, QPushButton:focus, QPushButton[picked="true"] {{
                background: {t.accent_fill}; border-color: {t.accent_fill}; }}
        """)
        grid = QGridLayout(self)
        grid.setContentsMargins(PAD, PAD, PAD, PAD)
        grid.setSpacing(PAD)
        self.zones = []
        for i, layout in enumerate(LAYOUTS):
            box = QWidget()
            box.setFixedSize(BOX_W, BOX_H)
            buttons = []
            for name, frac in layout:
                b = QPushButton(box)
                r = zone_rect(QRect(0, 0, BOX_W + GAP, BOX_H + GAP), frac)
                b.setGeometry(r.adjusted(0, 0, -GAP, -GAP))
                b.setAccessibleName(f"{name} (layout {i + 1})")
                b.setToolTip(name)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, f=frac: self.snap(f))
                buttons.append(b)
            self.zones.append(buttons)
            grid.addWidget(box, i // 3, i % 3)

    def show_for(self, x, y, w, h):
        """Shows the layouts by the top right of the active window, whose frame is at x, y, w, h."""
        self.target = x11.active_window()
        if not self.target:
            return
        self.build()
        self.adjustSize()
        k = QGuiApplication.primaryScreen().devicePixelRatio()
        x, y, w, h = (round(v / k) for v in (x, y, w, h))
        screen = QGuiApplication.screenAt(QPoint(x + w // 2, y + h // 2)) or QGuiApplication.primaryScreen()
        self.screen_area = screen.availableGeometry()
        self.ratio = screen.devicePixelRatio()
        avail = self.screen_area
        px = min(max(x + w - self.width() - 12, avail.left() + 8), avail.right() - self.width() - 8)
        py = min(max(y + 40, avail.top() + 8), avail.bottom() - self.height() - 8)
        self.chosen = None
        self.move(px, py)
        self.show()
        x11.enable_blur(int(self.winId()), self.p.get("transparency", True))
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def snap(self, frac):
        self.hide()
        r = zone_rect(self.screen_area, frac)
        k = self.ratio
        wid = self.target
        x11.unmaximize(wid)
        QTimer.singleShot(120, lambda: x11.place_window(wid, round(r.x() * k), round(r.y() * k),
                                                        round(r.width() * k), round(r.height() * k)))

    def keyPressEvent(self, e):
        n = e.key() - Qt.Key.Key_1
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
        elif self.chosen is None and 0 <= n < len(LAYOUTS):
            self.chosen = n
            for b in self.zones[n]:
                b.setProperty("picked", True)
                b.style().unpolish(b)
                b.style().polish(b)
        elif self.chosen is not None and 0 <= n < len(self.zones[self.chosen]):
            self.snap(LAYOUTS[self.chosen][n][1])
        else:
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
        p.setPen(QPen(self.c["border"], 1))
        p.drawRoundedRect(r, 8, 8)


def main():
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    style.apply_app_style(app)
    s = SnapLayouts()
    s.build()
    s.adjustSize()
    s.show()
    if "--screenshot" in sys.argv:
        out = sys.argv[sys.argv.index("--screenshot") + 1]
        QTimer.singleShot(500, lambda: (s.grab().save(out), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
