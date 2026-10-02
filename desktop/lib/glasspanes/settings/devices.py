"""Bluetooth & devices: Bluetooth, paired devices, mouse, typing, printers."""
from PyQt6.QtWidgets import QHBoxLayout, QSlider
from PyQt6.QtCore import Qt

from .. import appearance
from ..widgets import SettingRow, label
from .util import Page, control_panel, in_background, ok, run, spawn


def bt_powered():
    return "Powered: yes" in run("bluetoothctl", "show", timeout=5)


def bt_devices():
    out = run("bluetoothctl", "devices", "Paired", timeout=5) or run("bluetoothctl", "paired-devices", timeout=5)
    devs = []
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0] == "Device":
            info = run("bluetoothctl", "info", parts[1], timeout=5)
            devs.append((parts[1], parts[2], "Connected: yes" in info))
    return devs


class BluetoothPage(Page):
    title = "Bluetooth & devices"

    def build(self):
        self.has_bt = bool(run("bluetoothctl", "list", timeout=5).strip())
        c, lay = self.card()
        head = QHBoxLayout()
        head.addWidget(label("Devices"))
        head.addStretch(1)
        head.addWidget(self.button("Add device", lambda: spawn("bluedevil-wizard"), accent=True))
        lay.addLayout(head)
        if self.has_bt:
            self.bt_toggle = self.toggle("bluetooth", "Bluetooth", "Discoverable as this PC",
                                         bt_powered(), self.set_bt)
        else:
            self.row("bluetooth", "Bluetooth", "No Bluetooth adapter was found on this PC")
        self.list_host = self.body
        self.dev_rows = []
        self.section("Settings")
        self.row("print", "Printers & scanners", "Preferences, troubleshoot", open_key="printers")
        self.row("cursor", "Mouse", "Buttons, mouse pointer speed, scrolling", open_key="mouse")
        self.row("keyboard", "Typing", "Keyboard layout, repeat rate, touch keyboard",
                 on_click=lambda: control_panel("kcm_keyboard"))
        self.row("phone", "Phone link", "Connect your Android phone (KDE Connect if installed)",
                 on_click=lambda: spawn("kdeconnect-app") or spawn("plasma-discover", "--search", "kde connect"))
        self.row("usb_stick", "AutoPlay", "Defaults for removable drives and memory cards",
                 on_click=lambda: control_panel("kcm_device_automounter"))

    def set_bt(self, on):
        in_background(self, lambda: ok("bluetoothctl", "power", "on" if on else "off", timeout=10),
                      lambda _r: None)

    def refresh(self):
        if not self.has_bt:
            return
        in_background(self, bt_devices, self.show_devices)

    def show_devices(self, devs):
        for r in self.dev_rows:
            r.deleteLater()
        self.dev_rows = []
        if isinstance(devs, Exception):
            return
        idx = 3
        for addr, name, connected in devs:
            btn = self.button("Disconnect" if connected else "Connect",
                              lambda _=False, a=addr, c=connected: self.connect_dev(a, c))
            r = SettingRow(self.t, "bluetooth_connected" if connected else "bluetooth", name,
                           "Connected" if connected else "Paired", btn)
            self.body.insertWidget(idx, r)
            idx += 1
            self.dev_rows.append(r)

    def connect_dev(self, addr, connected):
        in_background(self, lambda: ok("bluetoothctl", "disconnect" if connected else "connect", addr,
                                       timeout=20), lambda _r: self.refresh())


class MousePage(Page):
    title = "Mouse"
    parent_key = "bluetooth"

    def build(self):
        left = appearance.kread("kcminputrc", ["Mouse"], "XLbInptLeftHanded", "false") == "true"
        self.combo("cursor", "Primary mouse button", "", [("Left", False), ("Right", True)], left,
                   self.set_left)
        accel = appearance.kread("kcminputrc", ["Mouse"], "XLbInptPointerAcceleration", "0")
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(-100, 100)
        try:
            s.setValue(int(float(accel) * 100))
        except ValueError:
            s.setValue(0)
        s.setFixedWidth(220)
        s.sliderReleased.connect(lambda: self.set_speed(s.value() / 100))
        self.row("cursor", "Mouse pointer speed", "", s)
        nat = appearance.kread("kcminputrc", ["Mouse"], "XLbInptNaturalScroll", "false") == "true"
        self.combo("arrow_up", "Scrolling direction", "", [("Down motion scrolls down", False),
                                                           ("Down motion scrolls up", True)], nat,
                   lambda v: self.set_key("XLbInptNaturalScroll", "true" if v else "false"))
        size = appearance.kread("kcminputrc", ["Mouse"], "cursorSize", "24")
        self.combo("cursor", "Mouse pointer size", "Takes effect after you sign out",
                   [("Normal", "24"), ("Large", "32"), ("Larger", "48"), ("Largest", "64")], size,
                   lambda v: self.set_key("cursorSize", v))
        self.section("Related settings")
        self.row("options", "Additional mouse settings", "Touchpad, acceleration profile",
                 on_click=lambda: control_panel("kcm_mouse"))

    def set_key(self, key, value):
        appearance.kwrite("kcminputrc", ["Mouse"], key, value)
        appearance.qdbus("org.kde.KWin", "/KWin", "reconfigure")
        spawn("qdbus6", "org.kde.kded6", "/kded", "org.kde.kded6.reconfigure")

    def set_left(self, on):
        self.set_key("XLbInptLeftHanded", "true" if on else "false")
        spawn("xmodmap", "-e", "pointer = 3 2 1" if on else "pointer = 1 2 3")

    def set_speed(self, v):
        self.set_key("XLbInptPointerAcceleration", f"{v:.2f}")
        for line in run("xinput", "list", "--id-only", timeout=5).split():
            spawn("xinput", "set-prop", line, "libinput Accel Speed", f"{v:.2f}")


PAGES = {"bluetooth": BluetoothPage, "mouse": MousePage}
