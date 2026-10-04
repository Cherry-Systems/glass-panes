"""The 'Shut Down Glass Panes' box that Alt+F4 opens on the desktop, as on Windows."""
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from . import session, style
from .widgets import ComboBox, label

CHOICES = [
    ("Switch user", session.switch_user, "Leave your apps open and let someone else sign in."),
    ("Sign out", session.sign_out, "Close all apps and sign out."),
    ("Sleep", session.sleep, "The PC stays on but uses low power. Apps stay open so when the PC "
                             "wakes up, you're instantly back to where you left off."),
    ("Shut down", session.shut_down, "Close all apps and turn off the PC."),
    ("Restart", session.restart, "Close all apps, turn off the PC and then turn it on again."),
]


class ShutDownDialog(QDialog):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
                         | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("Shut Down Glass Panes")
        self.setWindowIcon(QIcon.fromTheme("system-shutdown"))
        self.setFixedSize(420, 230)
        t = style.make_theme()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(style.app_icon("glasspanes-logo", 40).pixmap(40, 40))
        top.addWidget(logo)
        name = QLabel("Glass Panes")
        name.setStyleSheet("font-size: 18pt; font-weight: 600;")
        top.addWidget(name)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(QLabel("What do you want the computer to do?"))
        self.combo = ComboBox(t)
        for name, _action, _desc in CHOICES:
            self.combo.addItem(name)
        self.combo.setCurrentText("Shut down")
        lay.addWidget(self.combo)
        self.desc = label("", "secondary", wrap=True)
        lay.addWidget(self.desc, 1)
        self.combo.currentIndexChanged.connect(lambda i: self.desc.setText(CHOICES[i][2]))
        self.desc.setText(CHOICES[self.combo.currentIndex()][2])
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("OK")
        ok.setProperty("accent", "true")
        ok.setDefault(True)
        ok.clicked.connect(self.go)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        for b in (ok, cancel):
            b.setMinimumWidth(84)
            buttons.addWidget(b)
        lay.addLayout(buttons)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    def go(self):
        action = CHOICES[self.combo.currentIndex()][1]
        self.accept()
        action()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("glass-shutdown")
    style.apply_app_style(app)
    d = ShutDownDialog()
    if "--screenshot" in sys.argv:
        from PyQt6.QtCore import QTimer
        d.show()
        QTimer.singleShot(500, lambda: (d.grab().save(sys.argv[sys.argv.index("--screenshot") + 1]), app.quit()))
        sys.exit(app.exec())
    d.exec()


if __name__ == "__main__":
    main()
