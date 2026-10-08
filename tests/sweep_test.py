#!/usr/bin/env python3
"""Feature sweep: tries everything a user can reach on an installed Glass Panes, once, and keeps a
screenshot of each so a person can check what actually appeared (a window opening isn't proof the
feature works: the Store once opened fine with no apps in it).

  build/venv/bin/python tests/sweep_test.py [--vm-dir build/vm-sweep]

Covers every app in Start, every Settings page, opening each common file type, Windows programs
(.exe and .msi), every Windows keyboard shortcut, the taskbar, tray and desktop menus, the Store,
the web, sound, printing, the Recycle Bin, zip files, screenshots and sleep. Needs a disk installed
by tests/install_test.py and `python3 scripts/vm-shell.py serve`. Results: build/sweep/report.md,
screenshots in build/sweep/shots/ and contact sheets of them in build/sweep/sheets/.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VM_REL = sys.argv[sys.argv.index("--vm-dir") + 1] if "--vm-dir" in sys.argv else "build/vm-sweep"
os.environ["SOAK_VM_DIR"] = VM_REL
os.environ["SOAK_OUT"] = "build/sweep"
sys.path.insert(0, os.path.dirname(__file__))
import soak_test as st  # noqa: E402
from PIL import Image, ImageChops, ImageDraw, ImageStat  # noqa: E402

st.render = lambda: None
OUT = st.OUT
SHOTS = st.SHOTS
DOCS = "~/Documents/sweep"
LIB = "cd /usr/lib/glasspanes && python3"
results = []   # dicts: area, name, status (ok/fail/look), detail, shot
shot_no = [0]


def shot(name):
    shot_no[0] += 1
    path = os.path.join(SHOTS, f"{shot_no[0]:03d}-{name}.jpg"[:90])
    st.grab().resize((1024, 576)).save(path, quality=80)
    return path


def record(area, name, status, detail="", path=None):
    results.append(dict(area=area, name=name, status=status, detail=detail, shot=path))
    st.note(f"[{area}] {name}: {status.upper()} {detail}")
    write_report()


def run(cmd, timeout=60):
    return st.run(cmd, timeout)


def guest(args, timeout=60):
    return st.guest(args, timeout)


def win_ids(all_types=True):
    return {w["id"]: w for w in guest("windows all" if all_types else "windows")}


def desktop_ids():
    """Windows that belong to the desktop itself (taskbar, wallpaper), so they're never closed."""
    return {i for i, w in win_ids().items() if w["class"] in ("plasmashell",)}


BASE = set()


CORE = r"plasmashell|kwin_x11|glasspanes\.shell|ksmserver|kded6|kglobalacceld|Xorg|sddm"


def close_new(before, grace=4):
    """Close every window that wasn't there before, then kill whatever is left of their programs.
    Windows of the desktop itself (Start, menus of the Glass shell, the taskbar) only get Esc."""
    new = {i: w for i, w in win_ids().items() if i not in before and i not in BASE}
    if not new:
        return
    pids = " ".join(str(w["pid"]) for w in new.values() if w.get("pid"))
    core = set(run(f"for p in {pids}; do ps -o args= -p $p | grep -qE '{CORE}' && echo $p; done; true")
               .split()) if pids else set()
    new = {i: w for i, w in new.items() if str(w.get("pid")) not in core}
    if core:
        keys("esc")
    if not new:
        return
    guest("closeid " + " ".join(map(str, new)))
    time.sleep(grace)
    still = {i: w for i, w in win_ids().items() if i in new}
    pids = {w["pid"] for w in list(still.values()) + list(new.values()) if w.get("pid")}
    if still:
        keys("esc")
        time.sleep(1)
    for pid in pids:
        run(f"kill -9 {pid} 2>/dev/null; true")
    time.sleep(1)


def keys(*k):
    st.keys(*k)


def tidy():
    keys("esc", "esc")
    time.sleep(1)
    try:
        if guest("stats")["locked"] == "yes":
            st.click(800, 450)
            time.sleep(2)
            st.type_text(st.PASSWORD + "\n")
            time.sleep(4)
        close_new(set())
        run(st.KILL_APPS)
    except Exception:
        pass


def wait_new(before, secs=25, pattern=None):
    end = time.time() + secs
    while time.time() < end:
        now = win_ids()
        new = [w for i, w in now.items() if i not in before and i not in BASE]
        if pattern:
            import re
            new = [w for w in new if re.search(pattern, w["title"] + " " + w["class"], re.I)]
        if new:
            return new
        time.sleep(0.5)
    return []


