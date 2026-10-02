"""Network & internet: status, Wi-Fi networks, Ethernet, airplane mode, VPN, proxy."""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QHBoxLayout, QInputDialog, QLineEdit, QMessageBox

from ..widgets import SettingRow, label
from .util import Page, control_panel, in_background, ok, run


def nm_fields(line):
    """Splits nmcli -t output (colon separated, with \\: escapes)."""
    out, cur, i = [], "", 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if line[i] == ":":
            out.append(cur)
            cur = ""
        else:
            cur += line[i]
        i += 1
    out.append(cur)
    return out


def active_connections():
    rows = []
    for line in run("nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active").splitlines():
        f = nm_fields(line)
        if len(f) >= 3 and f[1] not in ("loopback", "bridge"):
            rows.append(f)
    return rows


def wifi_list():
    nets = {}
    for line in run("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                    timeout=20).splitlines():
        f = nm_fields(line)
        if len(f) < 4 or not f[1]:
            continue
        inuse, ssid, signal, sec = f[0] == "*", f[1], int(f[2] or 0), f[3]
        if ssid not in nets or signal > nets[ssid][1]:
            nets[ssid] = (inuse, signal, sec)
    return sorted(((s, *v) for s, v in nets.items()), key=lambda x: (not x[1], -x[2]))


def wifi_icon(signal):
    return "wifi_1" if signal > 70 else "wifi_2" if signal > 45 else "wifi_3" if signal > 20 else "wifi_4"


class NetworkPage(Page):
    title = "Network & internet"

    def build(self):
        c, lay = self.card()
        self.status_title = label("", "subtitle")
        self.status_desc = label("", "secondary")
        lay.addWidget(self.status_title)
        lay.addWidget(self.status_desc)
        self.has_wifi = "wifi" in run("nmcli", "-t", "-f", "TYPE", "device")
        if self.has_wifi:
            on = run("nmcli", "radio", "wifi").strip() == "enabled"
            self.wifi_toggle = self.toggle("wifi_1", "Wi-Fi", "Connect, manage known networks", on,
                                           self.set_wifi)
            self.nets_header = label("Available networks", "section")
            self.add(self.nets_header)
        self.net_rows = []
        self.net_index = self.body.count()
        self.section("More")
        self.row("plug_connected", "Ethernet", "Authentication, IP and DNS settings",
                 on_click=lambda: control_panel("kcm_networkmanagement"))
        self.row("shield_lock", "VPN", "Add, connect, manage",
                 on_click=lambda: control_panel("kcm_networkmanagement"))
        airplane = run("nmcli", "radio", "all").count("disabled") >= 2
        self.toggle("airplane", "Airplane mode", "Stop all wireless communication", airplane,
                    lambda on: ok("nmcli", "radio", "all", "off" if on else "on"))
        self.row("globe", "Proxy", "Proxy server for Wi-Fi and Ethernet connections",
                 on_click=lambda: control_panel("kcm_proxy"))
        self.row("options", "Advanced network settings", "View all network adapters, network reset",
                 on_click=lambda: control_panel("kcm_networkmanagement"))

    def refresh(self):
        in_background(self, lambda: (active_connections(), wifi_list() if self.has_wifi else []),
                      self.show)

    def show(self, result):
        if isinstance(result, Exception):
            return
        conns, nets = result
        if conns:
            name, kind, dev = conns[0][:3]
            self.status_title.setText(name if "wireless" in kind else "Ethernet")
            self.status_desc.setText("Connected, secured" if "wireless" in kind else f"Connected · {dev}")
        else:
            self.status_title.setText("Not connected")
            self.status_desc.setText("You aren't connected to any networks")
        for r in self.net_rows:
            r.deleteLater()
        self.net_rows = []
        if not self.has_wifi:
            return
        idx = self.body.indexOf(self.nets_header) + 1
        for ssid, inuse, signal, sec in nets[:12]:
            btn = self.button("Disconnect" if inuse else "Connect",
                              lambda _=False, s=ssid, u=inuse, k=sec: self.connect(s, u, k), accent=not inuse)
            r = SettingRow(self.t, wifi_icon(signal), ssid,
                           ("Connected, " if inuse else "") + ("Secured" if sec and sec != "--" else "Open"),
                           btn)
            self.body.insertWidget(idx, r)
            idx += 1
            self.net_rows.append(r)

    def set_wifi(self, on):
        ok("nmcli", "radio", "wifi", "on" if on else "off")
        QTimer.singleShot(2500, self.refresh)

    def connect(self, ssid, inuse, sec):
        if inuse:
            in_background(self, lambda: ok("nmcli", "connection", "down", "id", ssid), lambda _r: self.refresh())
            return
        known = ssid in run("nmcli", "-t", "-f", "NAME", "connection", "show").splitlines()
        args = ["nmcli", "device", "wifi", "connect", ssid]
        if not known and sec and sec != "--":
            pw, accepted = QInputDialog.getText(self, ssid, "Enter the network security key",
                                                QLineEdit.EchoMode.Password)
            if not accepted:
                return
            args += ["password", pw]

        def done(success):
            if success is not True:
                QMessageBox.warning(self, ssid, "Can't connect to this network.")
            self.refresh()
        in_background(self, lambda: ok(*args, timeout=45), done)


PAGES = {"network": NetworkPage}
