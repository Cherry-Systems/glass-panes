"""Time & language: date & time (time zone, automatic time), language & region, typing."""
import datetime
import os

from PyQt6.QtCore import QLocale, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

from .. import style
from ..widgets import label
from .util import Page, control_panel, in_background, ok, run, spawn


def timedate():
    info = {}
    for line in run("timedatectl", "show", timeout=5).splitlines():
        k, _, v = line.partition("=")
        info[k] = v
    return info


class TimeLangPage(Page):
    title = "Time & language"

    def build(self):
        c, lay = self.card()
        self.clock = QLabel()
        self.clock.setFont(style.font(26, QFont.Weight.DemiBold))
        lay.addWidget(self.clock)
        self.date = label("", "secondary")
        lay.addWidget(self.date)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.row("clock", "Date & time", "Time zones, automatic clock settings, calendar display",
                 open_key="time_date")
        self.row("local_language", "Language & region", "Glass Panes and some apps format dates and time "
                 "based on your region", open_key="language")
        self.row("keyboard", "Typing", "Keyboard layouts, autocorrect",
                 on_click=lambda: control_panel("kcm_keyboard"))

    def tick(self):
        now = datetime.datetime.now()
        self.clock.setText(now.strftime("%-I:%M %p"))
        self.date.setText(now.strftime("%A, %-d %B %Y"))


class DateTimePage(Page):
    title = "Date & time"
    parent_key = "time"

    def build(self):
        info = timedate()
        self.toggle("clock", "Set time automatically", "", info.get("NTP") == "yes",
                    lambda on: in_background(self, lambda: ok("timedatectl", "set-ntp", "true" if on else "false",
                                                                timeout=120), lambda _r: None))
        zones = [z for z in run("timedatectl", "list-timezones", timeout=10).splitlines() if "/" in z]
        cur = info.get("Timezone", "")
        cb = self.combo("globe", "Time zone", "", [(z.replace("_", " "), z) for z in zones], cur,
                        lambda z: in_background(self, lambda: ok("timedatectl", "set-timezone", z, timeout=120),
                                                lambda _r: None))
        cb.setMaxVisibleItems(16)
        cb.setMinimumWidth(280)
        self.section("Additional settings")
        self.row("arrow_sync_circle", "Sync now", "Synchronise the clock with an internet time server",
                 on_click=lambda: spawn("timedatectl", "set-ntp", "true"))
        self.row("calendar_ltr", "Clock and calendar on the taskbar", "24-hour clock, show seconds, calendar",
                 on_click=lambda: spawn("qdbus6", "org.kde.plasmashell", "/PlasmaShell",
                                        "org.kde.PlasmaShell.evaluateScript",
                                        "for (const p of panels()) for (const w of p.widgets('org.kde.plasma.digitalclock')) w.showConfigurationInterface()"))


class LanguagePage(Page):
    title = "Language & region"
    parent_key = "time"

    def build(self):
        lang = os.environ.get("LANG", "en_AU.UTF-8")
        ql = QLocale(lang.split(".")[0])
        name = QLocale.languageToString(ql.language())
        if ql.language() == QLocale.Language.C:
            name = "English"
        elif "_" in lang:
            name += f" ({QLocale.territoryToString(ql.territory())})"
        self.section("Language")
        self.row("local_language", "Glass Panes display language", name,
                 on_click=lambda: control_panel("kcm_regionandlang"))
        self.row("keyboard", "Keyboard", "Keyboard layouts and input methods",
                 on_click=lambda: control_panel("kcm_keyboard"))
        self.section("Region")
        self.row("globe", "Regional format", "Dates, times, numbers and currency",
                 on_click=lambda: control_panel("kcm_regionandlang"))


PAGES = {"time": TimeLangPage, "time_date": DateTimePage, "language": LanguagePage}
