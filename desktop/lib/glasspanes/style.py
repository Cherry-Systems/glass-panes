"""Windows 11 (WinUI / Fluent) look for Glass Panes' own apps: colours, fonts, icons, stylesheet."""
import os
from dataclasses import dataclass

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

from . import paths, prefs

FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Selawik", "Noto Sans", "DejaVu Sans"]


def _mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t)).name()


@dataclass
class Theme:
    dark: bool
    accent: str          # the user's accent colour
    accent_fill: str     # buttons / selected toggles (accent adjusted for contrast, like Windows)
    accent_hover: str
    on_accent: str       # text on accent_fill
    accent_text: str     # links / accent-coloured text
    window: str          # Mica base
    layer: str           # content area behind cards
    card: str
    card_hover: str
    card_border: str
    control: str
    control_hover: str
    control_pressed: str
    control_border: str
    subtle_hover: str
    subtle_pressed: str
    text: str
    text_secondary: str
    text_disabled: str
    divider: str
    flyout: str
    flyout_border: str
    danger: str = "#c42b1c"

    def rgba(self, color, alpha):
        c = QColor(color)
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def make_theme(mode=None, accent=None):
    p = prefs.load()
    mode = mode or p["mode"]
    accent = accent or p["accent"]
    if mode == "dark":
        fill = _mix(accent, "#ffffff", 0.45)
        return Theme(
            dark=True, accent=accent, accent_fill=fill, accent_hover=_mix(fill, "#000000", 0.1),
            on_accent="#000000", accent_text=fill,
            window="#202020", layer="#272727", card="#2b2b2b", card_hover="#323232",
            card_border="#1d1d1d", control="#2d2d2d", control_hover="#323232",
            control_pressed="#272727", control_border="#3a3a3a", subtle_hover="#2d2d2d",
            subtle_pressed="#292929", text="#ffffff", text_secondary="#c5c5c5",
            text_disabled="#787878", divider="#3a3a3a", flyout="#2c2c2c", flyout_border="#444444",
            danger="#ff99a4")
    fill = _mix(accent, "#000000", 0.08)
    return Theme(
        dark=False, accent=accent, accent_fill=fill, accent_hover=_mix(fill, "#ffffff", 0.12),
        on_accent="#ffffff", accent_text=_mix(accent, "#000000", 0.15),
        window="#f3f3f3", layer="#f9f9f9", card="#fbfbfb", card_hover="#f6f6f6",
        card_border="#e5e5e5", control="#fbfbfb", control_hover="#f6f6f6",
        control_pressed="#f5f5f5", control_border="#e0e0e0", subtle_hover="#eaeaea",
        subtle_pressed="#ededed", text="#1a1a1a", text_secondary="#5f5f5f",
        text_disabled="#a0a0a0", divider="#e5e5e5", flyout="#f9f9f9", flyout_border="#dcdcdc")


def font(size=10.5, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPointSizeF(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def load_fonts():
    """Development PCs may not have Selawik installed; load it from the build cache if so."""
    if "Selawik" in QFontDatabase.families():
        return
    cache = os.path.join(os.path.dirname(paths.DATA.rstrip("/")), "build", "cache", "fonts")
    if os.path.isdir(cache):
        for name in os.listdir(cache):
            QFontDatabase.addApplicationFont(os.path.join(cache, name))


_svg_cache = {}


def icon_pixmap(name, color, size=16, ratio=1.0):
    """A Fluent System Icon (desktop/icons/fluent/<name>.svg) drawn in `color`."""
    from PyQt6.QtSvg import QSvgRenderer
    key = (name, QColor(color).name(QColor.NameFormat.HexArgb), size, ratio)
    if key in _svg_cache:
        return _svg_cache[key]
    path = os.path.join(paths.ICONS, name + ".svg")
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        _svg_cache[key] = px
        return px
    c = QColor(color)
    data = data.replace(b"<svg ", f'<svg fill="{c.name()}" fill-opacity="{c.alphaF():.3f}" '.encode(), 1)
    renderer = QSvgRenderer(QByteArray(data))
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * ratio, size * ratio))
    p.end()
    px.setDevicePixelRatio(ratio)
    _svg_cache[key] = px
    return px


def icon(name, color, size=16):
    ic = QIcon()
    for r in (1.0, 2.0):
        ic.addPixmap(icon_pixmap(name, color, size, r))
    return ic


