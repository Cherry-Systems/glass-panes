#!/usr/bin/env python3
"""Runs inside the test VM for tests/soak_test.py: looks at windows and collects health stats.

  soak_guest.py windows [all]           open windows as JSON (all: every type, e.g. Start)
  soak_guest.py closeid ID...           ask these windows to close
  soak_guest.py wait REGEX [SECS]       wait for a window whose title or class matches
  soak_guest.py gone REGEX [SECS]       wait until no window matches
  soak_guest.py close REGEX             ask matching windows to close (like Alt+F4)
  soak_guest.py popups                  menus and other popups on screen, with their program
  soak_guest.py active                  the focused window
  soak_guest.py stats                   memory, load, key processes, disk, lock state
"""
import json
import os
import re
import subprocess
import sys
import time

from Xlib import X, display, protocol

d = display.Display()
root = d.screen().root
A = {n: d.intern_atom(n) for n in (
    "_NET_CLIENT_LIST", "_NET_WM_NAME", "_NET_WM_PID", "UTF8_STRING", "_NET_ACTIVE_WINDOW",
    "_NET_CLOSE_WINDOW", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_NORMAL",
    "_NET_WM_WINDOW_TYPE_DIALOG")}
KEY_PROCS = ("plasmashell", "kwin_x11", "Xorg", "glasspanes.shell", "kglobalacceld", "ksmserver")


def prop(w, name, kind=X.AnyPropertyType):
    try:
        p = w.get_full_property(A[name] if name in A else d.intern_atom(name), kind)
        return p.value if p else None
    except Exception:
        return None


def info(w):
    try:
        title = prop(w, "_NET_WM_NAME", A["UTF8_STRING"])
        title = title.decode(errors="replace") if isinstance(title, bytes) else (w.get_wm_name() or "")
        cls = w.get_wm_class() or ("", "")
        pid = prop(w, "_NET_WM_PID")
        types = prop(w, "_NET_WM_WINDOW_TYPE")
        state = prop(w, "_NET_WM_STATE")
        return {"id": w.id, "title": title, "class": cls[1] or cls[0],
                "pid": int(pid[0]) if pid is not None and len(pid) else None,
                "types": [d.get_atom_name(t) for t in types] if types is not None else [],
                "state": [d.get_atom_name(s).replace("_NET_WM_STATE_", "") for s in state]
                if state is not None else []}
    except Exception:
        return None


def windows(all_types=False):
    """Windows the window manager is managing: normal windows and dialogs, or every kind (Start is
    a frameless utility window; the taskbar and desktop are also listed then)."""
    ids = prop(root, "_NET_CLIENT_LIST") or []
    active = prop(root, "_NET_ACTIVE_WINDOW")
    active = active[0] if active is not None and len(active) else None
    out = []
    for i in ids:
        w = info(d.create_resource_object("window", i))
        if w:
            w["active"] = i == active
        if w and (all_types or not w["types"] or any(t in w["types"] for t in (
                "_NET_WM_WINDOW_TYPE_NORMAL", "_NET_WM_WINDOW_TYPE_DIALOG"))):
            out.append(w)
    return out


def popups():
    out = []
    for w in root.query_tree().children:
        try:
            a = w.get_attributes()
            if a.override_redirect and a.map_state == X.IsViewable:
                geo = w.get_geometry()
                if geo.width > 20 and geo.height > 20:
                    i = info(w) or {"id": w.id}
                    i["program"] = cmdline(i.get("pid"))
                    i["size"] = [geo.width, geo.height]
                    out.append(i)
        except Exception:
            pass
    return out


def cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode(errors="replace").strip()
    except Exception:
        return ""


def matching(pattern, everything=True):
    rx = re.compile(pattern, re.I)
    found = [w for w in windows(all_types=everything) if rx.search(w["title"]) or rx.search(w["class"])]
    if everything:
        for p in popups():  # menus: frameless windows the window manager doesn't list
            if rx.search(p.get("title") or "") or rx.search(p.get("class") or ""):
                found.append(p)
    return found


def stats():
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            mem[k] = int(v.split()[0]) // 1024
    procs = {}
    top = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/status") as f:
                st = dict(line.split(":", 1) for line in f if ":" in line)
            rss = int(st.get("VmRSS", "0 kB").split()[0]) // 1024
            cmd = cmdline(pid)
            name = st["Name"].strip()
            top.append((rss, name if "python" not in name else (cmd.split(" -m ")[-1][:40] or name)))
            for k in KEY_PROCS:
                if k == name or (k.startswith("glasspanes") and k in cmd):
                    procs[k] = {"pid": int(pid), "rss": rss}
        except Exception:
            pass
    top.sort(reverse=True)
    load = open("/proc/loadavg").read().split()[:3]
    df = os.statvfs("/")
    locked = subprocess.run(["loginctl", "show-session", os.environ.get("XDG_SESSION_ID", "auto"),
                             "-p", "LockedHint", "--value"], capture_output=True, text=True).stdout.strip()
    return {"mem_used": mem["MemTotal"] - mem["MemAvailable"], "mem_total": mem["MemTotal"],
            "swap_used": mem["SwapTotal"] - mem["SwapFree"], "load": [float(x) for x in load],
            "procs": procs, "top": top[:8], "disk_used_gb": round((df.f_blocks - df.f_bavail) *
                                                                  df.f_frsize / 2**30, 2),
            "uptime": float(open("/proc/uptime").read().split()[0]), "locked": locked}


def main():
    op, args = sys.argv[1], sys.argv[2:]
    if op == "windows":
        print(json.dumps(windows(all_types=args[:1] == ["all"])))
    elif op == "closeid":
        for i in args:
            win = d.create_resource_object("window", int(i))
            ev = protocol.event.ClientMessage(window=win, client_type=A["_NET_CLOSE_WINDOW"],
                                              data=(32, [int(time.time()), 2, 0, 0, 0]))
            root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.flush()
        print("ok")
    elif op == "popups":
        print(json.dumps(popups()))
    elif op == "active":
        a = prop(root, "_NET_ACTIVE_WINDOW")
        print(json.dumps(info(d.create_resource_object("window", a[0])) if a is not None and a[0] else None))
    elif op in ("wait", "gone"):
        limit = float(args[1]) if len(args) > 1 else 10
        start = time.time()
        while True:
            found = matching(args[0])
            if (op == "wait") == bool(found):
                print(json.dumps({"ok": True, "secs": round(time.time() - start, 2),
                                  "windows": found}))
                return
            if time.time() - start > limit:
                print(json.dumps({"ok": False, "secs": limit, "windows": found}))
                return
            time.sleep(0.2)
    elif op == "close":
        for w in matching(args[0], everything=False):  # never the taskbar or desktop
            win = d.create_resource_object("window", w["id"])
            ev = protocol.event.ClientMessage(window=win, client_type=A["_NET_CLOSE_WINDOW"],
                                              data=(32, [int(time.time()), 2, 0, 0, 0]))
            root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.flush()
        print("ok")
    elif op == "stats":
        print(json.dumps(stats()))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
