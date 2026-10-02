"""Where Glass Panes keeps its data. GLASSPANES_DATA points at the source tree when trying the apps
on a development PC (see the Makefile's try-* targets)."""
import os

DATA = os.environ.get("GLASSPANES_DATA", "/usr/share/glasspanes")
ICONS = os.path.join(DATA, "icons", "fluent")
_REPO_ART = os.path.join(os.path.dirname(DATA.rstrip("/")), "build", "art")
ARTWORK = os.path.join(DATA, "artwork") if os.path.isdir(os.path.join(DATA, "artwork")) else _REPO_ART
WALLPAPERS = "/usr/share/backgrounds/glasspanes"
if not os.path.isdir(WALLPAPERS) and os.path.isdir(os.path.join(_REPO_ART, "wallpapers")):
    WALLPAPERS = os.path.join(_REPO_ART, "wallpapers")

HOME = os.path.expanduser("~")
CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "glasspanes")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.join(HOME, ".local", "state")), "glasspanes")


def artwork(name):
    return os.path.join(ARTWORK, name)


def os_release():
    info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key:
                    info[key] = value.strip('"')
    except OSError:
        pass
    return info


def is_live_session():
    return os.path.exists("/run/live/medium") or "boot=live" in _cmdline()


def _cmdline():
    try:
        with open("/proc/cmdline") as f:
            return f.read()
    except OSError:
        return ""