def diff(a, b):
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def attempt(area, name, fn):
    before = set(win_ids())
    try:
        out = fn()
        out = out if isinstance(out, tuple) else ("ok", out or "")
        status, detail, path = (tuple(out) + (None,))[:3]
        record(area, name, status, detail, path)
    except Exception as e:
        path = shot(f"fail-{name}".replace(" ", "-").replace("/", "-"))
        record(area, name, "fail", f"{type(e).__name__}: {e}"[:300], path)
        tidy()
    try:
        close_new(before)
    except Exception:
        pass


# ---- apps -----------------------------------------------------------------------------------------
SKIP_APPS = r"log ?out|sign out|shut ?down|restart|sleep|lock|switch user"


def orca_on():
    """Narrator's screen reader is running (a zombie left by an old Orca doesn't count)."""
    return run("ps -C orca -o stat= | grep -qv Z && echo on || echo off").strip().endswith("on")


def sweep_apps():
    data = json.loads(run(f"{LIB} -c \"import json; from glasspanes import apps; "
                          "print(json.dumps([[a.id, a.name] for a in apps.sorted_apps(apps.all_apps())]))\"")
                      .strip().splitlines()[-1])
    import re
    st.note(f"{len(data)} apps in Start")
    for app_id, name in data:
        if re.search(SKIP_APPS, name, re.I):
            record("Apps", name, "look", "skipped (power or session action; tested separately)")
            continue

        def launch(app_id=app_id, name=name):
            before = set(win_ids())
            run(f"{LIB} -c \"from glasspanes import apps; apps.find('{app_id}').launch()\" "
                f"> /tmp/launch.log 2>&1; sleep 0.5", 30)
            new = wait_new(before, 30)
            time.sleep(4)
            path = shot("app-" + re.sub(r"\W+", "-", name))
            if name == "Narrator":  # no window; it turns the screen reader on, so turn it off again
                on = orca_on()
                run("glass-shell narrator; sleep 2")
                return ("ok" if on and not orca_on() else "fail"), f"Orca on: {on}, off again: {not orca_on()}", path
            if not new:
                err = run("cat /tmp/launch.log").strip()[-200:]
                return "fail", f"no window within 30 s {err}", path
            titles = "; ".join(f"{w['title']} [{w['class']}]" for w in new)[:200]
            return "look", f"opened: {titles}", path
        attempt("Apps", name, launch)


# ---- Settings ---------------------------------------------------------------------------------------
def sweep_settings():
    mods = "system devices network personal apps_page accounts time_lang access privacy update"
    pages = json.loads(run(f"{LIB} -c \"import json, importlib; p=[]; "
                           f"[p.extend(importlib.import_module('glasspanes.settings.'+m).PAGES) for m in '{mods}'.split()]; "
                           "print(json.dumps(p))\"").strip().splitlines()[-1])
    st.note(f"{len(pages)} Settings pages")
    for p in pages:
        def page(p=p):
            before = set(win_ids())
            run(f"setsid glass-settings --page {p} > /tmp/gs.log 2>&1 < /dev/null &")
            if not wait_new(before, 20, "^Settings"):
                raise RuntimeError("Settings didn't open")
            time.sleep(3.5)
            path = shot(f"settings-{p}")
            log = run("cat /tmp/gs.log")
            if "Traceback" in log:
                return "fail", "Python error: " + log.strip().splitlines()[-1][:200], path
            return "look", "", path
        attempt("Settings", p, page)
    for label, arg in (("Task Manager: Processes", ""), ("Task Manager: Performance", "--performance")):
        def tm(arg=arg, label=label):
            before = set(win_ids())
            run(f"setsid glass-taskmgr {arg} > /tmp/tm.log 2>&1 < /dev/null &")
            if not wait_new(before, 20):
                raise RuntimeError("Task Manager didn't open")
            time.sleep(5)
            return "look", "", shot(label.replace(" ", "").replace(":", "-"))
        attempt("Settings", label, tm)


# ---- file types ------------------------------------------------------------------------------------
MAKE_FILES = r"""
import os, wave, struct, math, zipfile
d = os.path.expanduser('~/Documents/sweep'); os.makedirs(d, exist_ok=True)
open(f'{d}/notes.txt', 'w').write('Hello from the Glass Panes sweep\n')
open(f'{d}/page.html', 'w').write('<html><body><h1>Local web page</h1></body></html>')
open(f'{d}/table.csv', 'w').write('name,amount\napples,3\npears,5\n')
open(f'{d}/drawing.svg', 'w').write('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><circle cx="100" cy="100" r="80" fill="#0067c0"/></svg>')
w = wave.open(f'{d}/tone.wav', 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
w.writeframes(b''.join(struct.pack('<h', int(8000*math.sin(2*math.pi*440*i/22050))) for i in range(22050*3))); w.close()
with zipfile.ZipFile(f'{d}/archive.zip', 'w') as z: z.writestr('inside.txt', 'zipped text')
pdf = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj 4 0 obj<</Length 44>>stream\nBT /F1 24 Tf 40 100 Td (Sweep PDF) Tj ET\nendstream endobj 5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n'
open(f'{d}/document.pdf', 'wb').write(pdf)
import zlib
def png(path, w, h):
    rows = b''.join(b'\0' + bytes(c for x in range(w) for c in (0, 103 + x * 150 // w, 192)) for y in range(h))
    chunk = lambda t, data: struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data))
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
png(f'{d}/photo.png', 320, 200)
print('made')
"""


