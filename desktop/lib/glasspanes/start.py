"""The Windows 11 Start menu: search, Pinned, Recommended, All apps, account and power.

Runs inside glass-shell (shell.py), which keeps it loaded so it opens instantly.
`python3 -m glasspanes.start --show` opens it on its own for trying out."""
import ast
import datetime
import operator
import os
import subprocess
import sys
import threading
import urllib.parse
from xml.etree import ElementTree

from PyQt6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
                          QUrl, pyqtSignal)
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics, QGuiApplication, QIcon,
                         QPainter, QPainterPath, QPen, QPixmap)
from PyQt6.QtWidgets import (QApplication, QFileIconProvider, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton,
                             QScrollArea, QStackedWidget, QStyle, QStyledItemDelegate, QToolButton,
                             QVBoxLayout, QWidget)

from . import apps as appdb
from . import paths, prefs, session, settings_index, style, x11

W, H = 642, 726
COLS = 6


def start_colors(t):
    if t.dark:
        return dict(bg=QColor(32, 32, 32, 236), border=QColor(70, 70, 70), bar=QColor(28, 28, 28, 240),
                    hover="rgba(255,255,255,0.07)", press="rgba(255,255,255,0.04)",
                    search="#1f1f1f", search_border="#3d3d3d", chip="rgba(255,255,255,0.08)")
    return dict(bg=QColor(242, 242, 242, 238), border=QColor(212, 212, 212), bar=QColor(233, 233, 233, 245),
                hover="rgba(0,0,0,0.05)", press="rgba(0,0,0,0.03)", search="#ffffff",
                search_border="#d6d6d6", chip="rgba(255,255,255,0.75)")


def circle_pixmap(path, size, ratio=2.0):
    src = QPixmap(path) if path else QPixmap()
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addEllipse(QRectF(0, 0, size * ratio, size * ratio))
    p.setClipPath(clip)
    if not src.isNull():
        s = src.scaled(px.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((px.width() - s.width()) // 2, (px.height() - s.height()) // 2, s)
    else:
        p.fillRect(px.rect(), QColor("#c8cdd4"))
    p.end()
    px.setDevicePixelRatio(ratio)
    return px


# ----------------------------------------------------------------------------- calculator

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv}


def calculate(expr):
    """Evaluates simple arithmetic typed into search ('12*3+4'); None if it isn't arithmetic."""
    e = expr.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "")
    if not e or not any(c.isdigit() for c in e) or not any(c in "+-*/%" for c in e):
        return None
    if any(c not in "0123456789.+-*/%() " for c in e):
        return None
    try:
        node = ast.parse(e, mode="eval").body
    except SyntaxError:
        return None

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            left, right = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(right) > 100:
                raise ValueError
            return _OPS[type(n.op)](left, right)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError
    try:
        v = ev(node)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if isinstance(v, float):
        v = round(v, 10)
        if v.is_integer():
            v = int(v)
    return f"{v:,}" if isinstance(v, int) else f"{v:,.10g}"


# ----------------------------------------------------------------------------- recent files

def recent_files(limit=12):
    path = os.path.expanduser("~/.local/share/recently-used.xbel")
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return []
    items = []
    for bm in root.findall("bookmark"):
        href = bm.get("href", "")
        if not href.startswith("file://"):
            continue
        p = urllib.parse.unquote(href[7:])
        if not os.path.exists(p) or os.path.isdir(p):
            continue
        stamp = bm.get("modified") or bm.get("visited") or bm.get("added") or ""
        try:
            when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            when = datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc)
        items.append((when, p))
    items.sort(key=lambda x: x[0], reverse=True)
    seen, out = set(), []
    for when, p in items:
        if p not in seen:
            seen.add(p)
            out.append((when, p))
    return out[:limit]


