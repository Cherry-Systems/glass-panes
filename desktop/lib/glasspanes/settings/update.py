"""Glass Update: check for, download and install updates (system packages via PackageKit, Store apps
via Flatpak, then Cherry Store apps). Updates never restart the PC on their own."""
import os
import re
import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from .. import style
from ..widgets import Card, SettingRow, label
from .util import Page, TaskDialog, in_background, run, spawn

STAMP = os.path.expanduser("~/.local/state/glasspanes/last-update-check")


def check_updates():
    run("pkcon", "refresh", timeout=600)
    out = run("pkcon", "get-updates", "--plain", timeout=300)
    pkgs = []
    for line in out.splitlines():
        m = re.match(r"^\s*(Normal|Security|Bug fix|Enhancement|Important|Low)\s+(\S+)", line)
        if m:
            pkgs.append((m.group(1), m.group(2)))
    flat = run("flatpak", "remote-ls", "--updates", "--columns=name", timeout=120)
    apps = [x for x in flat.splitlines() if x.strip()]
    cherry = re.findall(r"^(\S+): \S+ → \S+$", run("cherry", "update", "--check", timeout=120), re.M)
    os.makedirs(os.path.dirname(STAMP), exist_ok=True)
    with open(STAMP, "w") as f:
        f.write(str(time.time()))
    return pkgs, apps, cherry


def updates_count(n, what):
    return f"{n} {what} update{'' if n == 1 else 's'}"


def last_checked():
    try:
        with open(STAMP) as f:
            t = float(f.read())
        return time.strftime("Last checked: today, %-I:%M %p" if time.time() - t < 86400
                             else "Last checked: %-d %B, %-I:%M %p", time.localtime(t))
    except (OSError, ValueError):
        return "Check for updates to keep Glass Panes secure"


class UpdatePage(Page):
    title = "Glass Update"

    def build(self):
        hero = Card()
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(20, 18, 20, 18)
        hl.setSpacing(18)
        self.icon = QLabel()
        self.icon.setFixedSize(56, 56)
        hl.addWidget(self.icon)
        col = QVBoxLayout()
        self.headline = QLabel("You're up to date")
        self.headline.setFont(style.font(15, QFont.Weight.DemiBold))
        col.addWidget(self.headline)
        self.sub = label(last_checked(), "secondary", wrap=True)
        col.addWidget(self.sub)
        hl.addLayout(col, 1)
        self.action = self.button("Check for updates", self.check, accent=True)
        hl.addWidget(self.action, 0, Qt.AlignmentFlag.AlignTop)
        self.add(hero)
        self.set_icon("checkmark_circle", "#0f7b0f")
        self.list_host = QVBoxLayout()
        self.body.addLayout(self.list_host)
        self.section("More options")
        self.row("history", "Update history", "Recently installed updates", on_click=self.history)
        self.row("arrow_download", "Store app updates", "Update apps you got from the Store",
                 on_click=lambda: spawn("plasma-discover", "--mode", "update"))
        self.note("Glass Panes never restarts your PC to install updates. If an update needs a restart, "
                  "you'll be asked, and it happens when you choose.")
        self.pending = ([], [], [])

    def set_icon(self, name, color):
        self.icon.setPixmap(style.icon_pixmap(name, color, 56, 2.0))

    def check(self):
        self.action.setEnabled(False)
        self.headline.setText("Checking for updates…")
        self.sub.setText("This might take a few minutes.")
        self.set_icon("arrow_sync_circle", self.t.accent_fill)
        in_background(self, check_updates, self.checked)

    def checked(self, result):
        self.action.setEnabled(True)
        while self.list_host.count():
            w = self.list_host.takeAt(0).widget()
            if w:
                w.deleteLater()
        if isinstance(result, Exception):
            self.headline.setText("We couldn't check for updates")
            self.sub.setText("Make sure you're connected to the internet, then try again.")
            self.set_icon("status", "#c42b1c")
            return
        pkgs, apps, cherry = result
        self.pending = result
        if not pkgs and not apps and not cherry:
            self.headline.setText("You're up to date")
            self.sub.setText(last_checked())
            self.set_icon("checkmark_circle", "#0f7b0f")
            self.action.setText("Check for updates")
            self.action.clicked.disconnect()
            self.action.clicked.connect(self.check)
            return
        sec = sum(1 for k, _ in pkgs if k == "Security")
        self.headline.setText("Updates available")
        counts = [(pkgs, "system", f" ({sec} security)" if sec else ""),
                  (apps, "Store app", ""), (cherry, "Cherry Store app", "")]
        self.sub.setText(", ".join(updates_count(len(items), what) + extra for items, what, extra in counts if items))
        self.set_icon("arrow_download", self.t.accent_fill)
        self.action.setText("Download && install all")
        self.action.clicked.disconnect()
        self.action.clicked.connect(self.install)
        for kind, pid in pkgs[:30]:
            name = pid.split(";")[0]
            self.list_host.addWidget(SettingRow(self.t, "arrow_download", name, f"{kind} update"))
        if len(pkgs) > 30:
            self.list_host.addWidget(label(f"…and {len(pkgs) - 30} more", "secondary"))
        for name in cherry:
            self.list_host.addWidget(SettingRow(self.t, "arrow_download", name, "Cherry Store app update"))

    def install(self):
        pkgs, apps, _ = self.pending
        if pkgs:
            d = TaskDialog(self, "Installing updates", ["pkcon", "update", "-y", "--plain"],
                           "Updates installed.")
            d.exec()
        if apps:
            TaskDialog(self, "Updating Store apps", ["flatpak", "update", "-y", "--noninteractive"],
                       "Store apps updated.").exec()
        TaskDialog(self, "Updating Cherry Store apps", ["cherry", "update", "-y"],
                   "Cherry Store apps updated.").exec()
        if os.path.exists("/run/reboot-required") or os.path.exists("/var/run/reboot-required"):
            self.headline.setText("Restart required")
            self.sub.setText("Restart your PC whenever it suits you to finish installing updates.")
            self.set_icon("arrow_clockwise", self.t.accent_fill)
        else:
            self.check()

    def history(self):
        entries = []
        try:
            with open("/var/log/apt/history.log") as f:
                block = {}
                for line in f:
                    if line.startswith("Start-Date:"):
                        block = {"date": line.split(":", 1)[1].strip()}
                    elif line.startswith(("Upgrade:", "Install:")):
                        block["what"] = line.split(":", 1)[1].strip()
                    elif line.startswith("End-Date:") and "what" in block:
                        entries.append(block)
        except OSError:
            pass
        while self.list_host.count():
            w = self.list_host.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.list_host.addWidget(label("Update history", "section"))
        if not entries:
            self.list_host.addWidget(label("No updates have been installed yet.", "secondary"))
        for e in entries[-15:][::-1]:
            pk = [p.split(":")[0] for p in re.split(r"\),\s*", e["what"])][:6]
            self.list_host.addWidget(SettingRow(self.t, "checkmark", ", ".join(pk), e["date"]))


PAGES = {"update": UpdatePage}