def sweep_files():
    run(f"cat > /tmp/mk.py <<'EOF'\n{MAKE_FILES}\nEOF\npython3 /tmp/mk.py")
    run(f"cp \"$(ls /usr/share/backgrounds/glasspanes/*.png | head -1)\" {DOCS}/wallpaper.png; cd {DOCS} && "
        "f=$(ls /usr/share/wallpapers/*/contents/images/*.jpg 2>/dev/null | head -1); "
        "[ -n \"$f\" ] && cp \"$f\" photo.jpg; ls")
    files = [f for f in run(f"ls {DOCS}").split() if f not in ("unzipped",)][:14]
    for f in files:
        def open_file(f=f):
            before = set(win_ids())
            mime = run(f"xdg-mime query filetype {DOCS}/{f}; xdg-mime query default "
                       f"$(xdg-mime query filetype {DOCS}/{f})").split()
            run(f"(cd {DOCS} && setsid xdg-open {f}) >/dev/null 2>&1 < /dev/null &")
            new = wait_new(before, 30)
            time.sleep(4)
            path = shot("file-" + f.replace(".", "-"))
            if not new:
                return "fail", f"nothing opened ({' '.join(mime)})", path
            return "look", f"{' '.join(mime)} -> " + "; ".join(f"{w['title']} [{w['class']}]" for w in new)[:160], path
        attempt("Files", f, open_file)

    def explorer_view():
        before = set(win_ids())
        run(f"setsid dolphin {DOCS} >/dev/null 2>&1 < /dev/null &")
        wait_new(before, 20)
        time.sleep(5)
        return "look", "thumbnails and icons", shot("explorer-sweep-folder")
    attempt("Files", "File Explorer showing the files", explorer_view)

    def unzip():
        out = run(f"cd {DOCS} && rm -rf unzipped && mkdir unzipped && ark -b -o unzipped archive.zip; "
                  "cat unzipped/inside.txt unzipped/*/inside.txt 2>/dev/null", 60)
        return ("ok", "Compressed Folders extracted the zip") if "zipped text" in out else ("fail", out[-200:], None)
    attempt("Files", "extract a zip (Compressed Folders)", unzip)

    def recycle():
        out = run(f"cd {DOCS} && echo bin > binme.txt && kioclient move binme.txt trash:/ && sleep 1 && "
                  "kioclient ls trash:/ && test ! -e binme.txt && echo gone-from-folder")
        before = set(win_ids())
        run("setsid dolphin trash:/ >/dev/null 2>&1 < /dev/null &")
        wait_new(before, 20)
        time.sleep(4)
        path = shot("recycle-bin")
        close_new(before)
        emptied = run("ktrash6 --empty 2>&1; sleep 2; kioclient ls trash:/ | grep -c binme")
        ok = "binme.txt" in out and "gone-from-folder" in out and emptied.strip().endswith("0")
        return ("look" if ok else "fail"), (out.strip() + " / emptied: " + emptied.strip())[-200:], path
    attempt("Files", "Recycle Bin (delete, see it there, empty)", recycle)


