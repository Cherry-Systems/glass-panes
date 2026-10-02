"""Windows app support: opens .exe/.msi/.bat/.lnk files with Wine the way Windows would.

The first time, it creates the Windows environment (~/.wine, the C: drive) with a progress window,
using the .NET (Mono) and web (Gecko) add-ons shipped on the system so nothing is downloaded, then
gives Windows programs the Windows 11 'Light' look and Segoe UI-compatible fonts."""
import os
import subprocess
import sys
import tempfile
import time

PREFIX = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
ENV = dict(os.environ, WINEPREFIX=PREFIX, WINEDEBUG=os.environ.get("WINEDEBUG", "-all"))

REG = r"""REGEDIT4

[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\ThemeManager]
"ColorName"="NormalColor"
"DllName"="C:\\windows\\resources\\themes\\light\\light.msstyles"
"SizeName"="NormalSize"
"ThemeActive"="1"

[HKEY_CURRENT_USER\Software\Wine\Fonts\Replacements]
"Segoe UI"="Selawik"
"Segoe UI Semibold"="Selawik Semibold"
"Segoe UI Light"="Selawik Light"
"Segoe UI Semilight"="Selawik Semilight"
"Segoe UI Variable"="Selawik"
"Tahoma"="Selawik"
"MS Shell Dlg"="Selawik"
"MS Shell Dlg 2"="Selawik"
"Microsoft Sans Serif"="Selawik"
"Arial"="Liberation Sans"
"Times New Roman"="Liberation Serif"
"Courier New"="Liberation Mono"
"Calibri"="Carlito"
"Cambria"="Caladea"
"Consolas"="Cascadia Mono"

[HKEY_CURRENT_USER\Control Panel\Desktop]
"FontSmoothing"="2"
"FontSmoothingType"=dword:00000002
"FontSmoothingGamma"=dword:00000578
"FontSmoothingOrientation"=dword:00000001

[HKEY_CURRENT_USER\Control Panel\Colors]
"ActiveTitle"="0 103 192"
"Hilight"="0 103 192"
"HotTrackingColor"="0 103 192"
"Window"="255 255 255"
"ButtonFace"="243 243 243"
"Menu"="249 249 249"
"MenuBar"="243 243 243"
"""


def prefix_ready():
    return os.path.isfile(os.path.join(PREFIX, "system.reg")) and \
        os.path.isdir(os.path.join(PREFIX, "drive_c", "windows"))


def prepare():
    """Creates and configures the Wine prefix. Returns True when it is ready."""
    if prefix_ready() and os.path.exists(os.path.join(PREFIX, ".glasspanes")):
        return True
    subprocess.run(["wineboot", "--init"], env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["wineserver", "--wait"], env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with tempfile.NamedTemporaryFile("w", suffix=".reg", delete=False) as f:
        f.write(REG)
        reg = f.name
    subprocess.run(["wine", "regedit", "/S", reg], env=ENV, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    subprocess.run(["wineserver", "--wait"], env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.unlink(reg)
    if prefix_ready():
        with open(os.path.join(PREFIX, ".glasspanes"), "w") as f:
            f.write("configured\n")
        return True
    return False


def prepare_with_window():
    """prepare(), showing a small 'Getting Windows app support ready' window meanwhile."""
    if prefix_ready() and os.path.exists(os.path.join(PREFIX, ".glasspanes")):
        return True
    import threading
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget
    from . import style
    app = QApplication.instance() or QApplication(sys.argv)
    app.setDesktopFileName("glass-wine")
    t = style.apply_app_style(app)
    w = QWidget()
    w.setObjectName("Window")
    w.setWindowTitle("Windows app support")
    w.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    w.setFixedSize(440, 150)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(24, 20, 24, 20)
    title = QLabel("Getting Windows app support ready")
    title.setProperty("role", "subtitle")
    lay.addWidget(title)
    msg = QLabel("This only happens once and takes about a minute.")
    msg.setProperty("role", "secondary")
    lay.addWidget(msg)
    lay.addStretch(1)
    bar = QProgressBar()
    bar.setRange(0, 0)
    lay.addWidget(bar)
    w.show()
    result = {}
    th = threading.Thread(target=lambda: result.setdefault("ok", prepare()), daemon=True)
    th.start()
    timer = QTimer()
    timer.timeout.connect(lambda: (not th.is_alive()) and app.quit())
    timer.start(300)
    app.exec()
    w.close()
    return result.get("ok", False)


def fix_shortcuts(since):
    """Installers put Windows shortcuts on the desktop; make new ones launchable from Plasma."""
    from .firstlogin import desktop_dir
    for d in (desktop_dir(), os.path.expanduser("~/.local/share/applications/wine")):
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                if fn.endswith(".desktop") and os.path.getmtime(p) >= since - 2:
                    try:
                        os.chmod(p, 0o755)
                    except OSError:
                        pass
    subprocess.run(["kbuildsycoca6"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def command_for(path, args):
    low = path.lower()
    if low.endswith(".msi"):
        return ["wine", "msiexec", "/i", path] + args
    if low.endswith((".bat", ".cmd")):
        return ["wine", "cmd", "/c", path] + args
    if low.endswith(".lnk"):
        return ["wine", "start", "/unix", path] + args
    return ["wine", path] + args


def open_file(path, args):
    if not prepare_with_window():
        _error("Windows app support couldn't be set up.",
               "Try again, or open Settings > Apps > Windows apps to repair it.")
        return 1
    started = time.time()
    workdir = os.path.dirname(os.path.abspath(path)) or None
    try:
        proc = subprocess.Popen(command_for(os.path.abspath(path), args), env=ENV, cwd=workdir)
    except OSError as e:
        _error("This app can't run on your PC", str(e))
        return 1
    proc.wait()
    subprocess.run(["wineserver", "--wait"], env=ENV)
    fix_shortcuts(started)
    return 0


def _error(title, text):
    try:
        subprocess.run(["kdialog", "--title", "Windows app support", "--error", f"{title}\n\n{text}"])
    except OSError:
        print(f"{title}: {text}", file=sys.stderr)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: glass-wine FILE [ARGS...] | --prepare [--quiet] | --config | --drive", file=sys.stderr)
        return 2
    if argv[0] == "--prepare":
        ok = prepare() if "--quiet" in argv else prepare_with_window()
        return 0 if ok else 1
    if argv[0] == "--config":
        prepare_with_window()
        return subprocess.call(["winecfg"], env=ENV)
    if argv[0] == "--drive":
        prepare_with_window()
        return subprocess.call(["xdg-open", os.path.join(PREFIX, "drive_c")])
    if argv[0] == "--uninstaller":
        prepare_with_window()
        return subprocess.call(["wine", "uninstaller"], env=ENV)
    path = argv[0]
    if path.startswith("file://"):
        from urllib.parse import unquote
        path = unquote(path[7:])
    if not os.path.exists(path):
        _error("Windows can't find this file", path)
        return 1
    return open_file(path, argv[1:])


if __name__ == "__main__":
    sys.exit(main())