def friendly_time(when):
    now = datetime.datetime.now(datetime.timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    delta = now - when
    local = when.astimezone()
    if delta.days < 1 and local.date() == datetime.datetime.now().date():
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return "Just now"
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins // 60}h ago"
    if delta.days < 2:
        return "Yesterday at " + local.strftime("%-I:%M %p")
    return local.strftime("%-d %B")


class FileIndex:
    """Background list of the files in the user's folders, for 'Documents' search results."""

    def __init__(self):
        self.files = []
        self._thread = None

    def refresh(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._scan, daemon=True)
        self._thread.start()

    def _scan(self):
        home = os.path.expanduser("~")
        out, budget = [], 20000
        for top in ("Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos"):
            root = os.path.join(home, top)
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fn in files:
                    if not fn.startswith("."):
                        out.append(os.path.join(dirpath, fn))
                budget -= len(files) + 1
                if budget < 0:
                    break
        self.files = out

    def search(self, q, limit=5):
        q = q.lower()
        hits = [f for f in self.files if q in os.path.basename(f).lower()]
        hits.sort(key=lambda f: (not os.path.basename(f).lower().startswith(q), len(f)))
        return hits[:limit]


_icon_provider = None


def file_icon(path):
    global _icon_provider
    from PyQt6.QtCore import QFileInfo, QMimeDatabase
    mime = QMimeDatabase().mimeTypeForFile(path)
    ic = QIcon.fromTheme(mime.iconName())
    if ic.isNull():
        ic = QIcon.fromTheme(mime.genericIconName())
    if ic.isNull():
        if _icon_provider is None:
            _icon_provider = QFileIconProvider()
        ic = _icon_provider.icon(QFileInfo(path))
    return ic


# ----------------------------------------------------------------------------- widgets

class Tile(QToolButton):
    """A pinned app: 32px icon above its name."""

    def __init__(self, app, colors, menu_cb):
        super().__init__()
        self.app = app
        self.setFixedSize(96, 84)
        self.setIcon(style.app_icon(app.icon, 32))
        self.setIconSize(QSize(32, 32))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        fm = QFontMetrics(style.font(9))
        self.setText(fm.elidedText(app.name, Qt.TextElideMode.ElideRight, 88))
        self.setToolTip(app.name)
        self.setFont(style.font(9))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; background: transparent; padding-top: 10px; }}"
            f"QToolButton:hover {{ background: {colors['hover']}; }}"
            f"QToolButton:pressed {{ background: {colors['press']}; }}")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: menu_cb(self.app, self.mapToGlobal(pos)))


class ItemButton(QPushButton):
    """An icon + title (+ subtitle) row button, used for Recommended and All apps."""

    def __init__(self, icon, title, subtitle, colors, t, icon_size=32, height=52):
        super().__init__()
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icon.pixmap(icon_size, icon_size))
        ic.setFixedSize(icon_size, icon_size)
        ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(ic)
        text = QVBoxLayout()
        text.setSpacing(0)
        fm = QFontMetrics(style.font(9.5))
        name = QLabel(fm.elidedText(title, Qt.TextElideMode.ElideRight, 200 if subtitle else 460))
        name.setFont(style.font(9.5 if subtitle else 10))
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text.addWidget(name)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(style.font(8.5))
            sub.setStyleSheet(f"color: {t.text_secondary};")
            sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            text.addWidget(sub)
        lay.addLayout(text, 1)
        self.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 4px; background: transparent; text-align: left; }}"
            f"QPushButton:hover {{ background: {colors['hover']}; }}"
            f"QPushButton:pressed {{ background: {colors['press']}; }}")


