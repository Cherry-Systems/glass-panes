"""Task Manager: Processes, Performance, Startup apps, Details and Services, Windows 11 style."""
import collections
import configparser
import os
import platform
import signal
import subprocess
import sys
import time

import psutil
from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                             QStackedWidget, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from . import apps as appdb
from . import style
from .widgets import Card, NavList, label

HEAT_LIGHT = ("#fff4c4", "#ffe08a", "#ffc65c", "#f9a13a")
HEAT_DARK = ("#4a3f1a", "#6a5216", "#8a5a12", "#a8500e")
COLORS = {"cpu": "#117dbb", "mem": "#8b12ae", "disk": "#4da60c", "net": "#a74f01"}
ROLE_HEAT = Qt.ItemDataRole.UserRole + 10
ROLE_SORT = Qt.ItemDataRole.UserRole + 11


def fmt_bytes(n, per_sec=False):
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    n = float(n)
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    s = f"{n:.0f}" if i == 0 or n >= 100 else f"{n:.1f}"
    return f"{s} {units[i]}{'/s' if per_sec else ''}"


def window_pids():
    """PIDs owning top-level windows, with their titles (X11 _NET_CLIENT_LIST)."""
    try:
        from Xlib import X, display
        d = display.Display()
        root = d.screen().root
        net_list = d.intern_atom("_NET_CLIENT_LIST")
        net_pid = d.intern_atom("_NET_WM_PID")
        net_name = d.intern_atom("_NET_WM_NAME")
        utf8 = d.intern_atom("UTF8_STRING")
        out = {}
        prop = root.get_full_property(net_list, X.AnyPropertyType)
        for wid in (prop.value if prop else []):
            w = d.create_resource_object("window", wid)
            p = w.get_full_property(net_pid, X.AnyPropertyType)
            if not p:
                continue
            n = w.get_full_property(net_name, utf8)
            title = n.value.decode(errors="replace") if n else ""
            out.setdefault(int(p.value[0]), title)
        d.close()
        return out
    except Exception:  # noqa: BLE001 — no X server (tests) or no python-xlib
        return {}


class HeatDelegate(QStyledItemDelegate):
    def __init__(self, t, parent=None):
        super().__init__(parent)
        self.t = t

    def paint(self, p, opt, index):
        heat = index.data(ROLE_HEAT)
        if heat is not None and not (opt.state & opt.state.State_Selected):
            pal = HEAT_DARK if self.t.dark else HEAT_LIGHT
            lvl = 0 if heat < 0.05 else 1 if heat < 0.3 else 2 if heat < 0.6 else 3
            p.fillRect(opt.rect, QColor(pal[lvl]))
        super().paint(p, opt, index)


