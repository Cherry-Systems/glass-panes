"""The Windows right-click menus for the desktop, the empty part of the taskbar and the Recycle Bin.
Plasma's own menus are switched off for these spots (see patch-qml.py) and ask glass-shell instead."""
import os
import subprocess

from PyQt6.QtCore import QPoint, Qt, QUrl
from PyQt6.QtDBus import QDBusConnection, QDBusMessage
from PyQt6.QtGui import QActionGroup, QCursor, QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import style
from .firstlogin import desktop_dir

PLASMA = ["qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript"]
# Folder View's iconSize steps, picked to match Windows' pixel sizes on screen.
ICON_SIZES = [("Large icons", 5), ("Medium icons", 3), ("Small icons", 2)]
SORT_MODES = [("Name", 1), ("Size", 2), ("Item type", 3), ("Date modified", 4)]
TRASH = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "Trash", "files")


def run(*argv):
    return lambda: subprocess.Popen(list(argv), start_new_session=True)


def icon(name):
    return style.icon(name, style.make_theme().text, 16)


def add_submenu(menu, title, icon_name=None):
    sub = style.menu(menu)
    sub.setTitle(title)
    if icon_name:
        sub.setIcon(icon(icon_name))
    menu.addMenu(sub)
    return sub


def add_choices(menu, choices, current, choose):
    group = QActionGroup(menu)
    for label, value in choices:
        a = menu.addAction(label, lambda _checked=False, v=value: choose(v))
        a.setCheckable(True)
        a.setChecked(current == value)
        group.addAction(a)


def desktop_setting(key, default):
    script = f'var d = desktops()[0]; d.currentConfigGroup = ["General"]; print(d.readConfig("{key}"));'
    try:
        return int(subprocess.run(PLASMA + [script], capture_output=True, text=True, timeout=5).stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return default


def set_desktop_setting(key, value):
    script = ('var a = desktops(); for (var i = 0; i < a.length; i++) {'
              f' a[i].currentConfigGroup = ["General"]; a[i].writeConfig("{key}", {int(value)}); }}')
    subprocess.Popen(PLASMA + [script], stdout=subprocess.DEVNULL, start_new_session=True)


def refresh_desktop():
    for url in ("desktop:/", QUrl.fromLocalFile(desktop_dir()).toString()):
        msg = QDBusMessage.createSignal("/", "org.kde.KDirNotify", "FilesAdded")
        msg.setArguments([url])
        QDBusConnection.sessionBus().send(msg)


def unused_path(name, ext=""):
    path, n = os.path.join(desktop_dir(), name + ext), 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(desktop_dir(), f"{name} ({n}){ext}")
    return path


def new_folder():
    os.makedirs(unused_path("New folder"))


def new_text_document():
    open(unused_path("New Text Document", ".txt"), "x").close()


def add_paste(menu):
    data = QApplication.clipboard().mimeData()
    urls = [u.toString() for u in data.urls()] if data is not None and data.hasUrls() else []
    cut = data is not None and bytes(data.data("application/x-kde-cutselection")) == b"1"
    dest = QUrl.fromLocalFile(desktop_dir()).toString()
    paste = menu.addAction(icon("document"), "Paste", run("kioclient", "move" if cut else "copy", *urls, dest))
    paste.setEnabled(bool(urls))


def desktop_menu():
    m = style.menu()
    view = add_submenu(m, "View", "grid")
    add_choices(view, ICON_SIZES, desktop_setting("iconSize", 3), lambda v: set_desktop_setting("iconSize", v))
    sort = add_submenu(m, "Sort by", "task_list_ltr")
    add_choices(sort, SORT_MODES, desktop_setting("sortMode", 0), lambda v: set_desktop_setting("sortMode", v))
    m.addAction(icon("arrow_clockwise"), "Refresh", refresh_desktop)
    m.addSeparator()
    add_paste(m)
    new = add_submenu(m, "New", "add")
    new.addAction(icon("folder"), "Folder", new_folder)
    new.addSeparator()
    new.addAction(icon("document"), "Text Document", new_text_document)
    m.addSeparator()
    m.addAction(icon("desktop"), "Display settings", run("glass-settings", "--page", "display"))
    m.addAction(icon("paint_brush"), "Personalise", run("glass-settings", "--page", "personalisation"))
    m.addSeparator()
    m.addAction(icon("window_apps"), "Open in Terminal", run("konsole", "--workdir", desktop_dir()))
    m.exec(QCursor.pos())


def exec_above_taskbar(m):
    at = QCursor.pos()
    above = QGuiApplication.screenAt(at).availableGeometry().bottom() - m.sizeHint().height()
    m.exec(QPoint(at.x(), min(at.y(), above)))


def taskbar_menu():
    m = style.menu()
    m.addAction(icon("pulse"), "Task Manager", run("glass-taskmgr"))
    m.addAction(icon("settings"), "Taskbar settings", run("glass-settings", "--page", "taskbar"))
    exec_above_taskbar(m)


TRAY_MENUS = {
    "org.kde.plasma.volume": [("Open volume mixer", ("systemsettings", "kcm_pulseaudio")),
                              ("Sound settings", ("glass-settings", "--page", "sound"))],
    "org.kde.plasma.networkmanagement": [("Network and Internet settings", ("glass-settings", "--page", "network"))],
    "org.kde.plasma.battery": [("Power and sleep settings", ("glass-settings", "--page", "power"))],
}


def tray_menu(item):
    """Right-clicking the network, volume or battery icon."""
    m = style.menu()
    for text, argv in TRAY_MENUS.get(item, []):
        m.addAction(text, run(*argv))
    if not m.isEmpty():
        exec_above_taskbar(m)


def trash_items():
    try:
        return os.listdir(TRASH)
    except OSError:
        return []


def empty_recycle_bin():
    items = trash_items()
    if not items:
        return
    if len(items) > 1:
        title, text = "Delete Multiple Items", f"Are you sure you want to permanently delete these {len(items)} items?"
    elif os.path.isdir(os.path.join(TRASH, items[0])):
        title, text = "Delete Folder", "Are you sure you want to permanently delete this folder?"
    else:
        title, text = "Delete File", "Are you sure you want to permanently delete this file?"
    yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
    box = QMessageBox(QMessageBox.Icon.Warning, title, text, yes | no)
    box.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
    box.setWindowIcon(QIcon.fromTheme("user-trash-full"))
    if box.exec() == yes:
        subprocess.Popen(["ktrash6", "--empty"], start_new_session=True)


def recycle_bin_menu():
    m = style.menu()
    opener = m.addAction(icon("open"), "Open", run("dolphin", "trash:/"))
    bold = opener.font()
    bold.setBold(True)
    opener.setFont(bold)
    m.addAction(icon("delete"), "Empty Recycle Bin", empty_recycle_bin).setEnabled(bool(trash_items()))
    m.exec(QCursor.pos())
