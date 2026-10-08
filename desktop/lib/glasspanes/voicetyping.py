"""Win+H: Windows opens voice typing here. Glass Panes has no speech recognition, so it says so in a
small panel above the taskbar that leaves the keyboard with the app you were typing in."""
from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from . import prefs, style, x11
from .start import start_colors
from .widgets import icon_label, label

W = 380


class VoiceTyping(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Voice typing")
        self.setFixedWidth(W)
        self.timer = QTimer(self, singleShot=True, interval=8000, timeout=self.hide)

    def build(self):
        self.p = prefs.load()
        self.t = t = style.make_theme()
        self.c = start_colors(t)
        if self.layout():
            QWidget().setLayout(self.layout())
        for child in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.deleteLater()
        self.setStyleSheet(f"""
            * {{ color: {t.text}; }}
            QLabel {{ background: transparent; }}
            QPushButton {{ background: transparent; border: none; border-radius: 4px; padding: 6px; }}
            QPushButton:hover {{ background: {self.c['hover']}; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 8, 14)
        row.setSpacing(14)
        row.addWidget(icon_label("mic", t.text, 24), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = label("Voice typing isn't available on this PC")
        title.setFont(style.font(10.5, QFont.Weight.DemiBold))
        text.addWidget(title)
        text.addWidget(label("Glass Panes can't turn speech into text yet. You can keep typing with "
                             "the keyboard.", "secondary", wrap=True))
        row.addLayout(text, 1)
        close = QPushButton()
        close.setIcon(style.icon("dismiss", t.text, 12))
        close.setAccessibleName("Close")
        close.setToolTip("Close")
        close.clicked.connect(self.hide)
        row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)

    def toggle(self):
        if self.isVisible():
            self.hide()
            return
        self.build()
        self.adjustSize()
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.move(QPoint(avail.center().x() - W // 2, avail.bottom() - self.height() - 12))
        self.show()
        x11.enable_blur(int(self.winId()), self.p.get("transparency", True))
        self.timer.start()

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