# ---- Windows programs -------------------------------------------------------------------------------
def sweep_windows_apps():
    got = run("cd ~/Downloads && (test -f 7z2409-x64.exe || curl -sfLO https://www.7-zip.org/a/7z2409-x64.exe); "
              "(test -f 7z2409-x64.msi || curl -sfLO https://www.7-zip.org/a/7z2409-x64.msi); ls", 180)
    for f, label in (("7z2409-x64.exe", ".exe installer (double-click)"), ("7z2409-x64.msi", ".msi installer (double-click)")):
        def open_installer(f=f):
            if f not in got:
                raise RuntimeError(f"couldn't download {f}")
            before = set(win_ids())
            run(f"(cd ~/Downloads && setsid xdg-open {f}) >/dev/null 2>&1 < /dev/null &")
            new = wait_new(before, 90)
            time.sleep(6)
            path = shot("wine-" + f.replace(".", "-"))
            if not new:
                return "fail", "no installer window within 90 s", path
            return "look", "; ".join(f"{w['title']} [{w['class']}]" for w in new)[:160], path
        attempt("Windows apps", label, open_installer)
        run("wineserver -k 2>/dev/null; sleep 2; true", 30)

    def install_and_start():
        run("cd ~/Downloads && timeout 300 wine 7z2409-x64.exe /S; sleep 3", 330)
        if run(f"test -f {st.SEVENZIP} && echo yes").strip() != "yes":
            raise RuntimeError("silent install didn't install 7-Zip")
        keys("meta_l")
        time.sleep(1.5)
        st.type_text("7-Zip")
        time.sleep(2)
        p1 = shot("start-search-7zip")
        before = set(win_ids())
        keys("ret")
        new = wait_new(before, 45)
        time.sleep(3)
        p2 = shot("7zip-running")
        if not new:
            return "fail", "installed but didn't start from Start", p2
        return "look", f"installed; Start found it ({os.path.basename(p1)}); it opened", p2
    attempt("Windows apps", "install a Windows program, start it from Start", install_and_start)

    def listed_in_settings():
        before = set(win_ids())
        run("setsid glass-settings --page installedapps >/dev/null 2>&1 < /dev/null &")
        wait_new(before, 20)
        time.sleep(5)
        return "look", "7-Zip should be listed", shot("installed-apps-with-7zip")
    attempt("Windows apps", "Windows program listed in Installed apps", listed_in_settings)


# ---- keyboard shortcuts -----------------------------------------------------------------------------
SHORTCUTS = [
    ("Win (Start)", ["meta_l"]), ("Ctrl+Esc (Start)", ["ctrl-esc"]), ("Win+S (search)", ["meta_l-s"]),
    ("Win+E (File Explorer)", ["meta_l-e"]), ("Win+I (Settings)", ["meta_l-i"]), ("Win+R (Run)", ["meta_l-r"]),
    ("Win+X (quick link menu)", ["meta_l-x"]), ("Win+A (quick settings)", ["meta_l-a"]),
    ("Win+N (notifications)", ["meta_l-n"]), ("Win+V (clipboard history)", ["meta_l-v"]),
    ("Win+Tab (task view)", ["meta_l-tab"]), ("Win+. (emoji)", ["meta_l-dot"]),
    ("Win+Shift+S (Snipping Tool)", ["meta_l-shift-s"]), ("Print Screen", ["print"]),
    ("Win+Print Screen (save screenshot)", ["meta_l-print"]), ("Ctrl+Shift+Esc (Task Manager)", ["ctrl-shift-esc"]),
    ("Ctrl+Alt+Del", ["ctrl-alt-delete"]), ("Alt+F4 on the desktop (shut down box)", ["alt-f4"]),
    ("Win+P (project / displays)", ["meta_l-p"]),
    ("Win+U (accessibility settings)", ["meta_l-u"]), ("Win++ (magnifier)", ["meta_l-equal"]),
    ("Win+Ctrl+Enter (narrator)", ["meta_l-ctrl-ret"]), ("Win+Ctrl+D (new virtual desktop)", ["meta_l-ctrl-d"]),
    ("Win+H (voice typing)", ["meta_l-h"]), ("Win+G (game bar)", ["meta_l-g"]), ("Win+L (lock)", ["meta_l-l"]),
]
DESKTOP_COUNT = "qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.count"


def maximized(w):
    return w is not None and "MAXIMIZED_HORZ" in w["state"] and "MAXIMIZED_VERT" in w["state"]


def minimized(w):
    return w is not None and "HIDDEN" in w["state"]


# Pressed with Notepad open (and Calculator opened after it, in front, when the third item is True).
# The check looks at Notepad's window afterwards; without one, the screen has to change.
WINDOW_SHORTCUTS = [
    ("Win+Up (maximise)", ["meta_l-up"], False, maximized),
    ("Win+Up twice (stays maximised)", ["meta_l-up", "meta_l-up"], False, maximized),
    ("Win+Down (restore a maximised window)", ["meta_l-up", "meta_l-down"], False,
     lambda w: w is not None and not maximized(w) and not minimized(w)),
    ("Win+Down (minimise a restored window)", ["meta_l-down"], False, minimized),
    ("Win+Left (snap left)", ["meta_l-left"], False, None),
    ("Win+Right (snap right)", ["meta_l-right"], False, None),
    ("Win+D (show desktop)", ["meta_l-d"], False, None),
    ("Win+M (minimise all)", ["meta_l-m"], False, minimized),
    ("Win+Shift+M (restore after Win+M)", ["meta_l-m", "meta_l-shift-m"], False,
     lambda w: w is not None and not minimized(w) and w["active"]),
    ("Win+Home (minimise the other windows)", ["meta_l-home"], True, minimized),
    ("Alt+Tab (switch)", ["alt-tab"], True, lambda w: w is not None and w["active"]),
    ("Win+1 (first taskbar app)", ["meta_l-1"], False, None),
    ("Alt+F4 (close window)", ["alt-f4"], False, lambda w: w is None),
    ("Win+Z (snap layouts)", ["meta_l-z"], False,
     lambda w: any(p.get("title") == "Snap layouts" for p in guest("popups"))),
    ("Win+Z, 1, 1 (snap to the left half)", ["meta_l-z", "1", "1"], False,
     lambda w: snapped(w, 0, 800)),
    ("Win+Z, 3, 3 (snap to the right third)", ["meta_l-z", "3", "3"], False,
     lambda w: snapped(w, 1067, 533)),
]


