"""Installed applications, read from XDG .desktop files (including the ones Wine writes when a
Windows program is installed), and launching them."""
import configparser
import os
import re
import shlex
import subprocess

DESKTOP_ENVS = {"KDE", "X-GLASSPANES"}


def data_dirs():
    home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    dirs = [home] + os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    seen, out = set(), []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _unescape(value):
    out, i = [], 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value):
            n = value[i + 1]
            out.append({"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}.get(n, "\\" + n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


class App:
    __slots__ = ("id", "path", "name", "generic", "comment", "icon", "exec", "keywords",
                 "categories", "terminal", "is_wine", "workdir", "no_display")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def matches(self, query):
        q = query.lower()
        hay = [self.name, self.generic or "", self.comment or "", " ".join(self.keywords or []),
               os.path.splitext(self.id)[0]]
        return any(q in h.lower() for h in hay)

    def score(self, query):
        q = query.lower()
        n = self.name.lower()
        if n == q:
            return 100
        if n.startswith(q):
            return 80
        if any(w.startswith(q) for w in n.split()):
            return 60
        if q in n:
            return 40
        return 10

    def command(self, files=()):
        return exec_to_argv(self.exec, files, self.name, self.icon, self.path)

    def launch(self, files=()):
        argv = self.command(files)
        if not argv:
            return False
        if self.terminal:
            argv = ["konsole", "-e"] + argv
        try:
            subprocess.Popen(argv, cwd=self.workdir or os.path.expanduser("~"),
                             start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            return False


def exec_to_argv(exec_line, files=(), name="", icon="", path=""):
    if not exec_line:
        return []
    try:
        parts = shlex.split(_unescape(exec_line))
    except ValueError:
        parts = exec_line.split()
    argv = []
    for part in parts:
        if part in ("%f", "%u"):
            argv.extend(list(files)[:1])
        elif part in ("%F", "%U"):
            argv.extend(files)
        elif part == "%i":
            if icon:
                argv.extend(["--icon", icon])
        elif part == "%c":
            argv.append(name)
        elif part == "%k":
            argv.append(path or "")
        elif re.fullmatch(r"%[dDnNvm]", part):
            continue
        else:
            argv.append(part.replace("%%", "%"))
    return argv


def parse(path, desktop_id=None):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            cp.read_file(f)
    except (OSError, configparser.Error, UnicodeDecodeError):
        return None
    if not cp.has_section("Desktop Entry"):
        return None
    e = cp["Desktop Entry"]
    if e.get("Type", "Application") != "Application":
        return None
    lang = (os.environ.get("LANG") or "en_US").split(".")[0]

    def loc(key):
        for k in (f"{key}[{lang}]", f"{key}[{lang.split('_')[0]}]", key):
            if k in e:
                return e[k]
        return ""

    only = [s for s in e.get("OnlyShowIn", "").split(";") if s]
    notin = [s for s in e.get("NotShowIn", "").split(";") if s]
    hidden = e.get("Hidden", "false").lower() == "true"
    no_display = e.get("NoDisplay", "false").lower() == "true"
    if only and not (set(only) & DESKTOP_ENVS):
        no_display = True
    if set(notin) & DESKTOP_ENVS:
        no_display = True
    try_exec = e.get("TryExec", "")
    if try_exec and not _which(try_exec):
        hidden = True
    if hidden:
        return None
    did = desktop_id or os.path.basename(path)
    return App(
        id=did, path=path, name=loc("Name") or did, generic=loc("GenericName"),
        comment=loc("Comment"), icon=e.get("Icon", ""), exec=e.get("Exec", ""),
        keywords=[k for k in loc("Keywords").split(";") if k],
        categories=[c for c in e.get("Categories", "").split(";") if c],
        terminal=e.get("Terminal", "false").lower() == "true",
        is_wine="wine" in path.lower() or "wine " in e.get("Exec", "").lower(),
        workdir=e.get("Path", ""), no_display=no_display)


def _which(cmd):
    if os.path.isabs(cmd):
        return os.access(cmd, os.X_OK)
    return any(os.access(os.path.join(d, cmd), os.X_OK) for d in os.environ.get("PATH", "").split(":"))


def all_apps(include_hidden=False):
    """Every application, keyed by desktop-file ID (the first data dir that has an ID wins)."""
    found = {}
    for d in data_dirs():
        root = os.path.join(d, "applications")
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root, followlinks=True):
            for fn in files:
                if not fn.endswith(".desktop"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root)
                did = rel.replace(os.sep, "-")
                if did in found:
                    continue
                found[did] = parse(os.path.join(dirpath, fn), did)
    apps = {k: v for k, v in found.items() if v is not None}
    if not include_hidden:
        apps = {k: v for k, v in apps.items() if not v.no_display}
    return apps


def find(desktop_id):
    for d in data_dirs():
        root = os.path.join(d, "applications")
        candidates = [os.path.join(root, desktop_id)]
        if "-" in desktop_id:
            candidates.append(os.path.join(root, *desktop_id.split("-", 1)))
        for c in candidates:
            if os.path.exists(c):
                return parse(c, desktop_id)
    return None


def sorted_apps(apps):
    return sorted(apps.values(), key=lambda a: a.name.lower())


def wine_uninstall_entries():
    """Programs installed under Wine, from its uninstaller: list of (guid, name)."""
    try:
        out = subprocess.run(["wine", "uninstaller", "--list"], capture_output=True, text=True,
                             timeout=60, env=dict(os.environ, WINEDEBUG="-all")).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    entries = []
    for line in out.splitlines():
        if "|||" in line:
            guid, name = line.split("|||", 1)
            entries.append((guid.strip(), name.strip()))
    return entries


def owning_package(app):
    """Debian package that installed this .desktop file, or None."""
    if not app.path or app.path.startswith(os.path.expanduser("~")):
        return None
    path = os.path.realpath(app.path)
    for candidate in (path, app.path, path.replace("/usr/local/share/", "/usr/share/")):
        try:
            out = subprocess.run(["dpkg-query", "-S", candidate], capture_output=True, text=True,
                                 timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if out.returncode == 0 and ":" in out.stdout:
            return out.stdout.split(":", 1)[0].split(",")[0].strip()
    return None


def flatpak_id(app):
    if "flatpak" in (app.path or ""):
        return os.path.splitext(app.id)[0]
    return None


def pin_to_taskbar(desktop_id):
    """Adds a launcher to the taskbar's icon list through Plasma's scripting interface."""
    script = (
        "for (const p of panels()) { for (const w of p.widgets('org.kde.plasma.icontasks')) {"
        " w.currentConfigGroup = ['General'];"
        " let l = String(w.readConfig('launchers', '')).split(',').filter(x => x);"
        f" const id = 'applications:{desktop_id}';"
        " if (!l.includes(id)) { l.push(id); w.writeConfig('launchers', l.join(',')); w.reloadConfig(); }"
        " } }")
    return _plasma_script(script)


def _plasma_script(script):
    for tool in ("qdbus6", "qdbus"):
        try:
            subprocess.run([tool, "org.kde.plasmashell", "/PlasmaShell",
                            "org.kde.PlasmaShell.evaluateScript", script],
                           capture_output=True, timeout=10)
            return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False
