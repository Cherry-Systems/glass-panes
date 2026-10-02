#!/usr/bin/env python3
"""Drive a running QEMU VM through its QMP socket: screenshots, keyboard, mouse.

  qmp.py shot OUT.png              screenshot of the guest display (needs python3-pil)
  qmp.py keys ctrl-alt-t ret       key combos, qcode names joined with "-"
  qmp.py type 'echo hi'            type text (US layout; shifted characters handled)
  qmp.py click X Y [left|right]    move and click; X/Y are guest pixels from the screenshot
  qmp.py dclick X Y                double-click
  qmp.py move X Y                  move only

Socket: $QMP_SOCK, default ./build/vm/qmp.sock. The VM needs
  -qmp unix:PATH,server=on,wait=off   and, for absolute clicks,   -device qemu-xhci -device usb-tablet
"""
import json
import os
import socket
import sys
import tempfile
import time

SOCK = os.environ.get("QMP_SOCK", "build/vm/qmp.sock")

SHIFTED = set('~!@#$%^&*()_+{}|:"<>?ABCDEFGHIJKLMNOPQRSTUVWXYZ')
QCODES = {
    " ": "spc", "-": "minus", "=": "equal", ".": "dot", ",": "comma", "/": "slash", ";": "semicolon",
    "'": "apostrophe", "\n": "ret", "\t": "tab", "\\": "backslash", "[": "bracket_left", "]": "bracket_right",
    "`": "grave_accent", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
    "(": "9", ")": "0", "_": "minus", "+": "equal", "{": "bracket_left", "}": "bracket_right",
    "|": "backslash", ":": "semicolon", '"': "apostrophe", "<": "comma", ">": "dot", "?": "slash",
    "~": "grave_accent",
}


def connect():
    s = socket.socket(socket.AF_UNIX)
    s.connect(SOCK)
    f = s.makefile("rw")
    f.readline()
    command(f, "qmp_capabilities")
    return f


def command(f, name, **args):
    f.write(json.dumps({"execute": name, "arguments": args}) + "\n")
    f.flush()
    while True:
        reply = json.loads(f.readline())
        if "error" in reply:
            print(reply["error"], file=sys.stderr)
            return reply
        if "return" in reply:
            return reply


def screendump(f, path):
    command(f, "screendump", filename=os.path.abspath(path))


def screen_size(f):
    with tempfile.NamedTemporaryFile(suffix=".ppm") as tmp:
        screendump(f, tmp.name)
        tmp.readline()
        return tuple(map(int, tmp.readline().split()))


def send_key(f, names):
    command(f, "send-key", keys=[{"type": "qcode", "data": n} for n in names])


def pointer(f, x, y, clicks, button):
    w, h = screen_size(f)
    command(f, "input-send-event", events=[
        {"type": "abs", "data": {"axis": "x", "value": x * 32767 // (w - 1)}},
        {"type": "abs", "data": {"axis": "y", "value": y * 32767 // (h - 1)}},
    ])
    time.sleep(0.1)
    for _ in range(clicks):
        for down in (True, False):
            command(f, "input-send-event", events=[{"type": "btn", "data": {"down": down, "button": button}}])
            time.sleep(0.05)
        time.sleep(0.05)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    f = connect()
    op, rest = sys.argv[1], sys.argv[2:]
    if op == "shot":
        from PIL import Image
        ppm = rest[0] + ".ppm"
        screendump(f, ppm)
        Image.open(ppm).save(rest[0])
        os.remove(ppm)
    elif op == "keys":
        for combo in rest:
            send_key(f, combo.split("-"))
            time.sleep(0.15)
    elif op == "type":
        for ch in " ".join(rest):
            send_key(f, (["shift"] if ch in SHIFTED else []) + [QCODES.get(ch, ch.lower())])
            time.sleep(0.03)
    elif op in ("click", "dclick", "move"):
        clicks = {"click": 1, "dclick": 2, "move": 0}[op]
        pointer(f, int(rest[0]), int(rest[1]), clicks, rest[2] if len(rest) > 2 else "left")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