def snapped(w, x, width):
    """Notepad's frame starts at x and is `width` wide, from the top of the screen to the taskbar."""
    if w is None or maximized(w):
        return False
    fx, fy, fw, fh = w["frame"]
    return abs(fx - x) <= 2 and abs(fw - width) <= 2 and fy <= 1 and 800 < fh < 900


def notepad():
    found = [w for w in win_ids(False).values() if w["class"] == "kwrite"]
    return found[0] if found else None


def sweep_shortcuts():
    tidy()
    time.sleep(2)
    baseline = st.grab()
    for label, combo in SHORTCUTS:
        def press(label=label, combo=combo):
            before = set(win_ids())
            pops_before = len(guest("popups"))
            keys(*combo)
            time.sleep(3)
            img = st.grab()
            path = shot("key-" + "".join(c if c.isalnum() else "-" for c in label)[:40])
            new = [w for i, w in win_ids().items() if i not in before]
            pops = len(guest("popups"))
            change = diff(baseline, img)
            locked = guest("stats")["locked"] == "yes"
            if "virtual desktop" in label:
                n = run(DESKTOP_COUNT).strip().splitlines()[-1:]
                return ("ok" if n == ["2"] else "fail"), f"desktops now {n}", path
            if "narrator" in label:
                return ("ok" if orca_on() else "fail"), f"Orca running: {orca_on()}", path
            what = "; ".join(f"{w['title']} [{w['class']}]" for w in new)[:120]
            if locked:
                tidy()
            if new or pops > pops_before or change > 3 or locked:
                return "look", f"reacted (screen change {change:.0f}; {what or 'popup/overlay'})", path
            return "fail", "nothing happened", path
        attempt("Shortcuts", label, press)
        keys("esc")
        if "magnifier" in label:
            keys("meta_l-0")  # back to actual size, or every later screenshot is zoomed in
        if "narrator" in label or "voice typing" in label:
            keys(*combo)  # both toggle: Narrator off again, the voice typing panel closed
        if "narrator" in label:
            time.sleep(3)
            record("Shortcuts", "Win+Ctrl+Enter again (narrator off)", "fail" if orca_on() else "ok",
                   f"Orca running: {orca_on()}")
        time.sleep(1)
        tidy()
        if "virtual desktop" in label:
            before = run(DESKTOP_COUNT).strip().splitlines()[-1:]
            keys("meta_l-ctrl-f4")
            time.sleep(1.5)
            after = run(DESKTOP_COUNT).strip().splitlines()[-1:]
            record("Shortcuts", "Win+Ctrl+F4 (close virtual desktop)", "ok" if after == ["1"] else "fail",
                   f"desktops before {before}, after {after}")
    for label, combo, second, check in WINDOW_SHORTCUTS:
        def press_with_window(label=label, combo=combo, second=second, check=check):
            before = set(win_ids())
            run(f"setsid kwrite {DOCS}/notes.txt >/dev/null 2>&1 < /dev/null &")
            if not wait_new(before, 15, "kwrite"):
                raise st.Failed("Notepad didn't open")
            if second:
                before = set(win_ids())
                run("setsid kcalc >/dev/null 2>&1 < /dev/null &")
                wait_new(before, 15, "kcalc")
            time.sleep(2)
            a = st.grab()
            for c in combo:
                keys(c)
                time.sleep(1)
            time.sleep(1.5)
            b = st.grab()
            path = shot("winkey-" + "".join(c if c.isalnum() else "-" for c in label)[:40])
            change = diff(a, b)
            if check:
                w = notepad()
                seen = "closed" if w is None else f"state {w['state']}, active {w['active']}, frame {w.get('frame')}"
                return ("ok" if check(w) else "fail"), f"Notepad: {seen}; screen change {change:.0f}", path
            return ("look" if change > 2 else "fail"), f"screen change {change:.0f}", path
        attempt("Shortcuts", label, press_with_window)
        tidy()


