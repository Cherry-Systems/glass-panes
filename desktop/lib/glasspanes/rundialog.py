"""The Run dialog (Win+R). Understands the usual Windows commands (notepad, cmd, control, regedit,
ms-settings:, taskmgr, %USERPROFILE%...) as well as Linux commands, paths, URLs and .exe files."""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PyQt6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QVBoxLayout)

from . import paths, style
from .widgets import ComboBox

HISTORY = os.path.join(paths.STATE, "run-history.json")

# Windows command -> what to run on Glass Panes
ALIASES = {
    "notepad": ["kwrite"], "notepad.exe": ["kwrite"],
    "cmd": ["konsole"], "cmd.exe": ["konsole"], "powershell": ["konsole"], "pwsh": ["konsole"],
    "wt": ["konsole"], "terminal": ["konsole"],
    "explorer": ["dolphin"], "explorer.exe": ["dolphin"],
    "control": ["systemsettings"], "control panel": ["systemsettings"],
    "taskmgr": ["glass-taskmgr"], "taskmgr.exe": ["glass-taskmgr"],
    "calc": ["kcalc"], "calc.exe": ["kcalc"],
    "mspaint": ["kolourpaint"], "mspaint.exe": ["kolourpaint"], "paint": ["kolourpaint"],
    "snippingtool": ["spectacle"], "write": ["kwrite"], "wordpad": ["kwrite"],
    "charmap": ["kcharselect"], "msinfo32": ["kinfocenter"], "devmgmt.msc": ["kinfocenter"],
    "diskmgmt.msc": ["partitionmanager"], "compmgmt.msc": ["kinfocenter"],
    "appwiz.cpl": ["glass-settings", "--page", "installedapps"], "ncpa.cpl": ["glass-settings", "--page", "network"],
    "desk.cpl": ["glass-settings", "--page", "display"], "mmsys.cpl": ["glass-settings", "--page", "sound"],
    "main.cpl": ["glass-settings", "--page", "mouse"], "timedate.cpl": ["glass-settings", "--page", "time_date"],
    "powercfg.cpl": ["glass-settings", "--page", "power"], "sysdm.cpl": ["glass-settings", "--page", "about"],
    "winver": ["glass-settings", "--winver"], "dxdiag": ["kinfocenter"],
    "regedit": ["wine", "regedit"], "regedit.exe": ["wine", "regedit"],
    "winecfg": ["winecfg"], "msconfig": ["glass-settings", "--page", "startup"],
    "services.msc": ["systemsettings"], "printmanagement.msc": ["glass-settings", "--page", "printers"],
    "osk": ["glass-settings", "--page", "accessibility"], "magnify": ["glass-settings", "--page", "accessibility"],
    "shutdown": ["glass-shell", "security"], "logoff": ["qdbus6", "org.kde.Shutdown", "/Shutdown", "logout"],
    "firefox": ["firefox-esr"], "msedge": ["firefox-esr"], "iexplore": ["firefox-esr"],
    "chrome": ["firefox-esr"], "store": ["plasma-discover"], "ms-windows-store:": ["plasma-discover"],
}

ENV_VARS = {
    "userprofile": "~", "homepath": "~", "appdata": "~/.wine/drive_c/users/{user}/AppData/Roaming",
    "localappdata": "~/.wine/drive_c/users/{user}/AppData/Local", "temp": "/tmp", "tmp": "/tmp",
    "programfiles": "~/.wine/drive_c/Program Files", "windir": "~/.wine/drive_c/windows",
    "systemroot": "~/.wine/drive_c/windows", "systemdrive": "~/.wine/drive_c", "public": "/home",
}


# Windows' ms-settings: page names -> Glass Panes Settings pages.
MS_SETTINGS = {
    "windowsupdate": "update", "windowsupdate-action": "update", "display": "display", "sound": "sound",
    "notifications": "notifications", "powersleep": "power", "batterysaver": "power", "storagesense": "storage",
    "multitasking": "multitasking", "about": "about", "bluetooth": "bluetooth", "connecteddevices": "bluetooth",
    "printers": "printers", "mousetouchpad": "mouse", "network": "network", "network-wifi": "network",
    "network-status": "network", "personalization": "personalisation", "personalization-background": "background",
    "colors": "colors", "lockscreen": "lockscreen", "taskbar": "taskbar", "personalization-start": "start",
    "appsfeatures": "installedapps", "defaultapps": "defaultapps", "startupapps": "startup",
    "yourinfo": "yourinfo", "signinoptions": "signin", "otherusers": "otherusers", "dateandtime": "time_date",
    "regionlanguage": "language", "easeofaccess": "accessibility", "privacy": "privacy", "home": "system",
}


def load_history():
    try:
        with open(HISTORY) as f:
            h = json.load(f)
        return [x for x in h if isinstance(x, str)][:26]
    except (OSError, ValueError):
        return []


