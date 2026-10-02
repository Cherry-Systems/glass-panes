"""Windows 11 controls for Glass Panes' apps: toggle switch, cards, setting rows, navigation."""
from PyQt6.QtCore import (QEasingCurve, QPropertyAnimation, QRect, QRectF, QSize, Qt, pyqtProperty,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QStyledItemDelegate, QStyle, QVBoxLayout, QWidget)

from . import style


class ToggleSwitch(QAbstractButton):
    """The Windows 11 on/off switch, with 'On'/'Off' text to its left like in Settings."""

    def __init__(self, theme, checked=False, show_text=True, parent=None):
        super().__init__(parent)
        self.t = theme
        self.setCheckable(True)
        self.setChecked(checked)
        self.show_text = show_text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.setFixedHeight(32)
        self.setFixedWidth(84 if show_text else 44)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_pos(self):
        return self._pos

    def set_pos(self, v):
        self._pos = v
        self.update()

    pos = pyqtProperty(float, get_pos, set_pos)

    def setChecked(self, on):  # noqa: N802 (Qt naming)
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = 40
        x0 = self.width() - w - 2
        track = QRectF(x0, (self.height() - 20) / 2, w, 20)
        on = self.isChecked()
        hover = self.underMouse()
        if self.show_text:
            p.setPen(QColor(t.text if self.isEnabled() else t.text_disabled))
            p.setFont(style.font())
            p.drawText(QRect(0, 0, int(x0) - 12, self.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "On" if on else "Off")
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent_hover if hover else t.accent_fill))
        else:
            p.setPen(QPen(QColor(t.text_secondary), 1))
            p.setBrush(QColor(t.subtle_hover if hover else t.control))
        p.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        d = 14 if hover else 12
        cx = track.left() + 10 + self._pos * (w - 20)
        knob = QRectF(cx - d / 2, track.center().y() - d / 2, d, d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.on_accent if on else t.text_secondary))
        p.drawEllipse(knob)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def sizeHint(self):
        return QSize(self.width(), 32)


class ComboBox(QComboBox):
    """QComboBox with the Windows 11 chevron."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.t = theme
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        px = style.icon_pixmap("chevron_down", self.t.text_secondary, 12, self.devicePixelRatioF())
        p.drawPixmap(self.width() - 24, (self.height() - 12) // 2, px)


def label(text, role=None, wrap=False):
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


def icon_label(name, color, size=20):
    lb = QLabel()
    lb.setPixmap(style.icon_pixmap(name, color, size, 2.0))
    lb.setFixedSize(size, size)
    return lb


class Card(QFrame):
    clicked = pyqtSignal()

    def __init__(self, clickable=False, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card")
        if clickable:
            self.setProperty("hover", "true")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clickable = clickable

    def mouseReleaseEvent(self, e):
        if self.clickable and e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class SettingRow(Card):
    """One row of a Settings page: icon, title, description, and a control or chevron on the right."""

    def __init__(self, theme, icon_name, title, description="", control=None, chevron=False,
                 parent=None):
        super().__init__(clickable=chevron, parent=parent)
        self.t = theme
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(16)
        if icon_name:
            if isinstance(icon_name, str):
                lay.addWidget(icon_label(icon_name, theme.text, 20))
            else:
                ic = QLabel()
                ic.setPixmap(icon_name.pixmap(24, 24))
                ic.setFixedSize(24, 24)
                lay.addWidget(ic)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title = label(title)
        text.addWidget(self.title)
        self.description = label(description, "secondary", wrap=True)
        if description:
            text.addWidget(self.description)
        lay.addLayout(text, 1)
        self.setMinimumHeight(68 if description else 56)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        if chevron:
            lay.addWidget(icon_label("chevron_right", theme.text_secondary, 14))
        self.control = control

    def set_description(self, text):
        self.description.setText(text)


class NavDelegate(QStyledItemDelegate):
    """Settings navigation item: icon + text, rounded hover, accent pill on the selected item."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.t = theme

    def paint(self, p, opt, index):
        t = self.t
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(opt.rect).adjusted(4, 2, -4, -2)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.subtle_hover if not selected else (t.card if not t.dark else "#2d2d2d")))
            p.drawRoundedRect(r, 4, 4)
        if selected:
            p.setBrush(QColor(t.accent_fill))
            p.drawRoundedRect(QRectF(r.left(), r.center().y() - 8, 3, 16), 1.5, 1.5)
        icon_name = index.data(Qt.ItemDataRole.UserRole + 1)
        color = index.data(Qt.ItemDataRole.UserRole + 2) or t.text
        if icon_name:
            px = style.icon_pixmap(icon_name, color, 18, 2.0)
            p.drawPixmap(int(r.left() + 14), int(r.center().y() - 9), px)
        p.setPen(QColor(t.text))
        f = style.font()
        if selected:
            f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(r.adjusted(46, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, index.data())
        p.restore()

    def sizeHint(self, opt, index):
        return QSize(260, 40)


class NavList(QListWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setItemDelegate(NavDelegate(theme, self))
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QListWidget { background: transparent; }")

    def add(self, text, icon_name, key, color=None):
        it = QListWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, key)
        it.setData(Qt.ItemDataRole.UserRole + 1, icon_name)
        it.setData(Qt.ItemDataRole.UserRole + 2, color)
        self.addItem(it)
        return it


def divider():
    f = QFrame()
    f.setProperty("role", "divider")
    return f


def vbox(widget=None, margins=(0, 0, 0, 0), spacing=4):
    lay = QVBoxLayout(widget) if widget is not None else QVBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay


def hbox(widget=None, margins=(0, 0, 0, 0), spacing=8):
    lay = QHBoxLayout(widget) if widget is not None else QHBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay


class Spacer(QWidget):
    pass
