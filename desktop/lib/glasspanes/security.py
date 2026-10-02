"""The Ctrl+Alt+Del screen: Lock, Switch user, Sign out, Change a password, Task Manager, power."""
import subprocess

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from . import prefs, session, style


def blurred(path, size):
    img = QImage(path)
    if img.isNull():
        px = QPixmap(size)
        px.fill(QColor("#0b2a4a"))
        return px
    small = img.scaled(max(1, size.width() // 24), max(1, size.height() // 24),
                       Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    big = small.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    px = QPixmap.fromImage(big)
    p = QPainter(px)
    p.fillRect(px.rect(), QColor(0, 0, 0, 110))
    p.end()
    return px


class SecurityScreen(QWidget):
    def __init__(self):
        # A normal window: KWin keeps panels above fullscreen utility (Qt Tool) windows.
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Security options")
        geo = QGuiApplication.primaryScreen().geometry()
        for s in QGuiApplication.screens():
            geo = geo.united(s.geometry())
        self.setGeometry(geo)
        self.bg = blurred(prefs.wallpaper(), geo.size())
        self.t = style.make_theme("dark")
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(6)
        items = [("Lock", session.lock), ("Switch user", session.switch_user),
                 ("Sign out", session.sign_out), ("Change a password", self.change_password),
                 ("Task Manager", lambda: subprocess.Popen(["glass-taskmgr"], start_new_session=True))]
        for text, cb in items:
            b = QPushButton(text)
            b.setFont(style.font(14))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton { color: white; background: transparent; border: none;"
                            " padding: 6px 12px; text-align: left; }"
                            "QPushButton:hover { background: rgba(255,255,255,0.12); border-radius: 4px; }")
            b.clicked.connect(lambda _=False, c=cb: (self.close(), c()))
            col.addWidget(b)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addLayout(col)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(32 + 3 * 44, 0, 32, 32)  # balances the three icons so Cancel is centred
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setFixedSize(120, 34)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet("QPushButton { color: white; background: rgba(255,255,255,0.12);"
                             " border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; }"
                             "QPushButton:hover { background: rgba(255,255,255,0.2); }")
        cancel.clicked.connect(self.close)
        bottom.addWidget(cancel)
        bottom.addStretch(1)
        for name, cb in (("globe", lambda: (self.close(), subprocess.Popen(["glass-settings", "--page", "network"]))),
                         ("accessibility", lambda: (self.close(), subprocess.Popen(["glass-settings", "--page", "accessibility"]))),
                         ("power", None)):
            b = QPushButton()
            b.setIcon(style.icon(name, "#ffffff", 20))
            b.setFixedSize(44, 44)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton { background: transparent; border: none; border-radius: 4px; }"
                            "QPushButton:hover { background: rgba(255,255,255,0.12); }")
            if cb:
                b.clicked.connect(cb)
            else:
                b.clicked.connect(lambda _=False, w=b: self.power_menu(w))
            bottom.addWidget(b)
        lay.addLayout(bottom)

    def power_menu(self, w):
        m = QMenu(self)
        m.setStyleSheet(style.stylesheet(self.t))
        m.addAction("Sleep", lambda: (self.close(), session.sleep()))
        m.addAction("Shut down", lambda: (self.close(), session.shut_down()))
        m.addAction("Restart", lambda: (self.close(), session.restart()))
        m.exec(w.mapToGlobal(QPoint(0, -m.sizeHint().height() - 4)))

    def change_password(self):
        subprocess.Popen(["glass-settings", "--page", "accounts", "--change-password"],
                         start_new_session=True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(0, 0, self.bg)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def showEvent(self, e):
        super().showEvent(e)
        self.activateWindow()
        self.raise_()
        self.setFocus()