# ---- taskbar, tray, desktop ---------------------------------------------------------------------------
def sweep_taskbar():
    tidy()
    # The last item says whose pop-up must appear: a Glass shell menu (and its title), not KDE's.
    spots = [("Start button", (645, 877), "left", None), ("Search button", (697, 877), "left", None),
             ("Task view button", (748, 877), "left", None),
             ("Volume icon (Quick Settings)", (1427, 877), "left", "Quick Settings"),
             ("Network icon (Quick Settings)", (1461, 877), "left", "Quick Settings"),
             ("Third tray icon", (1491, 877), "left", None), ("Tray overflow (^)", (1519, 877), "left", None),
             ("Clock / calendar", (1560, 877), "left", None),
             ("Right-click volume icon", (1427, 877), "right", ""),
             ("Right-click taskbar", (1100, 877), "right", ""),
             ("Right-click Start button", (645, 877), "right", ""),
             ("Right-click desktop", (900, 400), "right", ""),
             ("Right-click Recycle Bin", (58, 45), "right", "")]
    for label, (x, y), button, glass in spots:
        def poke(x=x, y=y, button=button, label=label, glass=glass):
            qmp = st.qmp
            qmp.pointer(qmp.connect(), x, y, 1, button)
            time.sleep(2.5)
            path = shot("tray-" + "".join(c if c.isalnum() else "-" for c in label)[:30])
            if glass is None:
                return "look", "", path
            pops = guest("popups")
            ours = [p for p in pops if "glasspanes" in (p.get("program") or "")
                    and glass in (p.get("title") or "")]
            kde = [p for p in pops if "plasmashell" in (p.get("program") or "")
                   and not any("TOOLTIP" in t for t in p.get("types", []))]
            seen = "; ".join(f"{p.get('title')!r} [{p.get('program', '')[:40]}]" for p in pops)[:160]
            return ("ok" if ours and not kde else "fail"), f"popups: {seen or 'none'}", path
        attempt("Taskbar & desktop", label, poke)
        keys("esc")
        time.sleep(1)

    def win_a():
        keys("meta_l-a")
        time.sleep(2)
        pops = guest("popups")
        path = shot("quick-settings-win-a")
        keys("esc")
        found = any(p.get("title") == "Quick Settings" for p in pops)
        return ("ok" if found else "fail"), "Win+A opened Quick Settings" if found else "no Quick Settings", path
    attempt("Taskbar & desktop", "Win+A opens Quick Settings", win_a)

    def recycle_icon():
        before = set(win_ids())
        st.click(58, 45, 2)
        new = wait_new(before, 15)
        time.sleep(3)
        path = shot("desktop-recycle-bin-open")
        return ("look" if new else "fail"), "double-clicked the Recycle Bin icon", path
    attempt("Taskbar & desktop", "Open Recycle Bin from the desktop", recycle_icon)

    def start_views():
        keys("meta_l")
        time.sleep(1.5)
        p1 = shot("start-menu")
        st.click(1025, 210)  # All apps
        time.sleep(1.5)
        p2 = shot("start-all-apps")
        keys("esc", "esc")
        time.sleep(1)  # Start ignores being toggled again within 0.3 s of closing
        keys("meta_l")
        time.sleep(1.5)
        st.click(1047, 808)  # power button in Start
        time.sleep(1.5)
        p3 = shot("start-power-menu")
        keys("esc", "esc")
        time.sleep(1)
        keys("meta_l")
        time.sleep(1)
        st.type_text("12*3")
        time.sleep(1.5)
        p4 = shot("start-search-calculator")
        keys("esc")
        return "look", f"Start, All apps, power menu, calculator search ({os.path.basename(p2)}, {os.path.basename(p3)}, {os.path.basename(p4)})", p1
    attempt("Taskbar & desktop", "Start menu views", start_views)


