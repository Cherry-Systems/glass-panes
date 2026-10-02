"""Accounts: your info (name, picture), sign-in options (password), other users."""
import grp
import os
import pwd
import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QVBoxLayout)

from .. import session, style
from ..start import circle_pixmap
from ..widgets import Card, SettingRow, label
from .util import Page, control_panel, ok, run


def is_admin():
    try:
        name = session.login_name()
        return any(name in g.gr_mem for g in grp.getgrall() if g.gr_name in ("sudo", "wheel"))
    except KeyError:
        return False


def accounts_call(method, *args):
    """Calls org.freedesktop.Accounts.User.<method> for the current user."""
    path = run("busctl", "--system", "call", "org.freedesktop.Accounts", "/org/freedesktop/Accounts",
               "org.freedesktop.Accounts", "FindUserById", "x", str(os.getuid()), timeout=10).split()
    if len(path) < 2:
        return False
    obj = path[1].strip('"')
    sig = "s" * len(args)
    return ok("busctl", "--system", "call", "org.freedesktop.Accounts", obj,
              "org.freedesktop.Accounts.User", method, sig, *args, timeout=60)


class AccountsPage(Page):
    title = "Accounts"

    def build(self):
        hero = Card()
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(20, 18, 20, 18)
        hl.setSpacing(20)
        self.pic = QLabel()
        self.pic.setFixedSize(96, 96)
        hl.addWidget(self.pic)
        col = QVBoxLayout()
        self.name = QLabel()
        self.name.setFont(style.font(15, QFont.Weight.DemiBold))
        col.addWidget(self.name)
        col.addWidget(label("Local account", "secondary"))
        col.addWidget(label("Administrator" if is_admin() else "Standard user", "secondary"))
        col.addStretch(1)
        hl.addLayout(col, 1)
        self.add(hero)
        self.section("Account settings")
        self.row("person_circle", "Your info", "Profile photo, name", open_key="yourinfo")
        self.row("lock_closed", "Sign-in options", "Password, automatic sign-in", open_key="signin")
        self.row("people", "Other users", "Device access, work or school users, kiosk", open_key="otherusers")

    def refresh(self):
        self.pic.setPixmap(circle_pixmap(session.user_picture(), 96))
        self.name.setText(session.user_name())

    def change_password(self):
        self.window.open("signin")
        self.window.pages["signin"].change_password()


class YourInfoPage(Page):
    title = "Your info"
    parent_key = "accounts"

    def build(self):
        self.pic = QLabel()
        self.pic.setFixedSize(192, 192)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(self.pic)
        h.addStretch(1)
        self.body.addLayout(h)
        self.name = QLabel()
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setFont(style.font(15, QFont.Weight.DemiBold))
        self.body.addWidget(self.name)
        self.body.addSpacing(10)
        self.row("image", "Choose a photo", "", self.button("Browse files", self.choose_photo))
        self.row("edit", "Change your name", "", self.button("Change", self.change_name))

    def refresh(self):
        self.pic.setPixmap(circle_pixmap(session.user_picture(), 192))
        self.name.setText(session.user_name())

    def choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a photo", os.path.expanduser("~/Pictures"),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        from PyQt6.QtGui import QImage
        img = QImage(path)
        if img.isNull():
            return
        side = min(img.width(), img.height())
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side).scaled(
            256, 256, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        face = os.path.expanduser("~/.face.icon")
        img.save(face, "PNG")
        shutil.copy2(face, os.path.expanduser("~/.face"))
        accounts_call("SetIconFile", face)
        self.refresh()
        self.window.pages.get("accounts") and self.window.pages["accounts"].refresh()

    def change_name(self):
        name, accepted = QInputDialog.getText(self, "Change your name", "Name", text=session.user_name())
        if accepted and name.strip():
            if not accounts_call("SetRealName", name.strip()):
                ok("chfn", "-f", name.strip())
            self.refresh()


class PasswordDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Change your password")
        self.setFixedWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(8)
        t = QLabel("Change your password")
        t.setProperty("role", "subtitle")
        lay.addWidget(t)
        self.current = QLineEdit()
        self.current.setPlaceholderText("Current password")
        self.new = QLineEdit()
        self.new.setPlaceholderText("New password")
        self.again = QLineEdit()
        self.again.setPlaceholderText("Confirm password")
        for e in (self.current, self.new, self.again):
            e.setEchoMode(QLineEdit.EchoMode.Password)
            lay.addWidget(e)
        self.error = label("", "secondary", wrap=True)
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch(1)
        go = QPushButton("Next")
        go.setProperty("accent", "true")
        go.clicked.connect(self.change)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(go)
        row.addWidget(cancel)
        lay.addLayout(row)

    def change(self):
        if self.new.text() != self.again.text():
            self.error.setText("The passwords don't match.")
            return
        if len(self.new.text()) < 4:
            self.error.setText("Use at least 4 characters.")
            return
        import subprocess
        proc = subprocess.run(["passwd"], input=f"{self.current.text()}\n{self.new.text()}\n{self.new.text()}\n",
                              capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            QMessageBox.information(self, "Password", "Your password has been changed.")
            self.accept()
        else:
            self.error.setText("The current password is incorrect, or the new one is too simple.")


class SignInPage(Page):
    title = "Sign-in options"
    parent_key = "accounts"

    def build(self):
        self.row("lock_closed", "Password", "Sign in with your account's password",
                 self.button("Change", self.change_password))
        self.row("person", "Automatic sign-in", "Sign in without a password when this PC starts",
                 on_click=lambda: control_panel("kcm_sddm"))
        self.row("options", "Lock screen settings", "Lock when idle, require password after waking",
                 on_click=lambda: control_panel("kcm_screenlocker"))

    def change_password(self):
        PasswordDialog(self).exec()


class OtherUsersPage(Page):
    title = "Other users"
    parent_key = "accounts"

    def build(self):
        c, lay = self.card()
        row = QHBoxLayout()
        row.addWidget(label("Add other user"))
        row.addStretch(1)
        row.addWidget(self.button("Add account", lambda: control_panel("kcm_users"), accent=True))
        lay.addLayout(row)
        me = session.login_name()
        for p in pwd.getpwall():
            if 1000 <= p.pw_uid < 60000 and p.pw_name != me and os.path.isdir(p.pw_dir):
                self.add(SettingRow(self.t, "person", p.pw_gecos.split(",")[0] or p.pw_name, "Local account",
                                    self.button("Manage", lambda: control_panel("kcm_users"))))


PAGES = {"accounts": AccountsPage, "yourinfo": YourInfoPage, "signin": SignInPage,
         "otherusers": OtherUsersPage}