def save_history(cmd):
    h = [cmd] + [x for x in load_history() if x != cmd]
    os.makedirs(paths.STATE, exist_ok=True)
    with open(HISTORY, "w") as f:
        json.dump(h[:26], f)


def expand(text):
    user = os.environ.get("USER", "user")

    def repl(m):
        v = ENV_VARS.get(m.group(1).lower())
        if v is None:
            return os.environ.get(m.group(1), m.group(0))
        return os.path.expanduser(v.format(user=user))
    text = re.sub(r"%([A-Za-z_]+)%", repl, text)
    m = re.match(r"^([A-Za-z]):[\\/]?(.*)$", text)
    if m:  # Windows drive path: C:\ is the Windows apps' drive
        rest = m.group(2).replace("\\", "/")
        if m.group(1).upper() == "C":
            return os.path.join(os.path.expanduser("~/.wine/drive_c"), rest)
    return os.path.expanduser(text)


def resolve(text):
    """Turns what the user typed into an action: ('argv', [...]) | ('open', path/url) | ('error', msg)."""
    raw = text.strip()
    if not raw:
        return ("error", "")
    low = raw.lower()
    if low.startswith("ms-settings:"):
        page = low.split(":", 1)[1].strip("/") or "system"
        page = MS_SETTINGS.get(page, MS_SETTINGS.get(page.split("-")[0], page.split("-")[0]))
        return ("argv", ["glass-settings", "--page", page])
    if low in ALIASES:
        return ("argv", ALIASES[low])
    if re.match(r"^(https?|ftp)://", low) or re.match(r"^www\.", low):
        return ("open", raw if "://" in raw else "https://" + raw)
    path = expand(raw)
    if os.path.exists(path):
        if path.lower().endswith((".exe", ".msi", ".bat", ".lnk")):
            return ("argv", ["glass-wine", path])
        return ("open", path)
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    if parts and parts[0].lower() in ALIASES:
        return ("argv", ALIASES[parts[0].lower()] + parts[1:])
    if parts and shutil.which(parts[0]):
        return ("argv", parts)
    return ("error", f"Glass Panes cannot find '{raw}'. Make sure you typed the name correctly, "
                     "and then try again.")


class RunDialog(QDialog):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Run")
        self.setWindowIcon(QIcon.fromTheme("system-run"))
        self.setFixedSize(400, 186)
        t = style.make_theme()
        self.t = t
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(14)
        ic = QLabel()
        ic.setPixmap(style.app_icon("system-run", 32).pixmap(32, 32))
        ic.setAlignment(Qt.AlignmentFlag.AlignTop)
        top.addWidget(ic)
        msg = QLabel("Type the name of a program, folder, document, or Internet resource, and "
                     "Glass Panes will open it for you.")
        msg.setWordWrap(True)
        top.addWidget(msg, 1)
        lay.addLayout(top)
        row = QHBoxLayout()
        row.addWidget(QLabel("Open:"))
        self.combo = ComboBox(t)
        self.combo.setEditable(True)
        self.combo.addItems(load_history())
        self.combo.setCurrentIndex(0 if self.combo.count() else -1)
        self.combo.lineEdit().selectAll()
        row.addWidget(self.combo, 1)
        lay.addLayout(row)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("OK")
        ok.setProperty("accent", "true")
        ok.setDefault(True)
        ok.clicked.connect(self.go)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        for b in (ok, cancel, browse):
            b.setMinimumWidth(84)
            buttons.addWidget(b)
        lay.addLayout(buttons)

    def place(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.left() + 12, screen.bottom() - self.height() - 48)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Browse", os.path.expanduser("~"),
                                              "Programs (*.exe *.msi *.desktop *.sh);;All files (*)")
        if path:
            self.combo.setEditText(f'"{path}"' if " " in path else path)

    def go(self):
        text = self.combo.currentText().strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        kind, value = resolve(text)
        if kind == "error":
            if value:
                QMessageBox.critical(self, text, value)
            return
        save_history(self.combo.currentText().strip())
        if kind == "open":
            QDesktopServices.openUrl(QUrl(value) if "://" in value else QUrl.fromLocalFile(value))
        else:
            try:
                subprocess.Popen(value, start_new_session=True, cwd=os.path.expanduser("~"))
            except OSError as e:
                QMessageBox.critical(self, text, str(e))
                return
        self.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("glass-run")
    app.setDesktopFileName("glass-run")
    style.apply_app_style(app)
    d = RunDialog()
    d.place()
    if "--screenshot" in sys.argv:
        from PyQt6.QtCore import QTimer
        d.show()
        QTimer.singleShot(500, lambda: (d.grab().save(sys.argv[sys.argv.index("--screenshot") + 1]), app.quit()))
        sys.exit(app.exec())
    d.exec()


if __name__ == "__main__":
    main()