# ---- everyday things that must actually work ------------------------------------------------------------
def sweep_functions():
    def store():
        before = set(win_ids())
        run("setsid plasma-discover --search firefox >/dev/null 2>&1 < /dev/null &")
        new = wait_new(before, 30)
        for _ in range(20):
            time.sleep(2)
            t = " ".join(w["title"] for w in win_ids().values())
            if "items" in t:
                break
        path = shot("store-search")
        import re
        m = re.search(r"(\d+)\+? items", t)
        if not m or int(m.group(1)) == 0:
            return "fail", f"no search results ({t[:100]})", path
        return "look", f"{m.group(1)} results for 'firefox'", path
    attempt("Everyday", "Store search", store)

    def store_home():
        before = set(win_ids())
        run("setsid plasma-discover >/dev/null 2>&1 < /dev/null &")
        wait_new(before, 30)
        time.sleep(12)
        return "look", "Store home page", shot("store-home")
    attempt("Everyday", "Store home page", store_home)

    def store_install():
        out = run("pkcon -y --noninteractive install kmines 2>&1 | tail -2; dpkg -l kmines | grep -c ^ii", 300)
        ok = out.strip().endswith("1")
        return ("ok" if ok else "fail"), "installed KMines without a password" if ok else out[-200:]
    attempt("Everyday", "Store install (Debian app, no password)", store_install)

    def flathub_install():
        out = run("timeout 600 flatpak install -y --noninteractive --system flathub io.mpv.Mpv 2>&1 | tail -1; "
                  "flatpak list --app --columns=application", 630)
        return ("ok" if "io.mpv.Mpv" in out else "fail"), out.strip()[-150:]
    attempt("Everyday", "Store install (Flathub app, no password)", flathub_install)

    def web():
        before = set(win_ids())
        run("setsid firefox-esr https://en.wikipedia.org/wiki/Window >/dev/null 2>&1 < /dev/null &")
        new = wait_new(before, 60, "Wikipedia")
        time.sleep(5)
        path = shot("web-wikipedia")
        return ("look" if new else "fail"), "Wikipedia page" if new else "page title never appeared", path
    attempt("Everyday", "Browse a real website", web)

    def sound():
        out = run("pactl info | grep -E 'Server Name|Default Sink'; pactl list short sinks; "
                  f"timeout 10 paplay {DOCS}/tone.wav && echo played")
        ok = "played" in out and "Default Sink" in out
        return ("ok" if ok else "fail"), out.strip().replace("\n", " | ")[:200]
    attempt("Everyday", "Sound output plays a sound", sound)

    def printing():
        out = run("systemctl is-active cups; lpstat -r; lpstat -p -d 2>&1 | head -5")
        ok = "active" in out and "is running" in out
        return ("ok" if ok else "fail"), out.strip().replace("\n", " | ")[:200]
    attempt("Everyday", "Printing service", printing)

    def screenshot_file():
        out = run("rm -f ~/Pictures/sweep-shot.png; timeout 20 spectacle -b -n -f -o ~/Pictures/sweep-shot.png; "
                  "sleep 1; stat -c %s ~/Pictures/sweep-shot.png", 40)
        size = out.strip().splitlines()[-1] if out.strip() else "0"
        ok = size.isdigit() and int(size) > 10000
        return ("ok" if ok else "fail"), f"saved a screenshot file ({size} bytes)"
    attempt("Everyday", "Save a screenshot to Pictures", screenshot_file)

    def network():
        out = run("nmcli -t -f STATE,CONNECTIVITY general; nmcli -t -f NAME,TYPE con show --active")
        return ("ok" if "full" in out else "fail"), out.strip().replace("\n", " | ")[:200]
    attempt("Everyday", "Network connected", network)

    def notification():
        before = set(win_ids())
        run("notify-send -t 15000 'Sweep test' 'This is a notification'")
        pops = []
        for _ in range(8):
            time.sleep(1)
            pops = [w for i, w in win_ids().items() if i not in before
                    and any("NOTIFICATION" in t for t in w["types"])]
            if pops:
                break
        path = shot("notification")
        if not pops:
            return "fail", "no notification popup appeared", path
        return "look", f"popup shown ({pops[0]['class']})", path
    attempt("Everyday", "Notifications appear", notification)


def sweep_sleep():
    """Last, because a machine that doesn't come back takes the rest of the sweep with it."""
    def sleep_wake():
        run(f"(sleep 2; {st.sudo('systemctl suspend')}) >/dev/null 2>&1 &", 10)
        time.sleep(15)
        dark = st.brightness(st.grab()) < 20
        st.qmp.command(st.qmp.connect(), "system_wakeup")
        time.sleep(10)
        st.click(800, 450)
        time.sleep(3)
        path = shot("after-wake")
        locked = guest("stats", 30)["locked"]
        if locked == "yes":
            st.click(800, 450)
            time.sleep(2)
            st.type_text(st.PASSWORD + "\n")
            time.sleep(5)
        ok = guest("stats", 30)["locked"] == "no"
        return ("look" if ok else "fail"), f"slept (screen {'dark' if dark else 'still on'}), woke, " \
                                         f"{'asked for the password' if locked == 'yes' else 'did not lock'}", path
    attempt("Power", "Sleep and wake", sleep_wake)


