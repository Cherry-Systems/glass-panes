"""Applies the user's look (light/dark, accent colour, background, taskbar alignment) to the whole
desktop at once: Plasma colours and panel theme, window borders, icons, Qt app style, lock screen,
and Glass Panes' own apps."""
import glob
import json
import os
import shutil
import subprocess
import time

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


# The taskbar is [spacer, task manager, spacer, tray, clock]. Left alignment shrinks the first spacer
# to nothing instead of removing it: Plasma's scripting can add widgets only at the end and can't
# reorder them while the shell runs, so removed spacers can't be put back in place.
SPACER = "org.kde.plasma.panelspacer"
TASK_MANAGERS = ("org.kde.plasma.icontasks", "org.kde.plasma.taskmanager")

TASKBAR_READ = """
for (const p of panels()) {
  if (p.location !== 'bottom') continue;
  p.currentConfigGroup = ['General'];
  const order = String(p.readConfig('AppletOrder', '')).split(';').map(Number).filter(n => n > 0);
  const ids = order.filter(id => p.widgetIds.indexOf(id) >= 0)
                   .concat(p.widgetIds.filter(id => order.indexOf(id) < 0));
  print(JSON.stringify({panel: p.id, widgets: ids.map(id => [id, p.widgetById(id).type])}));
  break;
}
"""

TASKBAR_EDIT = """
for (const p of panels()) {
  if (p.id !== %(panel)d) continue;
  for (let i = 0; i < %(add)d; i++) p.addWidget('org.kde.plasma.panelspacer');
  for (const id of %(remove)s) p.widgetById(id).remove();
  for (const [id, expanding] of %(spacers)s) {
    const s = p.widgetById(id);
    s.currentConfigGroup = ['General'];
    s.writeConfig('expanding', expanding);
    s.writeConfig('length', 0);
    s.reloadConfig();
  }
  if (%(order)s.length) {
    p.currentConfigGroup = ['General'];
    p.writeConfig('AppletOrder', %(order)s.join(';'));
  }
}
"""


def _shell_script(js):
    for tool in ("qdbus6", "qdbus"):
        if shutil.which(tool):
            try:
                out = subprocess.run([tool, "org.kde.plasmashell", "/PlasmaShell",
                                      "org.kde.PlasmaShell.evaluateScript", js],
                                     capture_output=True, text=True, timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                return None
            return out.stdout if out.returncode == 0 else None
    return None


def _taskbar_layout():
    out = _shell_script(TASKBAR_READ) or ""
    for line in reversed(out.splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def _taskbar_edit(panel, add=0, remove=(), spacers=(), order=()):
    _shell_script(TASKBAR_EDIT % dict(panel=panel, add=add, remove=json.dumps(list(remove)),
                                      spacers=json.dumps([list(s) for s in spacers]),
                                      order=json.dumps(list(order))))


def taskbar_plan(widgets):
    """`widgets` is [[id, plugin], ...] in on-screen order. Returns the spacer in front of the task
    manager if the layout is intact (a spacer on each side of it), otherwise None."""
    ids = [w[0] for w in widgets]
    kinds = dict((w[0], w[1]) for w in widgets)
    tasks = next((i for i in ids if kinds[i] in TASK_MANAGERS), None)
    if tasks is None:
        return None
    t = ids.index(tasks)
    if t > 0 and kinds[ids[t - 1]] == SPACER and any(kinds[i] == SPACER for i in ids[t + 1:]):
        return ids[t - 1]
    return None


def taskbar_repair_order(widgets):
    """Order for a damaged taskbar: first spacer, task manager, second spacer, then everything else
    as it was. Returns (order, extra spacers to remove), or None if there's no task manager or
    fewer than two spacers."""
    ids = [w[0] for w in widgets]
    kinds = dict((w[0], w[1]) for w in widgets)
    tasks = next((i for i in ids if kinds[i] in TASK_MANAGERS), None)
    spacers = [i for i in ids if kinds[i] == SPACER]
    if tasks is None or len(spacers) < 2:
        return None
    rest = [i for i in ids if i != tasks and kinds[i] != SPACER]
    return [spacers[0], tasks, spacers[1]] + rest, spacers[2:]


def apply_taskbar(align):
    center = align != "left"
    layout = _taskbar_layout()
    if not layout:
        return
    left = taskbar_plan(layout["widgets"])
    if left is not None:
        _taskbar_edit(layout["panel"], spacers=[(left, center)])
        return
    # Damaged layout (e.g. by an older Glass Panes): put the spacers back, then restart the shell,
    # which is the only time Plasma reads the widget order.
    spacers = sum(1 for w in layout["widgets"] if w[1] == SPACER)
    if spacers < 2:
        _taskbar_edit(layout["panel"], add=2 - spacers)
        time.sleep(2)
        layout = _taskbar_layout()
    plan = taskbar_repair_order(layout["widgets"]) if layout else None
    if not plan:
        return
    order, extra = plan
    if extra:
        _taskbar_edit(layout["panel"], remove=extra)
        time.sleep(2)
    _taskbar_edit(layout["panel"], spacers=[(order[0], center), (order[2], True)], order=order)
    time.sleep(2)
    if not _run("systemctl", "--user", "restart", "plasma-plasmashell.service"):
        subprocess.Popen(["plasmashell", "--replace"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
