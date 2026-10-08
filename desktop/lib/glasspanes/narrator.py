"""Narrator (Win+Ctrl+Enter): turns the Orca screen reader on and off."""
import shutil
import subprocess

QUIET = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def running():
    return subprocess.run(["pgrep", "-x", "orca"], **QUIET).returncode == 0


def notify(title, text):
    subprocess.Popen(["notify-send", "--app-name=Narrator", "--icon=preferences-desktop-accessibility",
                      title, text], start_new_session=True, **QUIET)


def toggle():
    if running():
        # Orca has no quit option; it shuts down cleanly on SIGTERM.
        subprocess.run(["pkill", "-TERM", "-x", "orca"], **QUIET)
        notify("Narrator is off", "Press Win+Ctrl+Enter to turn it back on.")
    elif shutil.which("orca"):
        subprocess.Popen(["orca", "--replace"], start_new_session=True, stdin=subprocess.DEVNULL, **QUIET)
        notify("Narrator is on", "Narrator reads out what's on the screen. Press Win+Ctrl+Enter to turn it off.")
    else:
        notify("Narrator isn't installed", "The Orca screen reader is missing from this PC.")
