#!/usr/bin/env python3
"""Soak test: uses an installed Glass Panes VM like a person would, for hours, and keeps notes.

  build/venv/bin/python tests/soak_test.py [--hours 6] [--stay-signed-in] [--as-installed]

Boots the disk left by tests/install_test.py (build/vm-install-test), signs in, then repeats a
round of everyday tasks (Start, Notepad, File Explorer, Settings, Task Manager, Run, a Windows
app, the browser, locking, themes...) with sign-outs, idle periods and restarts in between. After
every round it checks for crashed or restarted desktop parts, error dialogs, windows or programs
that didn't close, log errors and memory growth. Notes go to build/soak/notes.md as it runs.
Needs `python3 scripts/vm-shell.py serve` running on the host.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
VM_DIR = os.path.join(ROOT, os.environ.get("SOAK_VM_DIR", "build/vm-install-test"))
OUT = os.path.join(ROOT, os.environ.get("SOAK_OUT", "build/soak"))
SHOTS = os.path.join(OUT, "shots")
os.environ["QMP_SOCK"] = os.path.join(VM_DIR, "qmp.sock")
import qmp  # noqa: E402
from PIL import Image, ImageStat  # noqa: E402

PASSWORD = "glass123"
HOURS = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 6.0
G = "python3 /tmp/soak_guest.py"
# One long session (no sign-outs or restarts), so slow memory leaks can show up.
STAY = "--stay-signed-in" in sys.argv
SETTINGS_PAGES = ["display", "sound", "notifications", "power", "storage", "multitasking", "about",
                  "bluetooth", "printers", "mouse", "network", "background", "colors", "lockscreen",
                  "taskbar", "start", "installedapps", "defaultapps", "startup", "yourinfo", "signin",
                  "otherusers", "time_date", "language", "accessibility", "privacy", "update",
                  "windowsapps"]
# Each name's first letter is bracketed so the pattern doesn't match the shell running pkill.
APP_PROCS = r"[k]write|[d]olphin|[k]calc|[s]pectacle|[7]zFM|[f]irefox|[g]lasspanes\.settings|[g]lasspanes\.taskmgr"
# Notepad answers a polite close (or SIGTERM) with a "save changes?" prompt.
KILL_APPS = f"pkill -f '{APP_PROCS}'; sleep 2; pkill -KILL -f '{APP_PROCS}'; sleep 1"
# Known harmless log lines (Bluetooth file transfer asking for a GNOME service).
LOG_NOISE = re.compile(r"evolution-source-registry|org\.gnome\.evolution|90-alsa-restore\.rules"
                       r"|PAM (unable to dlopen|adding faulty module).*pam_(kwallet5|sss|fprintd)")


class Failed(Exception):
    pass


class AgentDown(Exception):
    pass


class State:
    started = time.time()
    cycle = 0
    qemu_pid = None
    actions = {}       # name -> {"ok": n, "fail": n, "secs": [..]}
    issues = {}        # key -> {...}
    samples = []       # resource samples
    observations = []
    log = []
    key_pids = {}
    last_check = time.time()
    finished = None


S = State()


# ---- notes -----------------------------------------------------------------------------------------
def note(msg):
    line = time.strftime("%H:%M:%S ") + (f"[round {S.cycle}] " if S.cycle else "") + msg
    print(line, flush=True)
    S.log.append(line)
    render()


def observe(msg):
    S.observations.append(time.strftime("%H:%M ") + msg)
    note("observation: " + msg)


def issue(text, shot=None, severity="problem"):
    key = re.sub(r"\d+", "#", text)[:160]
    i = S.issues.setdefault(key, {"text": text, "count": 0, "first": time.strftime("%H:%M"),
                                  "rounds": [], "shot": shot, "severity": severity})
    i["count"] += 1
    i["last"] = time.strftime("%H:%M")
    if S.cycle not in i["rounds"]:
        i["rounds"].append(S.cycle)
    if shot and not i["shot"]:
        i["shot"] = shot
    note(f"ISSUE ({severity}): {text}")


def fmt_mb(mb):
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb} MB"


def render():
    os.makedirs(OUT, exist_ok=True)
    el = (S.finished or time.time()) - S.started
    lines = ["# Glass Panes soak test notes", "",
             f"- Started: {time.strftime('%a %d %b %H:%M', time.localtime(S.started))}, "
             f"planned length {HOURS:g} h" + (", one session (no sign-outs or restarts)" if STAY else ""),
             f"- Status: {'finished ' + time.strftime('%H:%M', time.localtime(S.finished)) if S.finished else 'running'}"
             f", {el / 3600:.1f} h so far, {S.cycle} round(s) of tasks",
             "- System: the installed test VM (build/vm-install-test), 4 GB RAM, 4 CPUs, internet on", "",
             "## Issues found", ""]
    if not S.issues:
        lines.append("None so far.")
    for n, i in enumerate(sorted(S.issues.values(), key=lambda i: (i["severity"] != "critical", -i["count"])), 1):
        shot = f" ([screenshot](shots/{os.path.basename(i['shot'])}))" if i["shot"] else ""
        rounds = ", ".join(map(str, i["rounds"][:12])) + ("..." if len(i["rounds"]) > 12 else "")
        lines.append(f"{n}. **{i['severity']}**: {i['text']}{shot}  \n"
                     f"   Seen {i['count']} time(s), first {i['first']}, last {i['last']}, rounds {rounds}")
    lines += ["", "## How each task went", "", "| Task | Worked | Failed | Typical time |",
              "|---|---|---|---|"]
    for name, a in S.actions.items():
        secs = sorted(a["secs"])
        typical = f"{secs[len(secs) // 2]:.1f} s" if secs else "-"
        lines.append(f"| {name} | {a['ok']} | {a['fail']} | {typical} |")
    lines += ["", "## Resource use over time", "",
              "| Time | Memory used | Swap used | Load | Taskbar (plasmashell) | Window manager (kwin) "
              "| Glass shell | Disk used |", "|---|---|---|---|---|---|---|---|"]
    step = max(1, len(S.samples) // 30)
    picked = S.samples[::step] + ([S.samples[-1]] if S.samples and (len(S.samples) - 1) % step else [])
    for s in picked:
        lines.append(f"| {s['time']} | {fmt_mb(s['mem'])} | {fmt_mb(s['swap'])} | {s['load']:.2f} | "
                     f"{s['plasmashell']} MB | {s['kwin']} MB | {s['glass']} MB | {s['disk']} GB |")
    lines += ["", "## Observations", ""] + [f"- {o}" for o in S.observations] + \
             ["", "## Log (most recent last)", ""] + [f"    {line}" for line in S.log[-400:]]
    with open(os.path.join(OUT, "notes.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


# ---- VM input and screenshots ----------------------------------------------------------------------
def grab():
    f = qmp.connect()
    tmp = os.path.join(OUT, "grab.ppm")
    qmp.screendump(f, tmp)
    img = Image.open(tmp).convert("RGB")
    return img


def shot(name):
    img = grab()
    path = os.path.join(SHOTS, f"r{S.cycle:03d}-{name}.jpg")
    img.resize((1024, 576)).save(path, quality=80)
    return path


def brightness(img):
    return sum(ImageStat.Stat(img).mean) / 3


def keys(*combos):
    f = qmp.connect()
    for c in combos:
        qmp.send_key(f, c.split("-"))
        time.sleep(0.2)


def type_text(text):
    f = qmp.connect()
    for ch in text:
        qmp.send_key(f, (["shift"] if ch in qmp.SHIFTED else []) + [qmp.QCODES.get(ch, ch.lower())])
        time.sleep(0.04)


def click(x, y, n=1):
    qmp.pointer(qmp.connect(), x, y, n, "left")


def wait_for_screen(timeout, settle=6):
    end = time.time() + timeout
    prev = None
    while time.time() < end:
        img = grab()
        if brightness(img) > 100 and prev is not None and abs(brightness(img) - brightness(prev)) < 0.5:
            return True
        prev = img
        time.sleep(settle)
    return False


# ---- talking to the VM -----------------------------------------------------------------------------
def agents():
    out = subprocess.run(["ss", "-tnpH", "dport = :18765"], capture_output=True, text=True).stdout
    pids = {int(p.split("pid=")[1].split(",")[0]) for p in out.split() if "pid=" in p}
    return pids - {os.getpid()}


def run(cmd, timeout=60):
    others = agents() - {S.qemu_pid}
    if others:
        raise SystemExit(f"another VM (pid {others}) is connected to vm-shell; stopping so no "
                         "commands go to the wrong machine")
    mark = "@@" + uuid.uuid4().hex[:10] + "@@"
    req = urllib.request.Request("http://127.0.0.1:18765/run", data=f"echo {mark}; {cmd}".encode(),
                                 headers={"X-Timeout": str(timeout)})
    try:
        with urllib.request.urlopen(req, timeout=timeout + 5) as r:
            out = r.read().decode(errors="replace")
    except Exception as e:
        raise AgentDown(str(e))
    if not out.startswith(mark):
        raise AgentDown(out[:200])
    return out[len(mark) + 1:]


def guest(args, timeout=60):
    out = run(f"{G} {args}", timeout).strip()
    if out.splitlines()[-1:] == ["ok"]:
        return True
    try:
        return json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        raise Failed(f"helper said: {out[-300:]}")


def wait_window(pattern, secs=10):
    r = guest(f"wait '{pattern}' {secs}", secs + 30)
    if not r["ok"]:
        raise Failed(f"no window matching '{pattern}' within {secs} s")
    return r


def wait_gone(pattern, secs=10):
    r = guest(f"gone '{pattern}' {secs}", secs + 30)
    if not r["ok"]:
        titles = ", ".join(w.get("title") or w.get("class") for w in r["windows"])
        raise Failed(f"window still open {secs} s after closing it: {titles}")
    return r


def sudo(cmd):
    return f"echo {PASSWORD} | sudo -S -p '' {cmd}"


def start_agent():
    keys("ctrl-alt-t")
    time.sleep(5)
    type_text("setsid bash -c 'curl -s 10.0.2.2:18765/files/tests/soak_agent.sh | bash' "
              ">/dev/null 2>&1 < /dev/null & exit\n")
    for _ in range(20):
        time.sleep(1)
        if S.qemu_pid in agents():
            run("curl -s 10.0.2.2:18765/files/tests/soak_guest.py -o /tmp/soak_guest.py && echo ok")
            return True
    return False


def sign_in(label):
    """From the lock or sign-in screen to a desktop with the agent connected."""
    t0 = time.time()
    if not wait_for_screen(300):
        issue(f"{label}: the screen stayed dark or kept changing for 5 minutes", shot(label + "-dark"),
              "critical")
    click(800, 450)
    time.sleep(2)
    type_text(PASSWORD + "\n")
    t1 = time.time()
    time.sleep(12)
    wait_for_screen(120)
    if not start_agent():
        shot_path = shot(label + "-no-agent")
        raise AgentDown(f"{label}: couldn't open a terminal after signing in ({shot_path})")
    S.key_pids = {}
    return t1 - t0, time.time() - t1


# ---- tasks -----------------------------------------------------------------------------------------
def t_start_notepad():
    keys("meta_l")
    r = wait_window("^Start$", 5)
    type_text("notepad")
    time.sleep(1.5)
    keys("ret")
    wait_window("kwrite", 15)
    time.sleep(1)
    type_text(f"Soak test round {S.cycle}")
    keys("ctrl-s")
    wait_window("save", 10)
    time.sleep(1)
    keys("ctrl-a")
    type_text(f"soak-{S.cycle}.txt\n")
    time.sleep(2)
    found = run(f"find ~ -maxdepth 3 -name soak-{S.cycle}.txt -exec cat {{}} \\;").strip()
    if f"Soak test round {S.cycle}" not in found:
        raise Failed(f"the saved file is missing or wrong (got {found[:80]!r})")
    keys("alt-f4")
    wait_gone("kwrite", 10)
    return f"Start opened in {r['secs']} s; typed, saved and closed a file"


def t_explorer():
    keys("meta_l-e")
    r = wait_window("dolphin", 10)
    time.sleep(1)
    keys("alt-f4")
    wait_gone("dolphin", 10)
    return f"Win+E opened File Explorer in {r['secs']} s"


def t_settings_shortcut():
    keys("meta_l-i")
    r = wait_window("^Settings$", 10)
    time.sleep(1)
    keys("alt-f4")
    wait_gone("^Settings$", 10)
    return f"Win+I opened Settings in {r['secs']} s"


def t_settings_pages():
    pages = [SETTINGS_PAGES[(S.cycle * 4 + i) % len(SETTINGS_PAGES)] for i in range(4)]
    for p in pages:
        run(f"setsid glass-settings --page {p} > /tmp/gs-{p}.log 2>&1 < /dev/null &")
        wait_window("^Settings$", 15)
        time.sleep(2.5)
        shot(f"settings-{p}")
        guest("close '^Settings$'")
        wait_gone("^Settings$", 10)
        log = run(f"cat /tmp/gs-{p}.log")
        if "Traceback" in log:
            issue(f"Settings page '{p}' raised a Python error: {log.strip().splitlines()[-1][:200]}",
                  shot(f"settings-{p}-error"))
    return "pages " + ", ".join(pages)


def t_taskmgr():
    keys("ctrl-shift-esc")
    r = wait_window("Task Manager", 10)
    time.sleep(6)
    keys("alt-f4")
    wait_gone("Task Manager", 10)
    return f"Ctrl+Shift+Esc opened Task Manager in {r['secs']} s"


def t_run_calc():
    keys("meta_l-r")
    wait_window("^Run$", 5)
    type_text("calc\n")
    r = wait_window("kcalc|calculator", 10)
    time.sleep(1)
    type_text("12*12=")
    time.sleep(1)
    keys("alt-f4")
    wait_gone("kcalc|calculator", 10)
    return f"Win+R, 'calc' opened Calculator in {r['secs']} s"


def t_winx():
    keys("meta_l-x")
    time.sleep(1.5)
    pops = guest("popups")
    shot("winx")
    keys("esc")
    if not any("glasspanes" in (p.get("program") or "") for p in pops):
        raise Failed("Win+X didn't show the quick link menu")
    return "Win+X menu shown"


def t_search():
    keys("meta_l-s")
    wait_window("^Start$", 5)
    type_text("display")
    time.sleep(1.5)
    shot("search")
    keys("esc")
    wait_gone("^Start$", 5)
    return "Win+S search opened and closed"


def t_alt_tab():
    run("setsid dolphin >/dev/null 2>&1 < /dev/null & setsid kcalc >/dev/null 2>&1 < /dev/null &")
    wait_window("dolphin", 15)
    wait_window("kcalc", 15)
    time.sleep(2)
    a1 = guest("active")
    keys("alt-tab")
    time.sleep(1.5)
    a2 = guest("active")
    keys("meta_l-d")
    time.sleep(1.5)
    shot("show-desktop")
    keys("meta_l-d")
    time.sleep(1)
    guest("close 'dolphin|kcalc'")
    wait_gone("dolphin|kcalc", 10)
    if not a1 or not a2 or a1["id"] == a2["id"]:
        raise Failed("Alt+Tab didn't switch to the other window")
    return f"Alt+Tab switched {a1['class']} -> {a2['class']}; Win+D toggled"


def t_snip():
    keys("meta_l-shift-s")
    up = False
    for _ in range(16):
        time.sleep(0.5)
        if run("pgrep -x spectacle >/dev/null && echo yes").strip() == "yes":
            up = True
            break
    shot("snip")
    keys("esc")
    if not up:
        raise Failed("Win+Shift+S didn't start the Snipping Tool")
    for _ in range(10):
        time.sleep(1)
        if not run("pgrep -x spectacle").strip():
            return "Snipping Tool opened and cancelled"
    raise Failed("Snipping Tool kept running after Esc")


def t_lock():
    keys("meta_l-l")
    time.sleep(4)
    if guest("stats")["locked"] != "yes":
        raise Failed("Win+L didn't lock the session")
    shot("locked")
    click(800, 450)
    time.sleep(2)
    type_text(PASSWORD + "\n")
    time.sleep(4)
    if guest("stats")["locked"] != "no":
        raise Failed("the session stayed locked after typing the password")
    return "locked and unlocked"


def appearance(changes):
    py = f"from glasspanes import appearance; appearance.apply({changes!r})"
    run(f'cd /usr/lib/glasspanes && python3 -c "{py}"', 90)


def t_themes():
    appearance({"mode": "dark"})
    time.sleep(4)
    shot("dark")
    appearance({"mode": "light"})
    time.sleep(4)
    return "dark mode and back"


def t_taskbar():
    check = "from glasspanes import appearance as a; print(a.taskbar_plan(a._taskbar_layout()['widgets']))"
    for align in ("left", "center"):
        appearance({"taskbar_align": align})
        time.sleep(3)
        shot(f"taskbar-{align}")
        if run(f'cd /usr/lib/glasspanes && python3 -c "{check}"').strip() == "None":
            raise Failed(f"taskbar layout damaged after switching to {align}")
    return "left and back to centre"


SEVENZIP = "~/.wine/drive_c/Program\\ Files/7-Zip/7zFM.exe"


def t_windows_app():
    if run(f"test -f {SEVENZIP} && echo yes").strip() != "yes":
        out = run("cd ~/Downloads && (curl -sfLO https://www.7-zip.org/a/7z2409-x64.exe || "
                  "curl -sfLO https://www.7-zip.org/a/7z2408-x64.exe) && ls 7z*.exe", 120).strip()
        if not out.endswith(".exe"):
            raise Failed("couldn't download the 7-Zip installer")
        t0 = time.time()
        run(f"cd ~/Downloads && timeout 300 wine {out.splitlines()[-1]} /S; sleep 3", 330)
        if run(f"test -f {SEVENZIP} && echo yes").strip() != "yes":
            raise Failed("7-Zip's installer finished but 7-Zip isn't installed")
        observe(f"7-Zip (a Windows app) installed silently in {time.time() - t0:.0f} s")
    keys("meta_l")
    wait_window("^Start$", 5)
    type_text("7-Zip")
    time.sleep(2)
    shot("start-7zip")
    keys("ret")
    r = wait_window("7zfm", 45)
    time.sleep(2)
    keys("alt-f4")
    wait_gone("7zfm", 15)
    time.sleep(5)
    if run("pgrep -f 7zFM.exe").strip():
        raise Failed("7-Zip's process kept running after its window closed")
    return f"opened 7-Zip from Start in {r['secs']} s and closed it"


def t_browser():
    keys("meta_l-r")
    wait_window("^Run$", 5)
    type_text("https://example.com\n")
    r = wait_window("Example Domain", 60)
    time.sleep(3)
    keys("alt-f4")
    wait_gone("Example Domain|firefox", 20)
    return f"Run opened a web page in the browser in {r['secs']} s"


TASKS = [("Start + Notepad + save", t_start_notepad), ("File Explorer (Win+E)", t_explorer),
         ("Settings (Win+I)", t_settings_shortcut), ("Settings pages", t_settings_pages),
         ("Task Manager (Ctrl+Shift+Esc)", t_taskmgr), ("Run + Calculator (Win+R)", t_run_calc),
         ("Quick link menu (Win+X)", t_winx), ("Search (Win+S)", t_search),
         ("Alt+Tab and Win+D", t_alt_tab), ("Snipping Tool (Win+Shift+S)", t_snip),
         ("Lock and unlock (Win+L)", t_lock), ("Windows app (7-Zip)", t_windows_app),
         ("Web browser", t_browser)]
EVERY_OTHER = [("Dark/light mode", t_themes), ("Taskbar alignment", t_taskbar)]


# ---- running tasks and recovering ------------------------------------------------------------------
def tidy():
    """Back to an empty desktop after a failed task."""
    keys("esc", "esc")
    time.sleep(1)
    try:
        st = guest("stats")
        if st["locked"] == "yes":
            click(800, 450)
            time.sleep(2)
            type_text(PASSWORD + "\n")
            time.sleep(4)
        guest("close '.'")
        time.sleep(3)
        run(KILL_APPS)
    except (Failed, AgentDown):
        pass


def recover_agent(why):
    note(f"lost contact with the VM ({why}); recovering")
    for attempt in range(3):
        keys("esc")
        time.sleep(2)
        img = grab()
        if brightness(img) < 20:
            click(800, 450)
            time.sleep(3)
        try:
            if start_agent():
                return
        except AgentDown:
            pass
        try:
            sign_in(f"recover{attempt}")
            return
        except AgentDown:
            pass
    issue("the VM stopped responding and had to be reset", shot("unresponsive"), "critical")
    qmp.command(qmp.connect(), "system_reset")
    time.sleep(40)
    sign_in("after-reset")


def do(name, fn):
    a = S.actions.setdefault(name, {"ok": 0, "fail": 0, "secs": []})
    t0 = time.time()
    try:
        detail = fn()
        a["ok"] += 1
        a["secs"].append(time.time() - t0)
        note(f"{name}: OK ({time.time() - t0:.1f} s) {detail}")
        return True
    except Failed as e:
        a["fail"] += 1
        issue(f"{name}: {e}", shot(re.sub(r"\W+", "-", name.lower()).strip("-") + "-fail"))
    except AgentDown as e:
        a["fail"] += 1
        issue(f"{name}: lost contact with the VM ({e})", shot("agent-lost"))
        recover_agent(str(e))
    tidy()
    return False


def health(after_restart=False):
    st = guest("stats")
    procs = st["procs"]
    S.samples.append({"time": time.strftime("%H:%M"), "mem": st["mem_used"], "swap": st["swap_used"],
                      "load": st["load"][0], "disk": st["disk_used_gb"],
                      "plasmashell": procs.get("plasmashell", {}).get("rss", 0),
                      "kwin": procs.get("kwin_x11", {}).get("rss", 0),
                      "glass": procs.get("glasspanes.shell", {}).get("rss", 0)})
    for k in ("plasmashell", "kwin_x11", "glasspanes.shell", "Xorg", "kglobalacceld"):
        pid = procs.get(k, {}).get("pid")
        if pid is None:
            issue(f"{k} is not running", shot(f"missing-{k}"), "critical")
        elif S.key_pids.get(k) and S.key_pids[k] != pid and not after_restart:
            issue(f"{k} restarted on its own (crash?)", shot(f"restart-{k}"))
        S.key_pids[k] = pid
    since = int(S.last_check)
    S.last_check = time.time()
    errs = run(sudo(f"journalctl -b -p err --since @{since} -q --no-pager -o cat") +
               " | sort | uniq -c | sort -rn | head -15").strip()
    for line in errs.splitlines():
        if line.strip() and not LOG_NOISE.search(line):
            issue("system log error: " + line.strip().split(None, 1)[-1][:220], severity="log")
    crashes = run(f"journalctl --user --since @{since} -q --no-pager -o cat | grep -iE "
                  "'traceback|segfault|core dumped|dumped core|kcrash: application|crashed' | "
                  "grep -v drkonqi | sort | uniq -c | head -10; " +
                  sudo(f"journalctl -b -k --since @{since} -q --no-pager -o cat") +
                  " | grep -i 'segfault' | head -5").strip()
    for line in crashes.splitlines():
        if line.strip():
            issue("crash or error in the session log: " + line.strip()[:220])
    leftover = [w for w in guest("windows") if w["class"] not in ("plasmashell",)]
    if leftover:
        issue("windows left open after the round: " +
              ", ".join(f"{w['title']} ({w['class']})" for w in leftover), shot("leftover"))
        guest("close '.'")
    procs_left = run(f"sleep 3; pgrep -af '{APP_PROCS}' | grep -v pgrep").strip()
    if procs_left:
        issue("programs still running after their windows closed: " +
              "; ".join(p.split(None, 1)[-1][:60] for p in procs_left.splitlines()))
        run(KILL_APPS)
    if len(S.samples) >= 6:
        first, last = S.samples[1], S.samples[-1]
        for k, label in (("plasmashell", "Taskbar (plasmashell)"), ("kwin", "Window manager (kwin)"),
                         ("glass", "Glass shell")):
            if first[k] and last[k] > first[k] * 1.5 and last[k] - first[k] > 80:
                issue(f"{label} memory keeps growing: {first[k]} MB at {first['time']} -> "
                      f"{last[k]} MB at {last['time']}", severity="leak?")


def idle_period():
    note("leaving the PC alone for 12 minutes")
    time.sleep(12 * 60)
    img = grab()
    dark = brightness(img) < 20
    shot("after-idle")
    click(800, 450)  # wake
    time.sleep(3)
    img2 = grab()
    st = guest("stats")
    observe(f"after 12 idle minutes the screen was {'off' if dark else 'on'} and the session "
            f"{'locked' if st['locked'] == 'yes' else 'not locked'}")
    if brightness(img2) < 20:
        issue("the screen didn't come back on after moving the mouse", shot("no-wake"), "critical")
    if st["locked"] == "yes":
        click(800, 450)
        time.sleep(2)
        type_text(PASSWORD + "\n")
        time.sleep(4)
        if guest("stats")["locked"] != "no":
            issue("couldn't unlock after the idle period", shot("idle-unlock"), "critical")


def sign_out_and_in():
    note("signing out and back in")
    try:
        run("(sleep 1; qdbus6 org.kde.Shutdown /Shutdown logout) >/dev/null 2>&1 &", 10)
    except AgentDown:
        pass
    time.sleep(10)
    pw_to_screen, to_ready = sign_in("sign-in")
    observe(f"signed back in: desktop ready {to_ready:.0f} s after the password")
    health(after_restart=True)


def restart_pc():
    note("restarting the PC")
    try:
        run(f"(sleep 2; {sudo('systemctl reboot')}) >/dev/null 2>&1 &", 10)
    except AgentDown:
        pass
    t0 = time.time()
    time.sleep(15)
    if not wait_for_screen(300):
        issue("no sign-in screen within 5 minutes of restarting", shot("restart-stuck"), "critical")
    observe(f"restart took {time.time() - t0:.0f} s from clicking restart to the sign-in screen")
    sign_in("after-restart")
    health(after_restart=True)


# ---- main ------------------------------------------------------------------------------------------
def sync_code():
    """Test the desktop code in this checkout rather than what was on the disk at install time."""
    subprocess.run(["tar", "-czf", os.path.join(OUT, "code.tar.gz"), "-C", os.path.join(ROOT, "desktop/lib"),
                    "glasspanes"], check=True)
    rel = os.path.relpath(os.path.join(OUT, "code.tar.gz"), ROOT)
    out = run(f"curl -s 10.0.2.2:18765/files/{rel} -o /tmp/code.tar.gz && " +
              sudo("tar -xzf /tmp/code.tar.gz -C /usr/lib/glasspanes") + " && "
              "pkill -f '^python3 -m glasspanes.shell'; sleep 1; "
              "setsid glass-shell --daemon >/dev/null 2>&1 < /dev/null & sleep 4; echo synced", 60)
    if "synced" not in out:
        issue(f"couldn't copy the current desktop code into the VM: {out.strip()[-200:]}")
    else:
        observe("tested the desktop code from this checkout (copied over the installed copy)")


def main():
    os.makedirs(SHOTS, exist_ok=True)
    for f in os.listdir(SHOTS):
        os.remove(os.path.join(SHOTS, f))
    if not os.path.exists(os.path.join(VM_DIR, "ssd.qcow2")):
        raise SystemExit("no installed disk in build/vm-install-test; run tests/install_test.py first")
    if subprocess.run(["pgrep", "-f", f"^qemu-system.*{VM_DIR}"], capture_output=True).returncode == 0:
        raise SystemExit("the test VM is already running")
    if subprocess.run(["ss", "-tlnH", "sport = :18765"], capture_output=True, text=True).stdout.strip() == "":
        subprocess.Popen([sys.executable, "scripts/vm-shell.py", "serve"], cwd=ROOT, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    subprocess.Popen(["scripts/run-qemu.sh", "--installed", "--uefi", "--headless", "--vm-dir", VM_DIR],
                     cwd=ROOT, stdout=open(os.path.join(OUT, "qemu.log"), "w"),
                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    time.sleep(5)
    S.qemu_pid = int(subprocess.run(["pgrep", "-f", f"^qemu-system.*{VM_DIR}"], capture_output=True,
                                    text=True).stdout.split()[0])
    note(f"VM started (pid {S.qemu_pid}); planned {HOURS:g} h")
    time.sleep(30)
    pw, ready = sign_in("first-sign-in")
    observe(f"first sign-in: desktop ready {ready:.0f} s after the password")
    run("rm -f ~/soak-*.txt ~/*/soak-*.txt")
    if "--as-installed" not in sys.argv:
        sync_code()
    health(after_restart=True)
    end = S.started + HOURS * 3600
    while time.time() < end:
        S.cycle += 1
        note(f"--- round {S.cycle} ---")
        tasks = TASKS + (EVERY_OTHER if S.cycle % 2 == 0 else [])
        for name, fn in tasks:
            if time.time() > end:
                break
            do(name, fn)
        try:
            health()
        except (Failed, AgentDown) as e:
            issue(f"health check failed: {e}", shot("health"))
            recover_agent(str(e))
        if time.time() > end:
            break
        try:
            if S.cycle % 12 == 0 and not STAY:
                restart_pc()
            elif S.cycle % 4 == 0 and not STAY:
                sign_out_and_in()
            elif S.cycle % 3 == 0:
                idle_period()
        except (Failed, AgentDown) as e:
            issue(f"{'restart' if S.cycle % 12 == 0 else 'sign-out/idle'} step failed: {e}", shot("periodic"))
            recover_agent(str(e))


def finish(*_):
    if S.finished:
        return
    S.finished = time.time()
    note("soak test finished")
    render()
    try:
        run(KILL_APPS, 20)
    except Exception:
        pass
    try:
        qmp.command(qmp.connect(), "system_powerdown")
        for _ in range(90):
            time.sleep(1)
            if subprocess.run(["pgrep", "-f", f"^qemu-system.*{VM_DIR}"],
                              capture_output=True).returncode != 0:
                break
        else:
            note("the VM didn't shut down within 90 s of pressing the power button; switched it off")
            qmp.command(qmp.connect(), "quit")
    except Exception:
        pass
    render()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, finish)
    os.makedirs(OUT, exist_ok=True)
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            issue(f"test stopped: {e.code}", severity="critical")
    except Exception as e:
        import traceback
        issue(f"the test script itself crashed: {e!r}", severity="critical")
        note(traceback.format_exc())
    finish()
