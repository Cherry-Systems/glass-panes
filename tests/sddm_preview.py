"""Renders the SDDM theme with mock sddm/userModel objects.

    QT_QPA_PLATFORM=offscreen build/venv/bin/python3 tests/sddm_preview.py OUT.png [signin] [PROP=VALUE ...]
"""
import os
import sys

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFontDatabase, QGuiApplication, QStandardItem, QStandardItemModel
from PyQt6.QtQuick import QQuickView

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
THEME = os.path.join(ROOT, "overlay/usr/share/sddm/themes/glasspanes")
ART = os.path.join(ROOT, "build/art/sddm")


class Sddm(QObject):
    loginFailed = pyqtSignal()
    loginSucceeded = pyqtSignal()

    @pyqtProperty(bool, constant=True)
    def canSuspend(self):
        return True

    @pyqtProperty(bool, constant=True)
    def canPowerOff(self):
        return True

    @pyqtProperty(bool, constant=True)
    def canReboot(self):
        return True

    @pyqtSlot(str, str, int)
    def login(self, user, password, session):
        print("login", user, password, session)
        QTimer.singleShot(100, self.loginFailed.emit)

    @pyqtSlot()
    def powerOff(self):
        pass

    @pyqtSlot()
    def reboot(self):
        pass

    @pyqtSlot()
    def suspend(self):
        pass


class Keyboard(QObject):
    @pyqtProperty(bool, constant=True)
    def capsLock(self):
        return False


class Users(QStandardItemModel):
    NAME, REAL, ICON = (Qt.ItemDataRole.UserRole + i for i in (1, 2, 3))

    def __init__(self, n):
        super().__init__()
        for name, real in [("isaiah", "Isaiah"), ("guest", "Guest")][:n]:
            it = QStandardItem()
            it.setData(name, self.NAME)
            it.setData(real, self.REAL)
            it.setData("file:///nonexistent.png", self.ICON)
            self.appendRow(it)

    def roleNames(self):
        return {self.NAME: b"name", self.REAL: b"realName", self.ICON: b"icon"}

    @pyqtProperty(int, constant=True)
    def lastIndex(self):
        return 0


class Sessions(QObject):
    @pyqtProperty(int, constant=True)
    def lastIndex(self):
        return 0


class Config(QObject):
    @pyqtProperty(str, constant=True)
    def background(self):
        return "file://" + os.path.join(ART, "background.png")

    @pyqtProperty(str, constant=True)
    def backgroundBlur(self):
        return "file://" + os.path.join(ART, "background-blur.png")

    @pyqtProperty(str, constant=True)
    def font(self):
        return "Selawik"


def main():
    app = QGuiApplication(sys.argv)
    for f in ("selawk.ttf", "selawksb.ttf"):
        p = os.path.join(ROOT, "build/cache/fonts", f)
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)
    view = QQuickView()
    objs = dict(sddm=Sddm(), keyboard=Keyboard(), userModel=Users(int(os.environ.get("USERS", "2"))),
                sessionModel=Sessions(), config=Config())
    for k, v in objs.items():
        view.rootContext().setContextProperty(k, v)
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.resize(1600, 900)
    view.setSource(QUrl.fromLocalFile(os.path.join(THEME, "Main.qml")))
    for e in view.errors():
        print("QML error:", e.toString())
    view.show()
    if "signin" in sys.argv:
        QTimer.singleShot(300, lambda: view.rootObject().showSignIn())
    # Extra arguments NAME=VALUE set properties on the theme, e.g. flyout=access magnify=true.
    for arg in sys.argv[2:]:
        if "=" in arg:
            name, value = arg.split("=", 1)
            value = {"true": True, "false": False}.get(value, value)
            QTimer.singleShot(400, lambda n=name, v=value: view.rootObject().setProperty(n, v))
    QTimer.singleShot(1500, lambda: (view.grabWindow().save(sys.argv[1]), app.quit()))
    app.exec()


if __name__ == "__main__":
    main()
