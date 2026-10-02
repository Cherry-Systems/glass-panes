"""Privacy & security: what Glass Panes does (and doesn't) collect, app permissions, security."""
from .. import prefs
from ..widgets import label
from .util import Page, control_panel, spawn


class PrivacyPage(Page):
    title = "Privacy & security"

    def build(self):
        c, lay = self.card()
        lay.addWidget(label("Your device is protected", "subtitle"))
        lay.addWidget(label("Glass Panes is built on Linux. Windows viruses and most Windows malware can't "
                            "harm it, apps from the Store are checked and sandboxed, and updates come "
                            "straight from Debian's security team.", "secondary", wrap=True))
        self.section("Security")
        self.row("arrow_sync_circle", "Glass Update", "Security updates for your system and apps",
                 open_key="update")
        self.row("lock_closed", "Screen lock", "Lock your PC when you step away",
                 on_click=lambda: control_panel("kcm_screenlocker"))
        self.section("Glass Panes permissions")
        self.row("eye", "Diagnostics & feedback",
                 "Glass Panes never sends diagnostic data, advertising IDs or usage history anywhere")
        p = prefs.load()
        self.toggle("history", "Show recently opened items in Start", "Stored only on this PC",
                    p.get("show_recommended", True), lambda on: prefs.update(show_recommended=on))
        self.row("search", "Searching Glass Panes", "Start searches your apps, settings and files on this PC; "
                 "only 'See web results' goes online")
        self.section("App permissions")
        self.row("location", "Location", "No apps can use your location unless you allow it in the app")
        self.row("camera", "Camera and microphone", "Store apps ask before using them",
                 on_click=lambda: spawn("plasma-discover", "--mode", "installed"))
        self.row("shield", "App permissions for Store apps", "Files, devices and network access",
                 on_click=lambda: control_panel("kcm_flatpak"))


PAGES = {"privacy": PrivacyPage}
