"""Narrator (Win+Ctrl+Enter): turns the Orca screen reader on and off."""
import shutil
import subprocess

import psutil

QUIET = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def running():
    """Orca is running; one that has quit but not been reaped yet (a zombie) doesn't count."""
    for p in psutil.process_iter(["name", "status"]):
        if p.info["name"] == "orca" and p.info["status"] != psutil.STATUS_ZOMBIE:
            return True
    return False


def notify(title, text):
    subprocess.Popen(["notify-send", "--app-name=Narrator", "--icon=preferences-desktop-accessibility",
                      title, text], start_new_session=True, **QUIET)


def toggle():
    if running():
        # Orca has no quit option; it shuts down cleanly on SIGTERM.
        subprocess.run(["pkill", "-TERM", "-x", "orca"], **QUIET)
        notify("Narrator is off", "Press Win+Ctrl+Enter to turn it back on.")
    elif shutil.which("orca"):
        # setsid --fork, so Orca isn't the Glass shell's child and is cleaned up when it quits.
        subprocess.run(["setsid", "--fork", "orca", "--replace"], stdin=subprocess.DEVNULL, **QUIET)
        notify("Narrator is on", "Narrator reads out what's on the screen. Press Win+Ctrl+Enter to turn it off.")
    else:
        notify("Narrator isn't installed", "The Orca screen reader is missing from this PC.")