def app_icon(name, size=32):
    """An application icon from the icon theme (or a file path), with a generic fallback."""
    if name and os.path.isabs(name) and os.path.exists(name):
        return QIcon(name)
    ic = QIcon.fromTheme(name) if name else QIcon()
    if ic.isNull() and name and "." in name:
        ic = QIcon.fromTheme(os.path.splitext(name)[0])
    if ic.isNull():
        ic = QIcon.fromTheme("application-x-executable")
    if ic.isNull():
        ic = icon("window_apps", "#5f5f5f", size)
    return ic


def stylesheet(t):
    """Base stylesheet shared by Settings, Task Manager and Run."""
    return f"""
    * {{ color: {t.text}; }}
    QWidget#Window, QMainWindow, QDialog {{ background: {t.window}; }}
    QToolTip {{ background: {t.flyout}; color: {t.text}; border: 1px solid {t.flyout_border};
                padding: 4px 8px; border-radius: 4px; }}
    QLabel {{ background: transparent; }}
    QLabel[role="title"] {{ font-size: 21pt; font-weight: 600; }}
    QLabel[role="subtitle"] {{ font-size: 15pt; font-weight: 600; }}
    QLabel[role="section"] {{ font-size: 10.5pt; font-weight: 600; padding-top: 14px; padding-bottom: 2px; }}
    QLabel[role="secondary"] {{ color: {t.text_secondary}; font-size: 9pt; }}
    QLabel[role="link"] {{ color: {t.accent_text}; }}
    QFrame[role="card"] {{ background: {t.card}; border: 1px solid {t.card_border}; border-radius: 6px; }}
    QFrame[role="card"][hover="true"]:hover {{ background: {t.card_hover}; }}
    QFrame[role="divider"] {{ background: {t.divider}; max-height: 1px; min-height: 1px; border: none; }}
    QPushButton {{ background: {t.control}; border: 1px solid {t.control_border};
                   border-bottom-color: {_mix(t.control_border, '#000000', 0.12) if not t.dark else t.control_border};
                   border-radius: 4px; padding: 5px 14px; min-height: 20px; }}
    QPushButton:hover {{ background: {t.control_hover}; }}
    QPushButton:pressed {{ background: {t.control_pressed}; color: {t.text_secondary}; }}
    QPushButton:disabled {{ color: {t.text_disabled}; }}
    QPushButton[accent="true"] {{ background: {t.accent_fill}; color: {t.on_accent};
                                  border: 1px solid {t.accent_fill}; }}
    QPushButton[accent="true"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton[accent="true"]:disabled {{ background: {t.control_border}; border-color: {t.control_border};
                                           color: {t.text_disabled}; }}
    QPushButton[flat="true"] {{ background: transparent; border: none; }}
    QPushButton[flat="true"]:hover {{ background: {t.subtle_hover}; }}
    QPushButton[link="true"] {{ background: transparent; border: none; color: {t.accent_text}; padding: 2px 4px; }}
    QPushButton[link="true"]:hover {{ text-decoration: underline; }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
        background: {t.control}; border: 1px solid {t.control_border};
        border-bottom: 1px solid {t.text_secondary}; border-radius: 4px; padding: 5px 10px;
        selection-background-color: {t.accent_fill}; selection-color: {t.on_accent}; }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-bottom: 2px solid {t.accent_fill};
        background: {t.layer if not t.dark else '#1f1f1f'}; }}
    QComboBox {{ padding-right: 28px; min-width: 120px; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: none; width: 0; }}
    QComboBox QAbstractItemView {{ background: {t.flyout}; border: 1px solid {t.flyout_border};
        border-radius: 6px; padding: 4px; outline: none; selection-background-color: {t.subtle_hover};
        selection-color: {t.text}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {t.text_secondary}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t.accent_fill}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {t.card}; border: 5px solid {t.accent_fill};
        width: 10px; height: 10px; margin: -8px 0; border-radius: 10px; }}
    QSlider::handle:horizontal:hover {{ border-width: 4px; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.rgba(t.text, 0.35)}; border-radius: 3px; min-height: 30px;
        margin: 0 2px; }}
    QScrollBar::handle:vertical:hover {{ background: {t.rgba(t.text, 0.55)}; margin: 0; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t.rgba(t.text, 0.35)}; border-radius: 3px; min-width: 30px; }}
    QProgressBar {{ background: {t.rgba(t.text, 0.25)}; border: none; border-radius: 2px; max-height: 4px;
        min-height: 4px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background: {t.accent_fill}; border-radius: 2px; }}
    QMenu {{ background: {t.flyout}; border: 1px solid {t.flyout_border}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 4px; margin: 1px 0; }}
    QMenu::item:selected {{ background: {t.subtle_hover}; }}
    QMenu::item:disabled {{ color: {t.text_disabled}; }}
    QMenu::separator {{ height: 1px; background: {t.divider}; margin: 4px 0; }}
    QMenu::icon {{ padding-left: 10px; }}
    QTreeView, QTableView, QListView {{ background: transparent; border: none; outline: none;
        alternate-background-color: {t.rgba(t.text, 0.02)}; }}
    QListView#popup {{ background: {t.flyout}; border: 1px solid {t.flyout_border}; border-radius: 6px;
        padding: 4px; color: {t.text}; }}
    QListView#popup::item {{ padding: 6px 10px; border-radius: 4px; }}
    QListView#popup::item:hover, QListView#popup::item:selected {{ background: {t.subtle_hover};
        color: {t.text}; }}
    QTreeView::item, QTableView::item {{ padding: 4px; border: none; }}
    QTreeView::item:hover, QTableView::item:hover {{ background: {t.subtle_hover}; }}
    QTreeView::item:selected, QTableView::item:selected {{ background: {t.rgba(t.accent_fill, 0.22)};
        color: {t.text}; }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{ background: transparent; border: none; border-right: 1px solid {t.divider};
        border-bottom: 1px solid {t.divider}; padding: 6px 8px; color: {t.text}; font-weight: 400; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; }}
    QCheckBox::indicator {{ border: 1px solid {t.text_secondary}; border-radius: 4px; background: {t.control}; }}
    QCheckBox::indicator:checked {{ background: {t.accent_fill}; border-color: {t.accent_fill};
        image: url({_check_png(t)}); }}
    QRadioButton::indicator {{ border: 1px solid {t.text_secondary}; border-radius: 10px; background: {t.control}; }}
    QRadioButton::indicator:checked {{ border: 5px solid {t.accent_fill}; background: {t.on_accent}; }}
    """


