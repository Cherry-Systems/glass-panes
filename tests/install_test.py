#!/usr/bin/env python3
"""Unattended install test: boots the ISO in a fresh UEFI VM, clicks through the installer like a
user would, reboots into the installed system, signs in and runs health checks.

  build/venv/bin/python tests/install_test.py [--offline]

Needs `python3 scripts/vm-shell.py serve` running on the host. Screenshots and report.txt go to
build/install-test/. Coordinates are guest pixels for the 1600x900 test VM.
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "build/install-test")
VM_DIR = os.path.join(ROOT, "build/vm-install-test")
os.environ["QMP_SOCK"] = os.path.join(VM_DIR, "qmp.sock")
import qmp  # noqa: E402
from PIL import Image, ImageStat  # noqa: E402

PASSWORD = "glass123"
NEXT = (1175, 719)
OFFLINE = "--offline" in sys.argv
report = []
shot_no = 0
qemu_pid = None


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    report.append(line)
    with open(os.path.join(OUT, "report.txt"), "w") as f:
        f.write("\n".join(report) + "\n")


def shot(name):
    global shot_no
    shot_no += 1
    path = os.path.join(OUT, f"{shot_no:02d}-{name}.png")
    f = qmp.connect()
    qmp.screendump(f, path + ".ppm")
    img = Image.open(path + ".ppm").convert("RGB")
    img.save(path)
    os.remove(path + ".ppm")
    return img


def brightness(img):
    return sum(ImageStat.Stat(img).mean) / 3


def click(x, y, n=1):
    qmp.pointer(qmp.connect(), x, y, n, "left")


def keys(*combos):
    f = qmp.connect()
    for c in combos:
        qmp.send_key(f, c.split("-"))
        time.sleep(0.15)


def type_text(text):
    f = qmp.connect()
    for ch in text:
        qmp.send_key(f, (["shift"] if ch in qmp.SHIFTED else []) + [qmp.QCODES.get(ch, ch.lower())])
        time.sleep(0.03)


def wait_for_screen(name, timeout, settle=8):
    """Wait until the display is lit and has stopped changing."""
    end = time.time() + timeout
    prev = None
    while time.time() < end:
        img = shot(name)
        if brightness(img) > 120 and prev is not None and \
                abs(brightness(img) - brightness(prev)) < 0.5:
            return img
        prev = img
        time.sleep(settle)
    raise SystemExit(f"FAIL: screen never settled ({name})")


def agent_connected():
    out = subprocess.run(["ss", "-tnpH", "dport = :18765"], capture_output=True, text=True).stdout
    pids = {int(p.split("pid=")[1].split(",")[0]) for p in out.split() if "pid=" in p}
    return pids


def run(cmd, timeout=120):
    """Run a command in the test VM's session. Refuses if any other VM's agent is connected."""
    others = agent_connected() - {qemu_pid}
    if others:
        raise SystemExit(f"FAIL: another VM (pid {others}) is connected to vm-shell; not sending commands")
    req = urllib.request.Request("http://127.0.0.1:18765/run", data=cmd.encode(),
                                 headers={"X-Timeout": str(timeout)})
    try:
        with urllib.request.urlopen(req, timeout=timeout + 5) as r:
            return r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.read().decode(errors="replace")


def start_agent():
    """Open a terminal, start the vm-shell agent detached from it, close the terminal."""
    if agent_connected() - {qemu_pid}:
        raise SystemExit("FAIL: another VM is connected to vm-shell")
    keys("ctrl-alt-t")
    time.sleep(5)
    type_text("setsid bash -c 'curl -s 10.0.2.2:18765/agent | bash' >/dev/null 2>&1 < /dev/null & exit\n")
    for _ in range(20):
        time.sleep(1)
        if qemu_pid in agent_connected():
            return
    raise SystemExit("FAIL: vm-shell agent did not connect")


def finish_page_shown(img):
    # The sidebar highlight (Windows accent blue) sits on the "Finish" entry.
    r, g, b = img.getpixel((330, 558))
    return b > 150 and r < 60


def main():
    global qemu_pid
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    shutil.rmtree(VM_DIR, ignore_errors=True)
    os.makedirs(VM_DIR)
    iso = os.path.join(ROOT, "build/install-test.iso")
    shutil.copy(os.path.join(ROOT, "out/glasspanes-1.0-amd64.iso"), iso)
    log(f"ISO: {time.ctime(os.path.getmtime(iso))}; network: {'off' if OFFLINE else 'on'}")

    args = ["scripts/run-qemu.sh", "--uefi", "--disks", "--headless", "--vm-dir", VM_DIR, "--iso", iso]
    if OFFLINE:
        args.insert(3, "--offline")
    qemu_log = open(os.path.join(VM_DIR, "qemu.log"), "w")
    subprocess.Popen(args, cwd=ROOT, stdout=qemu_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    time.sleep(5)
    qemu_pid = int(subprocess.run(["pgrep", "-f", f"^qemu-system.*{VM_DIR}"], capture_output=True,
                                  text=True).stdout.split()[0])
    log(f"VM started (pid {qemu_pid})")

    # ---- live session and installer ------------------------------------------------------------
    time.sleep(40)
    wait_for_screen("live-desktop", 240)
    log("live desktop is up")
    click(56, 175, 2)
    time.sleep(15)
    shot("welcome")
    click(*NEXT); time.sleep(3); shot("location")
    click(*NEXT); time.sleep(3); shot("keyboard")
    click(*NEXT); time.sleep(5); shot("partitions")
    click(498, 239); time.sleep(3); shot("erase-disk")
    click(*NEXT); time.sleep(3)
    click(591, 217); type_text("Sam Smith")
    click(591, 412); type_text(PASSWORD)
    click(797, 412); type_text(PASSWORD)
    time.sleep(2); shot("users")
    click(*NEXT); time.sleep(3); shot("summary")
    click(1167, 822); time.sleep(3); shot("confirm")
    click(755, 511)
    started = time.time()
    log("installation started")

    dark = 0
    while True:
        time.sleep(30)
        img = shot("installing")
        if brightness(img) < 20:
            dark += 1
            log(f"screen is dark {int(time.time() - started)} s into the install")
        if finish_page_shown(img):
            break
        if time.time() - started > 45 * 60:
            raise SystemExit("FAIL: installer did not reach the Finish page in 45 minutes")
    log(f"installer reached 'All done' after {int(time.time() - started) // 60} min; "
        f"screen went dark {dark} time(s)")

    # ---- first boot ---------------------------------------------------------------------------
    click(1265, 822)  # Done, with "Restart now" ticked
    log("restarting")
    time.sleep(30)
    wait_for_screen("first-boot", 240)
    click(800, 450)
    time.sleep(2)
    shot("sign-in")
    type_text(PASSWORD + "\n")
    time.sleep(20)
    wait_for_screen("installed-desktop", 120)
    log("signed in to the installed system")
    if OFFLINE:
        log("offline: health checks skipped (the command channel needs the network)")
        log("DONE")
        return
    start_agent()
    time.sleep(3)
    shot("installed-desktop-clean")

    checks = {
        "failed services": "systemctl --failed --no-legend --plain; echo end",
        "user": "id -un; getent passwd $(id -un) | cut -d: -f5",
        "computer name": "hostname",
        "disks": "findmnt -no SOURCE,FSTYPE,SIZE /; findmnt -no SOURCE,FSTYPE /boot/efi; cat /proc/swaps",
        "fstab": "grep -v '^#' /etc/fstab",
        "live/installer packages left (want 0)":
            "dpkg -l calamares live-boot live-config 2>/dev/null | grep -c ^ii",
        "language and time": "locale | head -1; timedatectl | grep -E 'zone|synchron'",
        "admin rights": f"echo {PASSWORD} | sudo -S -p '' whoami",
        "boot entries": "efibootmgr | head -4",
        "bootloader": f"ls /boot/efi/EFI; echo {PASSWORD} | sudo -S -p '' grep -c menuentry /boot/grub/grub.cfg",
        "Wine": "wine --version",
        "sign-in screen extras": "dpkg -l qt6-virtualkeyboard-plugin | grep -c ^ii; "
                                 "ls /usr/share/sddm/themes/glasspanes/NetworkFlyout.qml",
        "launch feedback off": "kreadconfig6 --file klaunchrc --group FeedbackStyle --key BusyCursor",
        "boot errors": "journalctl -b -p err --no-pager -q | tail -15; echo end",
        "disk use": "df -h / | tail -1",
    }
    if not OFFLINE:
        checks["internet"] = "nmcli -t -f STATE general; curl -sI https://deb.debian.org | head -1"
        checks["software updates reachable"] = \
            f"echo {PASSWORD} | sudo -S -p '' apt-get update -q 2>&1 | tail -2"
    for name, cmd in checks.items():
        log(f"--- {name}\n{run(cmd).rstrip()}")

    # Windows app support is set up in the background at first sign-in.
    for _ in range(30):
        if "yes" in run("test -d ~/.wine/drive_c/windows && echo yes"):
            break
        time.sleep(10)
    log(f"--- Windows app support (C: drive)\n"
        f"{run('ls ~/.wine/drive_c; wine cmd /c ver 2>/dev/null | tr -d \"\\r\"', 180).rstrip()}")

    # ---- second boot: make sure it comes back up --------------------------------------------
    run("(sleep 2; echo %s | sudo -S -p '' systemctl reboot) >/dev/null 2>&1 &" % PASSWORD, 10)
    log("rebooting a second time")
    time.sleep(40)
    wait_for_screen("second-boot", 240)
    click(800, 450)
    time.sleep(2)
    type_text(PASSWORD + "\n")
    time.sleep(20)
    wait_for_screen("second-boot-desktop", 120)
    log("second boot and sign-in OK")
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            log(str(e.code))
        raise