class Tree(QTreeWidget):
    def __init__(self, t, columns, widths):
        super().__init__()
        self.setColumnCount(len(columns))
        self.setHeaderLabels(columns)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setItemDelegate(HeatDelegate(t, self))
        self.setIconSize(QSize(20, 20))
        self.setSortingEnabled(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        h = self.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, w in enumerate(widths, start=1):
            self.setColumnWidth(i, w)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.headerItem().setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(f"QTreeWidget {{ border: none; background: {t.window}; }}"
                           f"QTreeWidget::item {{ height: 30px; border: none; }}"
                           f"QHeaderView::section {{ background: {t.window}; border: none;"
                           f" border-right: 1px solid {t.control_border}; padding: 6px 8px; }}")


class Graph(QWidget):
    """Scrolling 60-second usage graph, like Task Manager's performance charts."""

    def __init__(self, color, t, small=False):
        super().__init__()
        self.color = QColor(color)
        self.t = t
        self.data = collections.deque([0.0] * 60, maxlen=60)
        self.small = small
        self.setMinimumHeight(40 if small else 220)

    def push(self, v):
        self.data.append(max(0.0, min(1.0, v)))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.fillRect(r, QColor(self.t.card))
        grid = QColor(self.color)
        grid.setAlpha(40)
        p.setPen(QPen(grid, 1))
        if not self.small:
            for i in range(1, 10):
                y = r.top() + r.height() * i / 10
                p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
            for i in range(1, 20):
                x = r.left() + r.width() * i / 20
                p.drawLine(int(x), int(r.top()), int(x), int(r.bottom()))
        path = QPainterPath()
        n = len(self.data)
        pts = [(r.left() + r.width() * i / (n - 1), r.bottom() - r.height() * v) for i, v in enumerate(self.data)]
        path.moveTo(pts[0][0], r.bottom())
        for x, y in pts:
            path.lineTo(x, y)
        path.lineTo(pts[-1][0], r.bottom())
        fill = QColor(self.color)
        fill.setAlpha(45)
        p.fillPath(path, fill)
        p.setPen(QPen(self.color, 1.2))
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
        p.setPen(QPen(self.color, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)


class Sampler:
    """Collects system-wide and per-process usage once a second."""

    def __init__(self):
        self.ncpu = psutil.cpu_count() or 1
        self.prev_disk = psutil.disk_io_counters()
        self.prev_net = psutil.net_io_counters()
        self.prev_io = {}
        self.prev_t = time.monotonic()
        psutil.cpu_percent(None)
        self.procs = {}
        self.sample()

    def sample(self):
        now = time.monotonic()
        dt = max(0.2, now - self.prev_t)
        self.prev_t = now
        self.cpu = psutil.cpu_percent(None) / 100
        self.cpu_freq = psutil.cpu_freq()
        self.mem = psutil.virtual_memory()
        self.swap = psutil.swap_memory()
        d = psutil.disk_io_counters()
        if d and self.prev_disk:
            self.disk_rate = ((d.read_bytes - self.prev_disk.read_bytes) / dt,
                              (d.write_bytes - self.prev_disk.write_bytes) / dt)
            busy = getattr(d, "busy_time", None)
            pbusy = getattr(self.prev_disk, "busy_time", None)
            self.disk_active = min(1.0, (busy - pbusy) / (dt * 1000)) if busy is not None else min(
                1.0, sum(self.disk_rate) / 200e6)
        else:
            self.disk_rate, self.disk_active = (0, 0), 0
        self.prev_disk = d
        n = psutil.net_io_counters()
        self.net_rate = ((n.bytes_sent - self.prev_net.bytes_sent) / dt, (n.bytes_recv - self.prev_net.bytes_recv) / dt)
        self.prev_net = n
        procs = {}
        for pr in psutil.process_iter(["pid", "ppid", "name", "username", "status", "memory_info", "exe", "num_threads",
                                       "cmdline"]):
            info = pr.info
            try:
                info["cpu"] = pr.cpu_percent(None) / 100 / self.ncpu
            except psutil.Error:
                info["cpu"] = 0.0
            try:
                io = pr.io_counters()
                prev = self.prev_io.get(info["pid"])
                info["disk"] = ((io.read_bytes + io.write_bytes) - prev) / dt if prev is not None else 0
                self.prev_io[info["pid"]] = io.read_bytes + io.write_bytes
            except (psutil.Error, AttributeError):
                info["disk"] = 0
            info["rss"] = info["memory_info"].rss if info["memory_info"] else 0
            procs[info["pid"]] = info
        self.procs = procs


def friendly_name(info, app_names):
    exe = os.path.basename(info.get("exe") or "") or info.get("name") or "?"
    cmd = info.get("cmdline") or []
    if exe.startswith("python") and len(cmd) > 2 and cmd[1] == "-m":
        mod = cmd[2].split(".")[-1]
        return {"start": "Start", "shell": "Glass Shell", "taskmgr": "Task Manager",
                "settings": "Settings"}.get(mod, mod)
    if exe in ("wine-preloader", "wine64-preloader", "wine", "wine64") and cmd:
        return os.path.basename(cmd[0].replace("\\", "/"))
    return app_names.get(exe, exe)


class ProcessesPage(QWidget):
    COLS = ["Name", "Status", "CPU", "Memory", "Disk", "Network"]

    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = Tree(win.t, self.COLS, [90, 80, 100, 100, 90])
        self.tree.customContextMenuRequested.connect(self.menu)
        self.tree.itemSelectionChanged.connect(lambda: win.end_btn.setEnabled(bool(self.selected_pids())))
        lay.addWidget(self.tree)
        self.apps_root = QTreeWidgetItem(["Apps"])
        self.bg_root = QTreeWidgetItem(["Background processes"])
        for r in (self.apps_root, self.bg_root):
            r.setFont(0, style.font(10, QFont.Weight.DemiBold))
            r.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(r)
            r.setExpanded(True)
        self.items = {}
        self.app_names = {}
        self.app_icons = {}
        for a in appdb.all_apps(include_hidden=True).values():
            argv = a.command()
            if argv:
                exe = os.path.basename(argv[0])
                self.app_names.setdefault(exe, a.name)
                self.app_icons.setdefault(exe, a.icon)

    def selected_pids(self):
        it = self.tree.currentItem()
        if not it or it.data(0, Qt.ItemDataRole.UserRole) is None:
            return []
        return it.data(0, Qt.ItemDataRole.UserRole)

    def update_data(self, s):
        wins = window_pids()
        me = os.getuid()
        groups = {}
        own_pids = {pid for pid, i in s.procs.items() if i.get("username") == psutil.Process().username()}
        for pid in wins:
            if pid not in s.procs:
                continue
            members = [pid]
            try:
                members += [c.pid for c in psutil.Process(pid).children(recursive=True)]
            except psutil.Error:
                pass
            groups[("app", pid)] = members
        grouped = {p for m in groups.values() for p in m}
        for pid, info in s.procs.items():
            if pid in grouped or pid not in own_pids or info["name"] in ("systemd", "(sd-pam)"):
                continue
            groups[("bg", pid)] = [pid]
        seen = set()
        for key, members in groups.items():
            kind, pid = key
            info = s.procs[pid]
            cpu = sum(s.procs[m]["cpu"] for m in members if m in s.procs)
            mem = sum(s.procs[m]["rss"] for m in members if m in s.procs)
            disk = sum(s.procs[m]["disk"] for m in members if m in s.procs)
            name = friendly_name(info, self.app_names)
            if kind == "app" and len(members) > 1:
                name = f"{name} ({len(members)})"
            it = self.items.get(key)
            if it is None:
                it = QTreeWidgetItem()
                exe = os.path.basename(info.get("exe") or info["name"] or "")
                it.setIcon(0, style.app_icon(self.app_icons.get(exe, exe), 20))
                (self.apps_root if kind == "app" else self.bg_root).addChild(it)
                self.items[key] = it
            it.setText(0, name)
            it.setToolTip(0, wins.get(pid, "") or " ".join(info.get("cmdline") or [])[:200])
            it.setData(0, Qt.ItemDataRole.UserRole, members)
            it.setText(1, "Suspended" if info.get("status") == psutil.STATUS_STOPPED else "")
            vals = [(f"{cpu * 100:.1f}%", cpu), (fmt_bytes(mem), mem / max(1, s.mem.total) * 8),
                    (f"{disk / 1048576:.1f} MB/s", disk / 50e6), ("0 Mbps", 0.0)]
            for col, (text, heat) in enumerate(vals, start=2):
                it.setText(col, text)
                it.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                it.setData(col, ROLE_HEAT, heat)
            it.setData(0, ROLE_SORT, cpu * 1e12 + mem)
            seen.add(key)
        for key in list(self.items):
            if key not in seen:
                it = self.items.pop(key)
                (it.parent() or self.tree.invisibleRootItem()).removeChild(it)
        for root in (self.apps_root, self.bg_root):
            kids = [root.child(i) for i in range(root.childCount())]
            order = sorted(kids, key=lambda k: k.text(0).lower())
            if kids != order:
                cur = self.tree.currentItem()
                for k in kids:
                    root.removeChild(k)
                root.addChildren(order)
                if cur in order:
                    self.tree.setCurrentItem(cur)
            n = root.childCount()
            root.setText(0, f"{'Apps' if root is self.apps_root else 'Background processes'} ({n})")
        cpu_t = s.cpu
        self.tree.headerItem().setText(2, f"{cpu_t * 100:.0f}%\nCPU")
        self.tree.headerItem().setText(3, f"{s.mem.percent:.0f}%\nMemory")
        self.tree.headerItem().setText(4, f"{s.disk_active * 100:.0f}%\nDisk")
        self.tree.headerItem().setText(5, "0%\nNetwork")

    def menu(self, pos):
        pids = self.selected_pids()
        if not pids:
            return
        m = QMenu(self)
        m.addAction("End task", self.win.end_task)
        m.addAction("Open file location", lambda: self.open_location(pids[0]))
        m.addAction("Go to details", lambda: self.win.go_details(pids[0]))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def open_location(self, pid):
        try:
            exe = psutil.Process(pid).exe()
            subprocess.Popen(["dolphin", "--select", exe], start_new_session=True)
        except (psutil.Error, OSError):
            pass


class PerfTile(Card):
    def __init__(self, title, color, t):
        super().__init__(clickable=True)
        self.t = t
        self.setFixedHeight(68)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)
        self.graph = Graph(color, t, small=True)
        self.graph.setFixedSize(70, 50)
        lay.addWidget(self.graph)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel(title)
        self.title.setFont(style.font(10.5, QFont.Weight.DemiBold))
        self.sub = QLabel("")
        self.sub.setProperty("role", "secondary")
        col.addStretch(1)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.setChecked(False)

    def setChecked(self, on):  # noqa: N802 (Qt naming)
        bg = self.t.subtle_hover if on else "transparent"
        self.setStyleSheet(f"QFrame[role=card] {{ background: {bg}; border: none; border-radius: 6px; }}")


class PerformancePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        t = win.t
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        side = QVBoxLayout()
        side.setSpacing(2)
        self.tiles = {}
        disk_name = "Disk 0"
        net_name = "Wi-Fi" if any(n.startswith("wl") for n in psutil.net_if_addrs()) else "Ethernet"
        for key, title in (("cpu", "CPU"), ("mem", "Memory"), ("disk", disk_name), ("net", net_name)):
            tile = PerfTile(title, COLORS[key], t)
            tile.clicked.connect(lambda _=False, k=key: self.select(k))
            side.addWidget(tile)
            self.tiles[key] = tile
        side.addStretch(1)
        sw = QWidget()
        sw.setFixedWidth(230)
        sw.setLayout(side)
        lay.addWidget(sw)
        main = QVBoxLayout()
        head = QHBoxLayout()
        self.head = QLabel("CPU")
        self.head.setFont(style.font(20, QFont.Weight.DemiBold))
        self.model = label("", "secondary")
        self.model.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        head.addWidget(self.head)
        head.addStretch(1)
        head.addWidget(self.model)
        main.addLayout(head)
        self.caption = label("% Utilisation over 60 seconds", "secondary")
        main.addWidget(self.caption)
        self.graphs = QStackedWidget()
        self.big = {}
        for key in COLORS:
            g = Graph(COLORS[key], t)
            self.big[key] = g
            self.graphs.addWidget(g)
        main.addWidget(self.graphs, 1)
        self.stats = QLabel()
        self.stats.setTextFormat(Qt.TextFormat.RichText)
        main.addWidget(self.stats)
        lay.addLayout(main, 1)
        self.cpu_model = self._cpu_model()
        self.select("cpu")
        self.boot = psutil.boot_time()

    def _cpu_model(self):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
        return platform.processor() or "Processor"

    def select(self, key):
        self.key = key
        for k, tile in self.tiles.items():
            tile.setChecked(k == key)
        self.graphs.setCurrentWidget(self.big[key])
        self.head.setText(self.tiles[key].title.text())
        self.caption.setText({"cpu": "% Utilisation over 60 seconds", "mem": "Memory usage",
                              "disk": "Active time", "net": "Throughput"}[key])
        self.model.setText({"cpu": self.cpu_model, "mem": fmt_bytes(psutil.virtual_memory().total),
                            "disk": "", "net": ""}[key])

    @staticmethod
    def stat_html(pairs):
        cells = "".join(f"<td style='padding-right:28px'><span style='color:gray'>{k}</span><br>"
                        f"<span style='font-size:15pt'>{v}</span></td>" for k, v in pairs)
        return f"<table><tr>{cells}</tr></table>"

    def update_data(self, s):
        net_peak = max(1.0, max(s.net_rate) / 1.25e6)
        vals = {"cpu": s.cpu, "mem": s.mem.percent / 100, "disk": s.disk_active,
                "net": min(1.0, max(s.net_rate) / max(1.25e6, net_peak * 1.25e6))}
        for k, v in vals.items():
            self.tiles[k].graph.push(v)
            self.big[k].push(v)
        used = s.mem.total - s.mem.available
        self.tiles["cpu"].sub.setText(f"{s.cpu * 100:.0f}%  {s.cpu_freq.current / 1000:.2f} GHz"
                                      if s.cpu_freq else f"{s.cpu * 100:.0f}%")
        self.tiles["mem"].sub.setText(f"{fmt_bytes(used)}/{fmt_bytes(s.mem.total)} ({s.mem.percent:.0f}%)")
        self.tiles["disk"].sub.setText(f"SSD\n{s.disk_active * 100:.0f}%")
        self.tiles["net"].sub.setText(f"S: {s.net_rate[0] * 8 / 1000:.0f} R: {s.net_rate[1] * 8 / 1000:.0f} Kbps")
        up = int(time.time() - self.boot)
        uptime = f"{up // 86400}:{up % 86400 // 3600:02d}:{up % 3600 // 60:02d}:{up % 60:02d}"
        if self.key == "cpu":
            nthreads = sum(p.get("num_threads", 0) or 0 for p in s.procs.values())
            self.stats.setText(self.stat_html([
                ("Utilisation", f"{s.cpu * 100:.0f}%"),
                ("Speed", f"{s.cpu_freq.current / 1000:.2f} GHz" if s.cpu_freq else "—"),
                ("Processes", len(s.procs)), ("Logical processors", s.ncpu), ("Up time", uptime)]))
        elif self.key == "mem":
            self.stats.setText(self.stat_html([
                ("In use", fmt_bytes(used)), ("Available", fmt_bytes(s.mem.available)),
                ("Cached", fmt_bytes(getattr(s.mem, "cached", 0))),
                ("Swap", f"{fmt_bytes(s.swap.used)}/{fmt_bytes(s.swap.total)}")]))
        elif self.key == "disk":
            self.stats.setText(self.stat_html([
                ("Active time", f"{s.disk_active * 100:.0f}%"), ("Read speed", fmt_bytes(s.disk_rate[0], True)),
                ("Write speed", fmt_bytes(s.disk_rate[1], True))]))
        else:
            self.stats.setText(self.stat_html([
                ("Send", f"{s.net_rate[0] * 8 / 1000:.0f} Kbps"), ("Receive", f"{s.net_rate[1] * 8 / 1000:.0f} Kbps")]))


class StartupPage(QWidget):
    def __init__(self, win):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = Tree(win.t, ["Name", "Publisher", "Status", "Startup impact"], [160, 100, 120])
        self.tree.setRootIsDecorated(False)
        lay.addWidget(self.tree)
        self.tree.customContextMenuRequested.connect(self.menu)
        self.load()

    def load(self):
        self.tree.clear()
        user_dir = os.path.expanduser("~/.config/autostart")
        entries = {}
        for d in ("/etc/xdg/autostart", user_dir):
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".desktop"):
                        entries[f] = os.path.join(d, f)
        for fid, path in sorted(entries.items()):
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            try:
                cp.read(path, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError):
                continue
            if e.get("NoDisplay", "false") == "true" or fid.startswith(("glass-", "org.kde.", "polkit", "at-spi")):
                continue
            hidden = e.get("Hidden", "false").lower() == "true"
            it = QTreeWidgetItem([e.get("Name", fid), "", "Disabled" if hidden else "Enabled", "Not measured"])
            it.setIcon(0, style.app_icon(e.get("Icon", ""), 20))
            it.setData(0, Qt.ItemDataRole.UserRole, (fid, path, hidden))
            self.tree.addTopLevelItem(it)

    def menu(self, pos):
        it = self.tree.currentItem()
        if not it:
            return
        fid, path, hidden = it.data(0, Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        m.addAction("Enable" if hidden else "Disable", lambda: self.toggle(fid, path, hidden))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def toggle(self, fid, path, hidden):
        from .settings.apps_page import StartupPage as SP
        SP.set_enabled(None, fid, path, hidden)
        self.load()


class DetailsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = Tree(win.t, ["Name", "PID", "Status", "User name", "CPU", "Memory"], [70, 90, 110, 60, 100])
        self.tree.setRootIsDecorated(False)
        self.tree.setSortingEnabled(True)
        self.tree.customContextMenuRequested.connect(self.menu)
        self.tree.itemSelectionChanged.connect(lambda: win.end_btn.setEnabled(bool(self.selected_pids())))
        lay.addWidget(self.tree)
        self.items = {}

    def selected_pids(self):
        it = self.tree.currentItem()
        return [int(it.text(1))] if it else []

    def update_data(self, s):
        self.tree.setSortingEnabled(False)
        for pid, info in s.procs.items():
            it = self.items.get(pid)
            if it is None:
                it = NumItem()
                self.items[pid] = it
                self.tree.addTopLevelItem(it)
            it.setText(0, info["name"] or "?")
            it.setText(1, str(pid))
            it.setText(2, "Running" if info.get("status") != psutil.STATUS_STOPPED else "Suspended")
            it.setText(3, info.get("username") or "")
            it.setText(4, f"{info['cpu'] * 100:02.0f}")
            it.setText(5, f"{info['rss'] // 1024:,} K")
        for pid in list(self.items):
            if pid not in s.procs:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(self.items.pop(pid)))
        self.tree.setSortingEnabled(True)

    def select_pid(self, pid):
        it = self.items.get(pid)
        if it:
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it)

    def menu(self, pos):
        pids = self.selected_pids()
        if not pids:
            return
        m = QMenu(self)
        m.addAction("End task", self.win.end_task)
        m.addAction("End process tree", lambda: self.win.kill(pids, tree=True))
        m.exec(self.tree.viewport().mapToGlobal(pos))


