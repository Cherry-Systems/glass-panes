"""Runs at every login (autostart). The first time for each user it applies the Glass Panes look,
puts the Recycle Bin on the desktop and prepares Windows app support; later it only fills in what
is missing, so the user's own changes are never undone."""
import os
import subprocess
import time

from . import appearance, paths, prefs

RECYCLE_BIN = """[Desktop Entry]
Type=Link
Name=Recycle Bin
Icon=user-trash-full
EmptyIcon=user-trash
URL=trash:/
"""

THIS_PC = """[Desktop Entry]
Type=Link
Name=This PC
Icon=computer
URL=remote:/
"""


def desktop_dir():
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5)
        d = out.stdout.strip()
        if d:
            return d
    except (OSError, subprocess.TimeoutExpired):
        pass
    return os.path.expanduser("~/Desktop")


def put_desktop_icons():
    d = desktop_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "Recycle Bin.desktop")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(RECYCLE_BIN)
        os.chmod(path, 0o755)


def install_shortcut():
    """Live session: an 'Install Glass Panes' icon on the desktop."""
    if not paths.is_live_session():
        return
    src = "/usr/share/applications/calamares-install-debian.desktop"
    if not os.path.exists(src):
        return
    dst = os.path.join(desktop_dir(), "Install Glass Panes.desktop")
    if not os.path.exists(dst):
        with open(src) as f:
            text = f.read()
        with open(dst, "w") as f:
            f.write(text)
        os.chmod(dst, 0o755)


def live_no_lock():
    """Live session: never lock the screen (nobody knows the live password)."""
    if not paths.is_live_session():
        return
    for key in ("Autolock", "LockOnResume"):
        subprocess.run(["kwriteconfig6", "--file", "kscreenlockerrc", "--group", "Daemon",
                        "--key", key, "false"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["qdbus6", "org.kde.screensaver", "/ScreenSaver", "org.kde.screensaver.configure"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    live_no_lock()
    data = prefs.load()
    if not data.get("applied"):
        # Give Plasma a moment to finish starting so the plasma-apply-* tools reach it.
        time.sleep(3)
        appearance.apply(data=dict(data, taskbar_align=data["taskbar_align"]))
        put_desktop_icons()
        prefs.update(applied=True)
    install_shortcut()
    if not paths.is_live_session() and not os.path.isdir(os.path.expanduser("~/.wine/drive_c")):
        subprocess.Popen(["nice", "-n", "15", "glass-wine", "--prepare", "--quiet"],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
