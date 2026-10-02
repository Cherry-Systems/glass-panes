"""Account and session actions: user name and picture, lock, sign out, sleep, restart, shut down."""
import os
import pwd
import subprocess

from . import paths


def user_name():
    try:
        pw = pwd.getpwuid(os.getuid())
        full = pw.pw_gecos.split(",")[0].strip()
        return full or pw.pw_name
    except KeyError:
        return os.environ.get("USER", "User")


def login_name():
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return os.environ.get("USER", "user")


def user_picture():
    candidates = [os.path.expanduser("~/.face.icon"), os.path.expanduser("~/.face"),
                  f"/var/lib/AccountsService/icons/{login_name()}", paths.artwork("user.png")]
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 0:
            return c
    return ""


def _qdbus(*args):
    for tool in ("qdbus6", "qdbus"):
        try:
            r = subprocess.run([tool, *args], capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def _detach(argv):
    try:
        subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def lock():
    return _detach(["loginctl", "lock-session"])


def sign_out():
    if not _qdbus("org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logout"):
        _detach(["loginctl", "terminate-session", os.environ.get("XDG_SESSION_ID", "")])


def restart():
    if not _qdbus("org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logoutAndReboot"):
        _detach(["systemctl", "reboot"])


def shut_down():
    if not _qdbus("org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logoutAndShutdown"):
        _detach(["systemctl", "poweroff"])


def sleep():
    lock()
    _detach(["systemctl", "suspend"])


def switch_user():
    _qdbus("org.kde.ksmserver", "/KSMServer", "org.kde.KSMServerInterface.openSwitchUserDialog")
