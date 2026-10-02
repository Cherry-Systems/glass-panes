"""Building blocks for Settings pages."""
import shutil
import subprocess
import threading

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from .. import style
from ..widgets import Card, ComboBox, SettingRow, ToggleSwitch, label


def run(*argv, timeout=20, text=True):
    """Runs a command and returns its stdout ('' on any failure)."""
    if not shutil.which(argv[0]):
        return ""
    try:
        return subprocess.run(list(argv), capture_output=True, text=text, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def ok(*argv, timeout=60):
    if not shutil.which(argv[0]):
        return False
    try:
        return subprocess.run(list(argv), capture_output=True, timeout=timeout).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def spawn(*argv):
    try:
        subprocess.Popen(list(argv), start_new_session=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def control_panel(module):
    """Opens a KDE settings module ('Control Panel') for the advanced options."""
    return spawn("systemsettings", module)


class Worker(QObject):
    """Runs `fn` in a thread and delivers its result on the GUI thread."""
    done = pyqtSignal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001 — shown to the user by the caller
            result = e
        self.done.emit(result)


def in_background(parent, fn, callback):
    w = Worker(fn, parent)
    w.done.connect(callback)
    parent._workers = getattr(parent, "_workers", []) + [w]
    return w.start()


class Page(QWidget):
    """A Settings page: breadcrumb title + scrolling column of cards."""
    title = ""
    parent_key = None  # set for sub-pages (System > Display)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.t = window.t
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(0, 0, 28, 28)
        self.body.setSpacing(4)
        scroll.setWidget(host)
        outer.addWidget(scroll)
        self.build()
        self.body.addStretch(1)

    def build(self):
        pass

    def refresh(self):
        """Called each time the page is shown."""

    # -- helpers ---------------------------------------------------------------
    def section(self, text):
        self.body.addWidget(label(text, "section"))

    def add(self, widget):
        self.body.addWidget(widget)
        return widget

    def row(self, icon, title, desc="", control=None, open_key=None, on_click=None):
        r = SettingRow(self.t, icon, title, desc, control, chevron=bool(open_key or on_click))
        if open_key:
            r.clicked.connect(lambda: self.window.open(open_key))
        elif on_click:
            r.clicked.connect(on_click)
        self.body.addWidget(r)
        return r

    def toggle(self, icon, title, desc, checked, on_change):
        sw = ToggleSwitch(self.t, checked)
        sw.toggled.connect(on_change)
        self.row(icon, title, desc, sw)
        return sw

    def combo(self, icon, title, desc, items, current, on_change):
        """items: list of (label, value)."""
        cb = ComboBox(self.t)
        for text, value in items:
            cb.addItem(text, value)
        idx = next((i for i, (_t, v) in enumerate(items) if v == current), -1)
        cb.setCurrentIndex(idx)
        cb.currentIndexChanged.connect(lambda i: i >= 0 and on_change(cb.itemData(i)))
        cb.setMinimumWidth(200)
        self.row(icon, title, desc, cb)
        return cb

    def button(self, text, cb, accent=False):
        b = QPushButton(text)
        if accent:
            b.setProperty("accent", "true")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(cb)
        return b

    def link_row(self, text, cb):
        b = QPushButton(text)
        b.setProperty("link", "true")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(cb)
        h = QHBoxLayout()
        h.setContentsMargins(4, 6, 0, 0)
        h.addWidget(b)
        h.addStretch(1)
        self.body.addLayout(h)
        return b

    def note(self, text):
        lb = label(text, "secondary", wrap=True)
        lb.setContentsMargins(4, 2, 4, 6)
        self.body.addWidget(lb)
        return lb

    def card(self):
        c = Card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        self.body.addWidget(c)
        return c, lay


class TaskDialog(QDialog):
    """Runs a long command (install/remove/update) showing progress and its output."""

    def __init__(self, parent, title, argv, done_text="Done"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(520, 300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        head = QLabel(title)
        head.setProperty("role", "subtitle")
        lay.addWidget(head)
        self.status = QLabel("Working on it…")
        self.status.setProperty("role", "secondary")
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        lay.addWidget(self.bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Cascadia Mono", 9))
        lay.addWidget(self.log, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.close_btn = QPushButton("Close")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.done_text = done_text
        self.returncode = None
        from PyQt6.QtCore import QProcess
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        QTimer.singleShot(0, lambda: self.proc.start(argv[0], argv[1:]))

    def _read(self):
        data = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        for line in data.splitlines():
            line = line.strip()
            if line:
                self.log.appendPlainText(line)
                self.status.setText(line[:90])

    def _finished(self, code, _status):
        self.returncode = code
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.status.setText(self.done_text if code == 0 else f"Something went wrong (error {code}).")
        self.close_btn.setEnabled(True)
        self.close_btn.setProperty("accent", "true")
        self.close_btn.style().polish(self.close_btn)


__all__ = ["Page", "TaskDialog", "run", "ok", "spawn", "control_panel", "in_background", "style",
           "ComboBox", "ToggleSwitch"]