class NumItem(QTreeWidgetItem):
    def __lt__(self, other):
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        a, b = self.text(col).replace(",", "").rstrip(" K"), other.text(col).replace(",", "").rstrip(" K")
        try:
            return float(a) < float(b)
        except ValueError:
            return a.lower() < b.lower()


class ServicesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = Tree(win.t, ["Name", "Description", "Status"], [380, 100])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 260)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tree)
        self.loaded = False

    def showEvent(self, e):
        super().showEvent(e)
        if not self.loaded:
            self.loaded = True
            try:
                out = subprocess.run(["systemctl", "list-units", "--type=service", "--all", "--no-legend",
                                      "--plain", "--no-pager"], capture_output=True, text=True, timeout=10).stdout
            except (OSError, subprocess.TimeoutExpired):
                out = ""
            for line in out.splitlines():
                parts = line.split(None, 4)
                if len(parts) < 5:
                    continue
                unit, _load, _active, sub, desc = parts
                self.tree.addTopLevelItem(QTreeWidgetItem([unit.removesuffix(".service"), desc,
                                                           "Running" if sub == "running" else "Stopped"]))


PAGES = [("processes", "Processes", "grid"), ("performance", "Performance", "pulse"),
         ("startup", "Startup apps", "gauge"), ("details", "Details", "task_list_ltr"),
         ("services", "Services", "puzzle_piece")]


class TaskManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.t = style.make_theme()
        self.setWindowTitle("Task Manager")
        self.setWindowIcon(QIcon.fromTheme("utilities-system-monitor"))
        self.resize(1000, 680)
        root = QWidget()
        root.setObjectName("Window")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        side = QWidget()
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(8, 12, 8, 12)
        self.nav = NavList(self.t)
        for key, title, icon in PAGES:
            self.nav.add(title, icon if os.path.exists(os.path.join(style.paths.ICONS, icon + ".svg")) else "apps",
                         key)
        sl.addWidget(self.nav, 1)
        lay.addWidget(side)
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(16, 12, 16, 12)
        bar = QHBoxLayout()
        self.page_title = QLabel("Processes")
        self.page_title.setFont(style.font(15, QFont.Weight.DemiBold))
        bar.addWidget(self.page_title)
        bar.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type a name, publisher or PID to search")
        self.search.setFixedWidth(320)
        self.search.textChanged.connect(self.filter)
        bar.addWidget(self.search)
        run_btn = QPushButton(" Run new task")
        run_btn.setIcon(style.icon("add", self.t.text, 16))
        run_btn.setProperty("flat", "true")
        run_btn.clicked.connect(self.run_new)
        bar.addWidget(run_btn)
        self.end_btn = QPushButton(" End task")
        self.end_btn.setIcon(style.icon("dismiss", self.t.text, 16))
        self.end_btn.setProperty("flat", "true")
        self.end_btn.setEnabled(False)
        self.end_btn.clicked.connect(self.end_task)
        bar.addWidget(self.end_btn)
        ml.addLayout(bar)
        self.stack = QStackedWidget()
        self.sampler = Sampler()
        self.pages = {"processes": ProcessesPage(self), "performance": PerformancePage(self),
                      "startup": StartupPage(self), "details": DetailsPage(self), "services": ServicesPage(self)}
        for p in self.pages.values():
            self.stack.addWidget(p)
        ml.addWidget(self.stack, 1)
        lay.addWidget(main, 1)
        self.nav.currentRowChanged.connect(self.switch)
        self.nav.setCurrentRow(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        QTimer.singleShot(0, self.tick)

    def switch(self, row):
        key, title, _ = PAGES[row]
        self.stack.setCurrentWidget(self.pages[key])
        self.page_title.setText(title)
        self.end_btn.setVisible(key in ("processes", "details"))
        self.search.setVisible(key in ("processes", "details"))

    def tick(self):
        self.sampler.sample()
        for key in ("processes", "performance", "details"):
            self.pages[key].update_data(self.sampler)
        self.filter(self.search.text())

    def filter(self, text):
        q = text.lower().strip()
        page = self.stack.currentWidget()
        tree = getattr(page, "tree", None)
        if tree is None:
            return
        def walk(item):
            for i in range(item.childCount()):
                c = item.child(i)
                if c.childCount():
                    walk(c)
                    continue
                pids = c.data(0, Qt.ItemDataRole.UserRole)
                hay = c.text(0).lower() + " " + (c.text(1) if page is self.pages["details"] else
                                                 " ".join(map(str, pids if isinstance(pids, list) else [])))
                c.setHidden(bool(q) and q not in hay)
        walk(tree.invisibleRootItem())

    def current_pids(self):
        page = self.stack.currentWidget()
        return page.selected_pids() if hasattr(page, "selected_pids") else []

    def end_task(self):
        pids = self.current_pids()
        if pids:
            self.kill(pids)

    def kill(self, pids, tree=False):
        if tree:
            try:
                pids = pids + [c.pid for c in psutil.Process(pids[0]).children(recursive=True)]
            except psutil.Error:
                pass
        for pid in pids:
            if pid == os.getpid():
                continue
            try:
                psutil.Process(pid).terminate()
            except psutil.AccessDenied:
                QMessageBox.warning(self, "Task Manager", "Access is denied. This process belongs to the system.")
                return
            except psutil.Error:
                pass

        def force():
            for pid in pids:
                try:
                    if psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGKILL)
                except (OSError, psutil.Error):
                    pass
        QTimer.singleShot(3000, force)

    def go_details(self, pid):
        self.nav.setCurrentRow([k for k, *_ in PAGES].index("details"))
        self.pages["details"].update_data(self.sampler)
        self.pages["details"].select_pid(pid)

    def run_new(self):
        from .rundialog import RunDialog
        self._run = RunDialog()
        self._run.setWindowTitle("Create new task")
        self._run.show()


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("glass-taskmgr")
    app.setApplicationDisplayName("Task Manager")
    app.setDesktopFileName("glass-taskmgr")
    style.apply_app_style(app)
    w = TaskManager()
    if "--performance" in argv:
        w.nav.setCurrentRow(1)
    w.show()
    if "--screenshot" in argv:
        out = argv[argv.index("--screenshot") + 1]
        QTimer.singleShot(3500, lambda: (w.grab().save(out), app.quit()))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
