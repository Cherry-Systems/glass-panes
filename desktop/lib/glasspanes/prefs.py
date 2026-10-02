"""The user's Glass Panes preferences, in ~/.config/glasspanes/settings.json.

Every Glass Panes app reads these; Settings writes them and then applies them to the whole desktop
(see appearance.py), so one change updates everything at once."""
import json
import os

from . import paths

# Real desktop-file IDs (renamed to their Windows names by hooks/20-apps.sh), so a pinned app and its
# running window are the same entry on the taskbar.
DEFAULT_PINNED = [
    "firefox-esr.desktop",
    "org.kde.dolphin.desktop",
    "glass-settings.desktop",
    "org.kde.discover.desktop",
    "org.kde.kwrite.desktop",
    "org.kde.gwenview.desktop",
    "org.kde.kcalc.desktop",
    "org.kde.kolourpaint.desktop",
    "org.kde.spectacle.desktop",
    "org.kde.haruna.desktop",
    "org.kde.konsole.desktop",
    "glass-taskmgr.desktop",
    "systemsettings.desktop",
    "org.kde.okular.desktop",
    "glass-run.desktop",
    "glass-windows-apps.desktop",
    "org.kde.kcharselect.desktop",
    "org.kde.partitionmanager.desktop",
]

ACCENTS = [
    "#0067c0", "#0078d4", "#0063b1", "#2d7d9a", "#038387", "#00b294", "#018574", "#107c10",
    "#498205", "#ca5010", "#da3b01", "#e74856", "#c30052", "#e3008c", "#881798", "#744da9",
    "#8764b8", "#5d5a58", "#68768a", "#486860",
]

DEFAULTS = {
    "mode": "light",            # light | dark
    "accent": "#0067c0",
    "wallpaper": "",            # empty = the default for the current mode
    "taskbar_align": "center",  # center | left
    "pinned": DEFAULT_PINNED,
    "search_engine": "bing",
    "show_recommended": True,
    "transparency": True,
    "applied": False,           # set once the defaults have been applied for this user
}

FILE = os.path.join(paths.CONFIG, "settings.json")


def load():
    data = dict(DEFAULTS)
    try:
        with open(FILE) as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    if data["mode"] not in ("light", "dark"):
        data["mode"] = "light"
    if not isinstance(data["pinned"], list):
        data["pinned"] = list(DEFAULT_PINNED)
    return data


def save(data):
    os.makedirs(paths.CONFIG, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FILE)


def update(**changes):
    data = load()
    data.update(changes)
    save(data)
    return data


def default_wallpaper(mode):
    return os.path.join(paths.WALLPAPERS, f"glass-bloom-{mode}.png")


def wallpaper(data=None):
    data = data or load()
    wp = data.get("wallpaper") or ""
    if wp and os.path.exists(wp):
        return wp
    return default_wallpaper(data["mode"])