class ResultDelegate(QStyledItemDelegate):
    def __init__(self, t, colors, parent=None):
        super().__init__(parent)
        self.t = t
        self.c = colors

    def paint(self, p, opt, index):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        kind = index.data(Qt.ItemDataRole.UserRole + 1)
        r = QRectF(opt.rect)
        if kind == "header":
            p.setPen(QColor(self.t.text))
            p.setFont(style.font(9.5, QFont.Weight.DemiBold))
            p.drawText(r.adjusted(12, 6, 0, 0), Qt.AlignmentFlag.AlignVCenter, index.data())
            p.restore()
            return
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        best = kind == "best"
        rr = r.adjusted(4, 1, -4, -1)
        if selected or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 18) if not self.t.dark else QColor(255, 255, 255, 22))
            p.drawRoundedRect(rr, 4, 4)
        if selected:
            p.setBrush(QColor(self.t.accent_fill))
            p.drawRoundedRect(QRectF(rr.left(), rr.center().y() - 8, 3, 16), 1.5, 1.5)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        isz = 32 if best else 24
        if isinstance(icon, QIcon):
            icon.paint(p, int(rr.left() + 14), int(rr.center().y() - isz / 2), isz, isz)
        p.setPen(QColor(self.t.text))
        p.setFont(style.font(10.5 if best else 9.5, QFont.Weight.DemiBold if best else QFont.Weight.Normal))
        sub = index.data(Qt.ItemDataRole.UserRole + 2) or ""
        tx = rr.adjusted(26 + isz, 0, -8, 0)
        if sub:
            p.drawText(tx.adjusted(0, 0, 0, -rr.height() / 2 + 2), Qt.AlignmentFlag.AlignBottom,
                       QFontMetrics(p.font()).elidedText(index.data(), Qt.TextElideMode.ElideRight,
                                                         int(tx.width())))
            p.setPen(QColor(self.t.text_secondary))
            p.setFont(style.font(8.5))
            p.drawText(tx.adjusted(0, rr.height() / 2 + 1, 0, 0), Qt.AlignmentFlag.AlignTop, sub)
        else:
            p.drawText(tx, Qt.AlignmentFlag.AlignVCenter, index.data())
        p.restore()

    def sizeHint(self, opt, index):
        kind = index.data(Qt.ItemDataRole.UserRole + 1)
        return QSize(260, {"header": 34, "best": 64}.get(kind, 44))


# ----------------------------------------------------------------------------- Start menu