# ---- report -----------------------------------------------------------------------------------------------
def write_report():
    lines = ["# Glass Panes feature sweep", "",
             f"{len(results)} checks: {sum(r['status'] == 'ok' for r in results)} passed automatically, "
             f"{sum(r['status'] == 'look' for r in results)} need a look at the screenshot, "
             f"{sum(r['status'] == 'fail' for r in results)} failed.", ""]
    area = None
    for r in results:
        if r["area"] != area:
            area = r["area"]
            lines += ["", f"## {area}", "", "| Check | Result | Details | Screenshot |", "|---|---|---|---|"]
        s = f"[{os.path.basename(r['shot'])}](shots/{os.path.basename(r['shot'])})" if r["shot"] else ""
        detail = r["detail"].replace("|", "/").replace("\n", " ")
        lines.append(f"| {r['name']} | {r['status']} | {detail} | {s} |")
    with open(os.path.join(OUT, "report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def load_report():
    """Results of an earlier, interrupted sweep, read back from its report."""
    area = None
    with open(os.path.join(OUT, "report.md")) as f:
        for line in f:
            if line.startswith("## "):
                area = line[3:].strip()
            elif line.startswith("| ") and not line.startswith(("| Check", "|---")):
                name, status, detail, s = [c.strip() for c in line.strip().strip("|").split(" | ")]
                path = os.path.join(SHOTS, s[1:s.index("]")]) if s else None
                results.append(dict(area=area, name=name, status=status, detail=detail, shot=path))


def contact_sheets():
    d = os.path.join(OUT, "sheets")
    os.makedirs(d, exist_ok=True)
    files = sorted(f for f in os.listdir(SHOTS) if f.endswith(".jpg"))
    for n in range(0, len(files), 6):
        sheet = Image.new("RGB", (2 * 800, 3 * 470), "white")
        for k, f in enumerate(files[n:n + 6]):
            img = Image.open(os.path.join(SHOTS, f)).resize((800, 450))
            x, y = (k % 2) * 800, (k // 2) * 470
            sheet.paste(img, (x, y + 20))
            ImageDraw.Draw(sheet).text((x + 6, y + 4), f, fill="black")
        sheet.save(os.path.join(d, f"sheet-{n // 6 + 1:02d}.jpg"), quality=85)


def main():
    global BASE
    parts = [sweep_files, sweep_apps, sweep_settings, sweep_windows_apps, sweep_functions,
             sweep_taskbar, sweep_shortcuts, sweep_sleep]
    os.makedirs(SHOTS, exist_ok=True)
    if "--from" in sys.argv:
        start = sys.argv[sys.argv.index("--from") + 1]
        parts = parts[[p.__name__ for p in parts].index(f"sweep_{start}"):]
        redo = {p.__name__ for p in parts}
        areas = {"sweep_files": "Files", "sweep_apps": "Apps", "sweep_settings": "Settings",
                 "sweep_windows_apps": "Windows apps", "sweep_functions": "Everyday",
                 "sweep_taskbar": "Taskbar & desktop", "sweep_shortcuts": "Shortcuts", "sweep_sleep": "Power"}
        redo_areas = {areas[n] for n in redo}
        load_report()
        results[:] = [r for r in results if r["area"] not in redo_areas
                      and not (r["area"] == "Sweep" and r["name"] in redo)]
        shot_no[0] = max([int(f[:3]) for f in os.listdir(SHOTS) if f[:3].isdigit()] or [0])
    else:
        for f in os.listdir(SHOTS):
            os.remove(os.path.join(SHOTS, f))
    if "--only" in sys.argv:
        parts = parts[:1]
    running = subprocess.run(["pgrep", "-f", f"^qemu-system.*{st.VM_DIR}"], capture_output=True, text=True)
    if "--attach" in sys.argv:
        # Use the VM that is already running and signed in, and leave it running afterwards.
        st.S.qemu_pid = int(running.stdout.split()[0])
        BASE = desktop_ids()
        for part in parts:
            st.note(f"=== {part.__name__} ===")
            part()
            tidy()
        write_report()
        return
    if running.returncode == 0:
        raise SystemExit("the sweep VM is already running")
    subprocess.Popen(["scripts/run-qemu.sh", "--installed", "--uefi", "--headless", "--std-vga", "--vm-dir", st.VM_DIR],
                     cwd=ROOT, stdout=open(os.path.join(OUT, "qemu.log"), "w"), stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    time.sleep(5)
    st.S.qemu_pid = int(subprocess.run(["pgrep", "-f", f"^qemu-system.*{st.VM_DIR}"], capture_output=True,
                                       text=True).stdout.split()[0])
    time.sleep(30)
    st.sign_in("sweep-sign-in")
    time.sleep(10)
    BASE = desktop_ids()
    for part in parts:
        st.note(f"=== {part.__name__} ===")
        try:
            part()
        except Exception as e:
            record("Sweep", part.__name__, "fail", f"the section stopped: {e!r}"[:300])
            try:
                st.recover_agent(str(e))
            except Exception:
                pass
        tidy()
    write_report()
    contact_sheets()
    st.note("sweep finished")
    try:
        st.qmp.command(st.qmp.connect(), "system_powerdown")
    except Exception:
        pass


if __name__ == "__main__":
    main()
