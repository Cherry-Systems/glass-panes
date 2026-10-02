"""The Settings window: account card, 'Find a setting', category navigation, breadcrumb pages."""
import sys

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (QApplication, QCompleter, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                             QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import prefs, session, settings_index, style
from ..start import circle_pixmap
from ..widgets import Card, NavList

CATEGORIES = [
    # key, title, icon, colour
    ("system", "System", "desktop", "#0078d4"),
    ("bluetooth", "Bluetooth & devices", "bluetooth", "#0078d4"),
    ("network", "Network & internet", "wifi_1", "#4c84c4"),
    ("personalisation", "Personalisation", "paint_brush", "#e3792e"),
    ("apps", "Apps", "apps_list", "#6b6b8b"),
    ("accounts", "Accounts", "person_circle", "#2f9e5b"),
    ("time", "Time & language", "globe", "#2b88d8"),
    ("accessibility", "Accessibility", "accessibility", "#2b88d8"),
    ("privacy", "Privacy & security", "shield", "#6f7a86"),
    ("update", "Glass Update", "arrow_sync_circle", "#0078d4"),
]


def page_classes():
    from . import accounts, apps_page, devices, network, personal, system, time_lang, update, access, privacy
    classes = {}
    for mod in (system, devices, network, personal, apps_page, accounts, time_lang, access, privacy, update):
        classes.update(mod.PAGES)
    return classes


class SettingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.t = style.make_theme()
        self.setWindowTitle("Settings")
        self.setWindowIcon(QIcon.fromTheme("preferences-system"))
        self.resize(1120, 760)
        self.setMinimumSize(760, 520)
        self.classes = page_classes()
        self.pages = {}
        self.history = []
        self.current = None

        root = QWidget()
        root.setObjectName("Window")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget()
        side.setFixedWidth(300)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 12, 12, 12)
        sl.setSpacing(6)
        back = QPushButton()
        back.setIcon(style.icon("arrow_left", self.t.text, 16))
        back.setFixedSize(40, 32)
        back.setProperty("flat", "true")
        back.setToolTip("Back")
        back.clicked.connect(self.go_back)
        self.back_btn = back
        sl.addWidget(back)

        user = Card(clickable=True)
        user.setProperty("role", "navuser")
        user.setStyleSheet(f"QFrame[role=navuser] {{ background: transparent; border-radius: 6px; }}"
                           f"QFrame[role=navuser]:hover {{ background: {self.t.subtle_hover}; }}")
        ul = QHBoxLayout(user)
        ul.setContentsMargins(8, 8, 8, 8)
        ul.setSpacing(14)
        pic = QLabel()
        pic.setPixmap(circle_pixmap(session.user_picture(), 64))
        pic.setFixedSize(64, 64)
        ul.addWidget(pic)
        names = QVBoxLayout()
        names.setSpacing(0)
        n = QLabel(session.user_name())
        n.setFont(style.font(11, QFont.Weight.DemiBold))
        names.addWidget(n)
        acct = QLabel("Local Account")
        acct.setProperty("role", "secondary")
        names.addWidget(acct)
        ul.addLayout(names, 1)
        user.setFixedHeight(84)
        user.clicked.connect(lambda: self.open("accounts", reset=True))
        sl.addWidget(user)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a setting")
        self.search.setFixedHeight(34)
        self.search.setTextMargins(0, 0, 26, 0)
        self.search.addAction(style.icon("search", self.t.text_secondary, 14),
                              QLineEdit.ActionPosition.TrailingPosition)
        titles = [e[0] for e in settings_index.ENTRIES]
        comp = QCompleter(titles, self)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        comp.popup().setStyleSheet(style.stylesheet(self.t))
        comp.activated.connect(self.find_setting)
        self.search.setCompleter(comp)
        self.search.returnPressed.connect(lambda: self.find_setting(self.search.text()))
        sl.addWidget(self.search)
        sl.addSpacing(4)

        self.nav = NavList(self.t)
        for key, title, icon, color in CATEGORIES:
            self.nav.add(title, icon, key, color)
        self.nav.currentItemChanged.connect(self.nav_changed)
        sl.addWidget(self.nav, 1)
        lay.addWidget(side)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(28, 22, 0, 0)
        ml.setSpacing(14)
        self.crumb = QHBoxLayout()
        self.crumb.setSpacing(10)
        ml.addLayout(self.crumb)
        self.stack = QStackedWidget()
        ml.addWidget(self.stack, 1)
        lay.addWidget(main, 1)

    # -- navigation --------------------------------------------------------------
    def nav_changed(self, item, _prev):
        if item is not None and not getattr(self, "_syncing", False):
            self.open(item.data(Qt.ItemDataRole.UserRole), reset=True)

    def category_of(self, key):
        cls = self.classes.get(key)
        while cls is not None and cls.parent_key:
            key = cls.parent_key
            cls = self.classes.get(key)
        return key

    def open(self, key, reset=False):
        if key not in self.classes:
            key = "system"
        if self.current and not reset:
            self.history.append(self.current)
        elif reset:
            self.history = []
        self.current = key
        if key not in self.pages:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                page = self.classes[key](self)
            finally:
                QApplication.restoreOverrideCursor()
            self.pages[key] = page
            self.stack.addWidget(page)
        page = self.pages[key]
        page.refresh()
        self.stack.setCurrentWidget(page)
        self.set_crumbs(key)
        cat = self.category_of(key)
        self._syncing = True
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.ItemDataRole.UserRole) == cat:
                self.nav.setCurrentRow(i)
        self._syncing = False
        self.back_btn.setEnabled(bool(self.history))

    def go_back(self):
        if self.history:
            key = self.history.pop()
            self.current = None
            self.open(key)
            self.history.pop() if self.history and self.history[-1] == key else None

    def set_crumbs(self, key):
        while self.crumb.count():
            w = self.crumb.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        chain = []
        k = key
        while k:
            cls = self.classes[k]
            chain.insert(0, (k, cls.title))
            k = cls.parent_key
        for i, (k, title) in enumerate(chain):
            last = i == len(chain) - 1
            if last:
                lb = QLabel(title)
                lb.setProperty("role", "title")
                self.crumb.addWidget(lb)
            else:
                b = QPushButton(title)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(f"QPushButton {{ font-size: 21pt; font-weight: 600; border: none;"
                                f" background: transparent; color: {self.t.text_secondary}; padding: 0; }}"
                                f"QPushButton:hover {{ color: {self.t.text}; }}")
                b.clicked.connect(lambda _=False, kk=k: self.open(kk, reset=True))
                self.crumb.addWidget(b)
                arrow = QLabel()
                arrow.setPixmap(style.icon_pixmap("chevron_right", self.t.text_secondary, 16, 2.0))
                self.crumb.addWidget(arrow)
        self.crumb.addStretch(1)

    def restyle(self):
        """Re-themes the window after the mode or accent colour changes."""
        self.t = style.make_theme()
        style.apply_app_style(QApplication.instance(), self.t)
        self.nav.itemDelegate().t = self.t
        self.nav.viewport().update()
        current = self.current
        for page in self.pages.values():
            self.stack.removeWidget(page)
            page.deleteLater()
        self.pages = {}
        self.current = None
        self.open(current or "system", reset=True)

    def find_setting(self, text):
        hits = settings_index.search(text, 1)
        if hits:
            self.open(hits[0][1], reset=True)
            QTimer.singleShot(0, self.search.clear)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("glass-settings")
    app.setApplicationDisplayName("Settings")
    app.setDesktopFileName("glass-settings")
    style.apply_app_style(app)
    if "--winver" in argv:
        from .system import show_winver
        show_winver()
        return 0
    w = SettingsWindow()
    page = argv[argv.index("--page") + 1] if "--page" in argv else "system"
    if "--uninstall" in argv:
        page = "installedapps"
    w.open(page, reset=True)
    w.show()
    if "--uninstall" in argv:
        did = argv[argv.index("--uninstall") + 1]
        QTimer.singleShot(300, lambda: w.pages["installedapps"].uninstall_desktop_id(did))
    if "--change-password" in argv:
        QTimer.singleShot(300, lambda: w.pages["accounts"].change_password())
    if "--screenshot" in argv:
        out = argv[argv.index("--screenshot") + 1]
        QTimer.singleShot(1500, lambda: (w.grab().save(out), app.quit()))
    return app.exec()