class StartMenu(QWidget):
    closed = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self.setWindowTitle("Start")
        self.files = FileIndex()
        self.results = []
        self._hidden_at = 0
        self._anim = None
        self._win_key_alone = False
        self.build()
        # The popup grabs the keyboard, so the global Windows-key shortcut can't close it.
        QApplication.instance().installEventFilter(self)

    # -- construction -------------------------------------------------------
    def build(self):
        self.p = prefs.load()
        self.t = style.make_theme()
        self.c = start_colors(self.t)
        for child in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.deleteLater()
        if self.layout():
            QWidget().setLayout(self.layout())
        t, c = self.t, self.c
        self.setStyleSheet(f"* {{ color: {t.text}; }} QLabel {{ background: transparent; }}")
        self.setFont(style.font())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(32, 30, 32, 0)
        bl.setSpacing(0)

        # Search box
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search for apps, settings, and documents")
        self.search.setFixedHeight(36)
        self.search.setTextMargins(32, 0, 12, 0)
        self.search.setStyleSheet(
            f"QLineEdit {{ background: {c['search']}; border: 1px solid {c['search_border']};"
            f" border-radius: 18px; padding: 0 8px; font-size: 10pt; }}"
            f"QLineEdit:focus {{ border-bottom: 2px solid {t.accent_fill}; }}")
        glass = QLabel(self.search)
        glass.setPixmap(style.icon_pixmap("search", t.text_secondary, 16, 2.0))
        glass.move(14, 10)
        glass.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.search.textChanged.connect(self.on_search)
        self.search.returnPressed.connect(self.activate_first)
        self.search.installEventFilter(self)
        bl.addWidget(self.search)
        bl.addSpacing(18)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_home())
        self.stack.addWidget(self.build_all_apps())
        self.stack.addWidget(self.build_search_page())
        bl.addWidget(self.stack, 1)
        outer.addWidget(body, 1)

        outer.addWidget(self.build_bar())

    def section_header(self, title, button_text=None, button_cb=None, back=False):
        row = QHBoxLayout()
        row.setContentsMargins(20, 0, 20, 0)
        lb = QLabel(title)
        lb.setFont(style.font(10.5, QFont.Weight.DemiBold))
        row.addWidget(lb)
        row.addStretch(1)
        if button_text:
            b = QPushButton(("  " if back else "") + button_text + ("" if back else "  "))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(style.font(9))
            b.setIcon(style.icon("chevron_left" if back else "chevron_right", self.t.text, 10))
            b.setIconSize(QSize(10, 10))
            if not back:
                b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            b.setFixedHeight(26)
            b.setStyleSheet(
                f"QPushButton {{ background: {self.c['chip']}; border: 1px solid "
                f"{'rgba(0,0,0,0.06)' if not self.t.dark else 'rgba(255,255,255,0.06)'};"
                f" border-radius: 4px; padding: 0 8px; }}"
                f"QPushButton:hover {{ background: {self.c['hover']}; }}")
            b.clicked.connect(button_cb)
            row.addWidget(b)
        return row

    def build_home(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addLayout(self.section_header("Pinned", "All apps", lambda: self.stack.setCurrentIndex(1)))
        self.pinned_area = QScrollArea()
        self.pinned_area.setWidgetResizable(True)
        self.pinned_area.setFrameShape(QFrame.Shape.NoFrame)
        self.pinned_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pinned_area.setStyleSheet("QScrollArea { background: transparent; }" + self._scroll_qss())
        self.pinned_area.setFixedHeight(3 * 84 + 14)
        lay.addWidget(self.pinned_area)
        lay.addSpacing(10)
        self.recommended_header = QWidget()
        rh = QVBoxLayout(self.recommended_header)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.addLayout(self.section_header("Recommended"))
        lay.addWidget(self.recommended_header)
        self.recommended = QWidget()
        self.recommended_layout = QGridLayout(self.recommended)
        self.recommended_layout.setContentsMargins(8, 4, 8, 0)
        self.recommended_layout.setHorizontalSpacing(8)
        self.recommended_layout.setVerticalSpacing(4)
        lay.addWidget(self.recommended)
        lay.addStretch(1)
        return page

    def build_all_apps(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addLayout(self.section_header("All apps", "Back", lambda: self.stack.setCurrentIndex(0),
                                          back=True))
        self.all_area = QScrollArea()
        self.all_area.setWidgetResizable(True)
        self.all_area.setFrameShape(QFrame.Shape.NoFrame)
        self.all_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.all_area.setStyleSheet("QScrollArea { background: transparent; }" + self._scroll_qss())
        lay.addWidget(self.all_area, 1)
        return page

    def build_search_page(self):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 12)
        lay.setSpacing(12)
        self.result_list = QListWidget()
        self.result_list.setItemDelegate(ResultDelegate(self.t, self.c, self.result_list))
        self.result_list.setMouseTracking(True)
        self.result_list.setFrameShape(QFrame.Shape.NoFrame)
        self.result_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_list.setStyleSheet("QListWidget { background: transparent; outline: none; }"
                                       + self._scroll_qss())
        self.result_list.currentRowChanged.connect(self.show_details)
        self.result_list.itemClicked.connect(lambda it: self.activate(self.result_list.row(it)))
        self.result_list.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.result_list, 11)

        self.details = QFrame()
        self.details.setStyleSheet(
            f"QFrame#details {{ background: {'rgba(255,255,255,0.6)' if not self.t.dark else 'rgba(255,255,255,0.04)'};"
            f" border-radius: 8px; }}")
        self.details.setObjectName("details")
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(16, 28, 16, 16)
        dl.setSpacing(6)
        self.d_icon = QLabel()
        self.d_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.d_icon.setFixedHeight(72)
        dl.addWidget(self.d_icon)
        self.d_title = QLabel()
        self.d_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.d_title.setWordWrap(True)
        self.d_title.setFont(style.font(13, QFont.Weight.DemiBold))
        dl.addWidget(self.d_title)
        self.d_kind = QLabel()
        self.d_kind.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.d_kind.setStyleSheet(f"color: {self.t.text_secondary};")
        dl.addWidget(self.d_kind)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {self.t.divider};")
        dl.addSpacing(10)
        dl.addWidget(line)
        dl.addSpacing(6)
        self.d_actions = QVBoxLayout()
        self.d_actions.setSpacing(2)
        dl.addLayout(self.d_actions)
        dl.addStretch(1)
        lay.addWidget(self.details, 9)
        return page

    def build_bar(self):
        bar = QFrame()
        bar.setObjectName("bar")
        bar.setFixedHeight(64)
        bar.setStyleSheet("QFrame#bar { background: transparent; }")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(52, 0, 52, 0)
        user = QPushButton("  " + session.user_name())
        user.setIcon(QIcon(circle_pixmap(session.user_picture(), 32)))
        user.setIconSize(QSize(32, 32))
        user.setFixedHeight(40)
        user.setCursor(Qt.CursorShape.PointingHandCursor)
        user.setFont(style.font(9.5))
        user.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 4px; padding: 0 12px; background: transparent; }}"
            f"QPushButton:hover {{ background: {self.c['hover']}; }}")
        user.clicked.connect(lambda: self.user_menu(user))
        lay.addWidget(user)
        lay.addStretch(1)
        power = QPushButton()
        power.setIcon(style.icon("power", self.t.text, 16))
        power.setIconSize(QSize(16, 16))
        power.setFixedSize(40, 40)
        power.setToolTip("Power")
        power.setCursor(Qt.CursorShape.PointingHandCursor)
        power.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 4px; background: transparent; }}"
            f"QPushButton:hover {{ background: {self.c['hover']}; }}")
        power.clicked.connect(lambda: self.power_menu(power))
        lay.addWidget(power)
        return bar

    def _scroll_qss(self):
        h = "rgba(0,0,0,0.35)" if not self.t.dark else "rgba(255,255,255,0.35)"
        return (f"QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}"
                f"QScrollBar::handle:vertical {{ background: {h}; border-radius: 2px; min-height: 30px;"
                f" margin: 0 2px; }}"
                f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}"
                f"QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}")

    # -- content ------------------------------------------------------------
    def refresh(self):
        self.p = prefs.load()
        self.apps = appdb.all_apps()
        self.fill_pinned()
        self.fill_recommended()
        self.fill_all_apps()
        self.files.refresh()

    def fill_pinned(self):
        grid_host = QWidget()
        grid_host.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(4, 0, 4, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)
        n = 0
        for did in self.p["pinned"]:
            app = self.apps.get(did) or appdb.find(did)
            if not app:
                continue
            tile = Tile(app, self.c, self.app_menu)
            tile.clicked.connect(lambda _=False, a=app: self.launch(a))
            grid.addWidget(tile, n // COLS, n % COLS)
            n += 1
        for i in range(n, COLS):
            spacer = QWidget()
            spacer.setFixedSize(96, 84)
            grid.addWidget(spacer, 0, i)
        grid.setRowStretch(max(1, (n + COLS - 1) // COLS), 1)
        self.pinned_area.setWidget(grid_host)

    def fill_recommended(self):
        lay = self.recommended_layout
        while lay.count():
            w = lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        show = self.p.get("show_recommended", True)
        self.recommended_header.setVisible(show)
        self.recommended.setVisible(show)
        if not show:
            return
        items = recent_files(6)
        if not items:
            empty = QLabel("The more you use your device, the more we'll show your new apps\n"
                           "and recent files here.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {self.t.text_secondary}; padding: 24px;")
            empty.setFont(style.font(9))
            lay.addWidget(empty, 0, 0, 1, 2)
            return
        for i, (when, path) in enumerate(items):
            b = ItemButton(file_icon(path), os.path.basename(path), friendly_time(when), self.c, self.t)
            b.clicked.connect(lambda _=False, p=path: self.open_path(p))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda pos, p=path, w=b: self.file_menu(p, w.mapToGlobal(pos)))
            lay.addWidget(b, i // 2, i % 2)

    def fill_all_apps(self):
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(8, 0, 8, 8)
        lay.setSpacing(0)
        letter = None
        for app in appdb.sorted_apps(self.apps):
            first = app.name[:1].upper()
            first = first if first.isalpha() else "#"
            if first != letter:
                letter = first
                lb = QLabel(letter)
                lb.setFont(style.font(9.5, QFont.Weight.DemiBold))
                lb.setContentsMargins(14, 10, 0, 4)
                lay.addWidget(lb)
            b = ItemButton(style.app_icon(app.icon, 24), app.name, "", self.c, self.t,
                           icon_size=24, height=40)
            b.clicked.connect(lambda _=False, a=app: self.launch(a))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda pos, a=app, w=b: self.app_menu(a, w.mapToGlobal(pos)))
            lay.addWidget(b)
        lay.addStretch(1)
        self.all_area.setWidget(host)

    # -- search ---------------------------------------------------------------
    def on_search(self, text):
        q = text.strip()
        if not q:
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(2)
        results = []
        calc = calculate(q)
        if calc is not None:
            results.append(dict(kind="calc", title=f"= {calc}", sub="Calculator · Press Enter to copy",
                                icon=style.app_icon("accessories-calculator"), value=calc))
        matched = sorted((a for a in self.apps.values() if a.matches(q)),
                         key=lambda a: (-a.score(q), a.name.lower()))
        for a in matched[:8]:
            results.append(dict(kind="app", title=a.name, sub="App", icon=style.app_icon(a.icon, 32),
                                app=a))
        settings_hits = [dict(kind="setting", title=title, sub="System settings",
                              icon=style.icon(icon, self.t.accent_text, 24), page=page)
                         for title, page, icon in settings_index.search(q, 4)]
        ql = q.lower()
        if calc is None and settings_hits and \
                any(w.startswith(ql) for w in settings_hits[0]["title"].lower().split()) and \
                not (matched and matched[0].score(q) >= 60):
            results.insert(0, settings_hits.pop(0))
        results.extend(settings_hits)
        for f in self.files.search(q, 5):
            results.append(dict(kind="file", title=os.path.basename(f),
                                sub=os.path.dirname(f).replace(os.path.expanduser("~"), "This PC"),
                                icon=file_icon(f), path=f))
        results.append(dict(kind="web", title=q, sub="See web results",
                            icon=style.icon("search", self.t.text, 24), query=q))
        self.results = results
        self.populate_results()

    def populate_results(self):
        lst = self.result_list
        lst.blockSignals(True)
        lst.clear()
        headers = {"calc": "Best match", "app": "Apps", "setting": "Settings", "file": "Documents",
                   "web": "Search the web"}
        first = True
        last_kind = None
        self.row_to_result = {}
        for i, r in enumerate(self.results):
            if first:
                h = QListWidgetItem("Best match")
                h.setData(Qt.ItemDataRole.UserRole + 1, "header")
                h.setFlags(Qt.ItemFlag.NoItemFlags)
                lst.addItem(h)
            elif r["kind"] != last_kind:
                h = QListWidgetItem(headers[r["kind"]])
                h.setData(Qt.ItemDataRole.UserRole + 1, "header")
                h.setFlags(Qt.ItemFlag.NoItemFlags)
                lst.addItem(h)
            it = QListWidgetItem(r["title"])
            it.setData(Qt.ItemDataRole.DecorationRole, r["icon"])
            it.setData(Qt.ItemDataRole.UserRole + 1, "best" if first else r["kind"])
            it.setData(Qt.ItemDataRole.UserRole + 2, r["sub"])
            lst.addItem(it)
            self.row_to_result[lst.count() - 1] = i
            last_kind = None if first else r["kind"]
            first = False
        lst.blockSignals(False)
        if self.row_to_result:
            lst.setCurrentRow(min(self.row_to_result))

    def show_details(self, row):
        idx = self.row_to_result.get(row) if hasattr(self, "row_to_result") else None
        while self.d_actions.count():
            w = self.d_actions.takeAt(0).widget()
            if w:
                w.deleteLater()
        if idx is None:
            return
        r = self.results[idx]
        self.d_icon.setPixmap(r["icon"].pixmap(64, 64))
        self.d_title.setText(r["title"])
        self.d_kind.setText(r["sub"] if r["kind"] != "file" else "Document")
        actions = [("Open", "open", lambda: self.activate(row))]
        if r["kind"] == "app":
            a = r["app"]
            pinned = a.id in self.p["pinned"]
            actions.append(("Unpin from Start" if pinned else "Pin to Start", "pin",
                            lambda: self.toggle_pin(a)))
            actions.append(("Pin to taskbar", "pin", lambda: (appdb.pin_to_taskbar(a.id), self.hide_menu())))
            actions.append(("Uninstall", "delete", lambda: self.uninstall(a)))
        elif r["kind"] == "file":
            actions.append(("Open file location", "folder", lambda: self.show_in_folder(r["path"])))
            actions.append(("Copy path", "document", lambda: QGuiApplication.clipboard().setText(r["path"])))
        elif r["kind"] == "calc":
            actions = [("Copy", "document", lambda: self.activate(row))]
        for text, icon, cb in actions:
            b = QPushButton("   " + text)
            b.setIcon(style.icon(icon, self.t.text, 16))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(36)
            b.setStyleSheet(
                f"QPushButton {{ border: none; border-radius: 4px; text-align: left; padding-left: 12px;"
                f" background: transparent; }} QPushButton:hover {{ background: {self.c['hover']}; }}")
            b.clicked.connect(cb)
            self.d_actions.addWidget(b)

    def activate_first(self):
        if self.stack.currentIndex() == 2:
            row = self.result_list.currentRow()
            if row in getattr(self, "row_to_result", {}):
                self.activate(row)

    def activate(self, row):
        idx = self.row_to_result.get(row)
        if idx is None:
            return
        r = self.results[idx]
        k = r["kind"]
        if k == "app":
            self.launch(r["app"])
        elif k == "setting":
            self.run(["glass-settings", "--page", r["page"]])
        elif k == "file":
            self.open_path(r["path"])
        elif k == "calc":
            QGuiApplication.clipboard().setText(r["value"].replace(",", ""))
            self.hide_menu()
        elif k == "web":
            engines = {"bing": "https://www.bing.com/search?q=",
                       "google": "https://www.google.com/search?q=",
                       "duckduckgo": "https://duckduckgo.com/?q="}
            base = engines.get(self.p.get("search_engine"), engines["bing"])
            QDesktopServices.openUrl(QUrl(base + urllib.parse.quote(r["query"])))
            self.hide_menu()

    # -- actions --------------------------------------------------------------
    def launch(self, app):
        app.launch()
        self.hide_menu()

    def run(self, argv):
        try:
            subprocess.Popen(argv, start_new_session=True)
        except OSError:
            pass
        self.hide_menu()

    def open_path(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        self.hide_menu()

    def show_in_folder(self, path):
        self.run(["dolphin", "--select", path])

    def toggle_pin(self, app):
        pinned = list(self.p["pinned"])
        if app.id in pinned:
            pinned.remove(app.id)
        else:
            pinned.append(app.id)
        self.p = prefs.update(pinned=pinned)
        self.fill_pinned()
        if self.stack.currentIndex() == 2:
            self.show_details(self.result_list.currentRow())

    def uninstall(self, app):
        self.run(["glass-settings", "--uninstall", app.id])

    def app_menu(self, app, pos):
        m = QMenu(self)
        pinned = app.id in self.p["pinned"]
        m.addAction(style.icon("pin", self.t.text, 16), "Unpin from Start" if pinned else "Pin to Start",
                    lambda: self.toggle_pin(app))
        m.addAction(style.icon("pin", self.t.text, 16), "Pin to taskbar",
                    lambda: (appdb.pin_to_taskbar(app.id), self.hide_menu()))
        if pinned and self.p["pinned"].index(app.id) > 0:
            m.addAction(style.icon("arrow_up", self.t.text, 16), "Move to front",
                        lambda: self.move_front(app))
        m.addSeparator()
        m.addAction(style.icon("delete", self.t.text, 16), "Uninstall", lambda: self.uninstall(app))
        m.exec(pos)

    def file_menu(self, path, pos):
        m = QMenu(self)
        m.addAction(style.icon("open", self.t.text, 16), "Open", lambda: self.open_path(path))
        m.addAction(style.icon("folder", self.t.text, 16), "Open file location",
                    lambda: self.show_in_folder(path))
        m.exec(pos)

    def move_front(self, app):
        pinned = [p for p in self.p["pinned"] if p != app.id]
        self.p = prefs.update(pinned=[app.id] + pinned)
        self.fill_pinned()

    def user_menu(self, button):
        m = QMenu(self)
        m.addAction(style.icon("person_circle", self.t.text, 16), "Change account settings",
                    lambda: self.run(["glass-settings", "--page", "accounts"]))
        m.addAction(style.icon("lock_closed", self.t.text, 16), "Lock", lambda: (self.hide_menu(), session.lock()))
        m.addAction(style.icon("sign_out", self.t.text, 16), "Sign out",
                    lambda: (self.hide_menu(), session.sign_out()))
        m.exec(button.mapToGlobal(QPoint(0, -m.sizeHint().height() - 6)))

    def power_menu(self, button):
        m = QMenu(self)
        m.addAction(style.icon("lock_closed", self.t.text, 16), "Sign-in options",
                    lambda: self.run(["glass-settings", "--page", "accounts"]))
        m.addSeparator()
        m.addAction(style.icon("weather_moon", self.t.text, 16), "Sleep", lambda: (self.hide_menu(), session.sleep()))
        m.addAction(style.icon("power", self.t.text, 16), "Shut down",
                    lambda: (self.hide_menu(), session.shut_down()))
        m.addAction(style.icon("arrow_clockwise", self.t.text, 16), "Restart",
                    lambda: (self.hide_menu(), session.restart()))
        m.exec(button.mapToGlobal(QPoint(0, -m.sizeHint().height() - 6)))

    # -- showing / hiding -----------------------------------------------------
    def toggle(self):
        import time
        if self.isVisible():
            self.hide_menu()
        elif time.monotonic() - self._hidden_at > 0.3:
            self.show_menu()

    def show_menu(self, search_text=None):
        p = prefs.load()
        t = style.make_theme()
        if (t.dark, t.accent) != (self.t.dark, self.t.accent) or p.get("transparency") != self.p.get("transparency"):
            self.build()
        self.refresh()
        self.stack.setCurrentIndex(0)
        self.search.clear()
        screen = QGuiApplication.screenAt(QGuiApplication.primaryScreen().geometry().center()) \
            or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        if self.p.get("taskbar_align") == "left":
            x = avail.left() + 12
        else:
            x = avail.center().x() - W // 2
        y = avail.bottom() - H - 11
        end = QPoint(x, y)
        self.move(end + QPoint(0, 40))
        self.setWindowOpacity(0.0)
        self.show()
        x11.enable_blur(int(self.winId()), self.p.get("transparency", True))
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        if search_text:
            self.search.setText(search_text)
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(end + QPoint(0, 40))
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._anim.start()
        self._fade.start()

    def hide_menu(self):
        if self.isVisible():
            self.hide()

    def hideEvent(self, e):
        import time
        self._hidden_at = time.monotonic()
        self.closed.emit()
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            if self.stack.currentIndex() == 1 and not self.search.text():
                self.stack.setCurrentIndex(0)
            else:
                self.hide_menu()
            return
        super().keyPressEvent(e)

    def eventFilter(self, obj, e):
        from PyQt6.QtCore import QEvent
        if self.isVisible() and e.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) \
                and not e.isAutoRepeat():
            win_key = e.key() in (Qt.Key.Key_Meta, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R)
            if e.type() == QEvent.Type.KeyPress:
                self._win_key_alone = win_key
            elif win_key and self._win_key_alone:
                self._win_key_alone = False
                self.hide_menu()
                return True
        if obj is self.search and e.type() == QEvent.Type.KeyPress and self.stack.currentIndex() == 2:
            if e.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                lst = self.result_list
                rows = sorted(self.row_to_result)
                if rows:
                    cur = lst.currentRow()
                    pos = rows.index(cur) if cur in rows else 0
                    pos = min(len(rows) - 1, pos + 1) if e.key() == Qt.Key.Key_Down else max(0, pos - 1)
                    lst.setCurrentRow(rows[pos])
                return True
        return super().eventFilter(obj, e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(self.c["bg"])
        if not self.p.get("transparency", True):
            bg.setAlpha(255)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.fillPath(path, bg)
        # bottom account/power bar
        p.save()
        p.setClipPath(path)
        bar = QRectF(r.left(), r.bottom() - 64, r.width(), 64)
        p.fillRect(bar, self.c["bar"])
        p.setPen(QPen(self.c["border"], 1))
        p.drawLine(bar.topLeft(), bar.topRight())
        p.restore()
        p.setPen(QPen(self.c["border"], 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 8, 8)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("glass-start")
    style.apply_app_style(app)
    menu = StartMenu()
    menu.show_menu(search_text=sys.argv[sys.argv.index("--search") + 1] if "--search" in sys.argv else None)
    menu.closed.connect(app.quit)
    if "--screenshot" in sys.argv:
        out = sys.argv[sys.argv.index("--screenshot") + 1]
        QTimer.singleShot(900, lambda: (menu.grab().save(out), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
