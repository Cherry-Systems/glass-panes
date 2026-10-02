"""glass-shell: the always-running helper behind the Windows key, Start, Win+R, Win+X and
Ctrl+Alt+Del. Keeps Start loaded so it opens instantly, and listens on D-Bus (org.glasspanes.Shell)."""
import os
import subprocess
import sys

from PyQt6.QtCore import QFileSystemWatcher, QObject, QPoint, QTimer, pyqtClassInfo, pyqtSlot
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection
from PyQt6.QtGui import QCursor, QGuiApplication
from PyQt6.QtWidgets import QApplication, QMenu

from . import prefs, session, style

SERVICE = "org.glasspanes.Shell"


@pyqtClassInfo("D-Bus Interface", SERVICE)
class Adaptor(QDBusAbstractAdaptor):
    def __init__(self, shell):
        super().__init__(shell)
        self.shell = shell

    @pyqtSlot()
    def ToggleStart(self):  # noqa: N802 (D-Bus naming)
        self.shell.toggle_start()

    @pyqtSlot()
    def ShowSearch(self):  # noqa: N802
        self.shell.show_search()

    @pyqtSlot()
    def Run(self):  # noqa: N802
        self.shell.show_run()

    @pyqtSlot()
    def Security(self):  # noqa: N802
        self.shell.show_security()

    @pyqtSlot()
    def PowerUserMenu(self):  # noqa: N802
        self.shell.power_user_menu()

    @pyqtSlot()
    def Reload(self):  # noqa: N802
        self.shell.reload()


class Shell(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._start = None
        self._run = None
        self._security = None
        self.adaptor = Adaptor(self)
        self.watcher = QFileSystemWatcher([prefs.FILE] if os.path.exists(prefs.FILE) else [])
        self.watcher.fileChanged.connect(lambda _p: QTimer.singleShot(200, self.reload))

    @property
    def start(self):
        if self._start is None:
            from .start import StartMenu
            self._start = StartMenu()
        return self._start

    def reload(self):
        style.apply_app_style(self.app)
        if self._start is not None and not self._start.isVisible():
            self._start.build()
        if os.path.exists(prefs.FILE) and prefs.FILE not in self.watcher.files():
            self.watcher.addPath(prefs.FILE)

    def toggle_start(self):
        self.start.toggle()

    def show_search(self):
        if self.start.isVisible():
            self.start.hide_menu()
        else:
            self.start.show_menu()

    def show_run(self):
        from .rundialog import RunDialog
        if self._run is not None and self._run.isVisible():
            self._run.activateWindow()
            return
        self._run = RunDialog()
        self._run.place()
        self._run.show()
        self._run.activateWindow()

    def show_security(self):
        from .security import SecurityScreen
        if self._security is not None and self._security.isVisible():
            return
        self._security = SecurityScreen()
        self._security.show()

    def power_user_menu(self):
        """Win+X: the 'power user' menu Windows shows by the Start button."""
        t = style.make_theme()
        m = QMenu()
        m.setStyleSheet(style.stylesheet(t))

        def run(*argv):
            return lambda: subprocess.Popen(list(argv), start_new_session=True)
        entries = [
            ("Installed apps", run("glass-settings", "--page", "installedapps")),
            ("Power Options", run("glass-settings", "--page", "power")),
            ("System", run("glass-settings", "--page", "about")),
            ("Device Manager", run("kinfocenter")),
            ("Network Connections", run("glass-settings", "--page", "network")),
            ("Disk Management", run("partitionmanager")),
            None,
            ("Terminal", run("konsole")),
            ("Terminal (Admin)", run("konsole", "-e", "sudo", "-i")),
            None,
            ("Task Manager", run("glass-taskmgr")),
            ("Settings", run("glass-settings")),
            ("File Explorer", run("dolphin")),
            ("Search", self.show_search),
            ("Run", self.show_run),
            None,
        ]
        for e in entries:
            if e is None:
                m.addSeparator()
            else:
                m.addAction(e[0], e[1])
        sub = m.addMenu("Shut down or sign out")
        sub.setStyleSheet(style.stylesheet(t))
        sub.addAction("Sign out", session.sign_out)
        sub.addAction("Sleep", session.sleep)
        sub.addAction("Shut down", session.shut_down)
        sub.addAction("Restart", session.restart)
        m.addAction("Desktop", lambda: subprocess.Popen(
            ["qdbus6", "org.kde.kglobalaccel", "/component/kwin", "invokeShortcut", "Show Desktop"]))
        avail = QGuiApplication.primaryScreen().availableGeometry()
        size = m.sizeHint()
        if prefs.load().get("taskbar_align") == "left":
            pos = QPoint(avail.left() + 8, avail.bottom() - size.height() - 4)
        else:
            pos = QPoint(avail.center().x() - 140, avail.bottom() - size.height() - 4)
        if "--at-cursor" in sys.argv:
            pos = QCursor.pos()
        m.exec(pos)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("glass-shell")
    app.setQuitOnLastWindowClosed(False)
    style.apply_app_style(app)
    bus = QDBusConnection.sessionBus()
    shell = Shell(app)
    if not bus.registerService(SERVICE):
        print("glass-shell is already running", file=sys.stderr)
        return 0
    bus.registerObject("/Shell", shell)
    # Build Start in the background so the first press of the Windows key is instant.
    QTimer.singleShot(1500, lambda: shell.start)
    then = sys.argv[sys.argv.index("--then") + 1] if "--then" in sys.argv else None
    if then:
        QTimer.singleShot(0, getattr(shell.adaptor, then))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