def _check_png(t):
    """Writes a white checkmark PNG for checkbox indicators (QSS needs a file)."""
    out_dir = os.path.join(paths.STATE, "cache")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"check-{QColor(t.on_accent).name()[1:]}.png")
    if not os.path.exists(out):
        icon_pixmap("checkmark", t.on_accent, 14, 1.0).save(out)
    return out


def kde_icon_theme():
    import configparser
    for path in (os.path.expanduser("~/.config/kdeglobals"), "/etc/xdg/kdeglobals"):
        cp = configparser.RawConfigParser(strict=False, interpolation=None)
        try:
            cp.read(path)
            if cp.has_option("Icons", "Theme"):
                return cp.get("Icons", "Theme")
        except configparser.Error:
            continue
    return "Win11"


def menu(parent=None):
    """A Windows 11 pop-up menu: the flyout colours, with see-through corners so they show rounded."""
    from PyQt6.QtWidgets import QMenu
    m = QMenu(parent)
    m.setStyleSheet(stylesheet(make_theme()))
    m.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return m


def windows_style():
    """Fusion, except that clicking a slider's track jumps the thumb there, like Windows."""
    from PyQt6.QtWidgets import QProxyStyle, QStyle

    class WindowsStyle(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, data=None):
            if hint == QStyle.StyleHint.SH_Slider_AbsoluteSetButtons:
                return Qt.MouseButton.LeftButton.value
            return super().styleHint(hint, option, widget, data)

    return WindowsStyle("Fusion")


def apply_app_style(app, t=None):
    t = t or make_theme()
    load_fonts()
    if not QIcon.themeName() or QIcon.themeName() == "hicolor":
        QIcon.setThemeName(kde_icon_theme())
    QIcon.setFallbackThemeName("breeze")
    app.setFont(font())
    app.setStyle(windows_style())
    from PyQt6.QtGui import QPalette
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t.window))
    pal.setColor(QPalette.ColorRole.Base, QColor(t.card))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t.layer))
    pal.setColor(QPalette.ColorRole.Text, QColor(t.text))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Button, QColor(t.control))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t.accent_fill))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t.on_accent))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_secondary))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.flyout))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Link, QColor(t.accent_text))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(t))
    return t


ICON_SIZE = QSize(16, 16)
