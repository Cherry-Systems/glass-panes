"""Applies the user's look (light/dark, accent colour, background, taskbar alignment) to the whole
desktop at once: Plasma colours and panel theme, window borders, icons, Qt app style, lock screen,
and Glass Panes' own apps."""
import glob
import os
import shutil
import subprocess

from . import prefs

THEMES = {
    "light": dict(colors="Win11OSLight", plasma="Win11OS-light", aurorae="__aurorae__svg__Win11OS-light",
                  icons="Win11", kvantum="Win11OS-light", gtk="Breeze"),
    "dark": dict(colors="Win11OSDark", plasma="Win11OS-dark", aurorae="__aurorae__svg__Win11OS-dark",
                 icons="Win11-dark", kvantum="Win11OS-dark", gtk="Breeze-Dark"),
}


def _run(*argv, timeout=20):
    if not shutil.which(argv[0]) and not os.path.isabs(argv[0]):
        return False
    try:
        return subprocess.run(list(argv), capture_output=True, timeout=timeout).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def kwrite(file, groups, key, value):
    args = ["kwriteconfig6", "--file", file]
    for g in groups:
        args += ["--group", g]
    args += ["--key", key, str(value)]
    return _run(*args)


def kread(file, groups, key, default=""):
    args = ["kreadconfig6", "--file", file]
    for g in groups:
        args += ["--group", g]
    args += ["--key", key, "--default", default]
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return default


def qdbus(*args):
    for tool in ("qdbus6", "qdbus"):
        if shutil.which(tool):
            return _run(tool, *args)
    return False


def libexec(name):
    for pattern in (f"/usr/lib/*/libexec/{name}", f"/usr/libexec/{name}", f"/usr/lib/libexec/{name}"):
        hits = glob.glob(pattern)
        if hits:
            return hits[0]
    return None


def hex_to_rgb(color):
    c = color.lstrip("#")
    return ",".join(str(int(c[i:i + 2], 16)) for i in (0, 2, 4))


def apply_mode(mode, accent):
    th = THEMES[mode]
    _run("plasma-apply-colorscheme", th["colors"])
    _run("plasma-apply-colorscheme", "--accent-color", accent)
    kwrite("kdeglobals", ["General"], "AccentColor", hex_to_rgb(accent))
    _run("plasma-apply-desktoptheme", th["plasma"])
    kwrite("kwinrc", ["org.kde.kdecoration2"], "library", "org.kde.kwin.aurorae")
    kwrite("kwinrc", ["org.kde.kdecoration2"], "theme", th["aurorae"])
    changeicons = libexec("plasma-changeicons")
    if changeicons:
        _run(changeicons, th["icons"])
    else:
        kwrite("kdeglobals", ["Icons"], "Theme", th["icons"])
    kv = os.path.expanduser("~/.config/Kvantum")
    os.makedirs(kv, exist_ok=True)
    with open(os.path.join(kv, "kvantum.kvconfig"), "w") as f:
        f.write(f"[General]\ntheme={th['kvantum']}\n")
    kwrite("kdeglobals", ["KDE"], "widgetStyle", "kvantum")
    gtk = os.path.expanduser("~/.config/gtk-3.0")
    os.makedirs(gtk, exist_ok=True)
    kwrite(os.path.join(gtk, "settings.ini"), ["Settings"], "gtk-application-prefer-dark-theme",
           "true" if mode == "dark" else "false")
    qdbus("org.kde.KWin", "/KWin", "reconfigure")


def apply_wallpaper(path):
    if not path or not os.path.exists(path):
        return
    _run("plasma-apply-wallpaperimage", path)
    kwrite("kscreenlockerrc", ["Greeter", "Wallpaper", "org.kde.image", "General"], "Image", "file://" + path)
    kwrite("kscreenlockerrc", ["Greeter", "Wallpaper", "org.kde.image", "General"], "PreviewImage",
           "file://" + path)


TASKBAR_SCRIPT = """
for (const p of panels()) {
  if (p.location !== 'bottom') continue;
  const ids = p.widgetIds;
  const spacers = p.widgets('org.kde.plasma.panelspacer');
  const left = '%s' === 'left';
  if (left) {
    if (spacers.length > 1) {
      const first = spacers.reduce((a, b) => ids.indexOf(a.id) < ids.indexOf(b.id) ? a : b);
      first.remove();
    }
  } else if (spacers.length < 2) {
    const s = p.addWidget('org.kde.plasma.panelspacer');
    const order = p.widgetIds.filter(x => x !== s.id);
    order.unshift(s.id);
    p.widgetIds = order;
  }
}
"""


def apply_taskbar(align):
    qdbus("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript",
          TASKBAR_SCRIPT % ("left" if align == "left" else "center"))


def notify_apps():
    _run("glass-shell", "reload")


def apply(changes=None, data=None):
    """Saves `changes` (if any) and applies everything affected by them."""
    data = prefs.update(**changes) if changes else (data or prefs.load())
    keys = set(changes or data)
    if keys & {"mode", "accent"}:
        apply_mode(data["mode"], data["accent"])
    if keys & {"mode", "wallpaper"}:
        apply_wallpaper(prefs.wallpaper(data))
    if "taskbar_align" in keys:
        apply_taskbar(data["taskbar_align"])
    notify_apps()
    return data
