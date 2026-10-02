"""Small X11 helpers: ask KWin to blur behind a translucent window (Windows 11 acrylic)."""
import os


def enable_blur(win_id, enable=True):
    if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11" or not os.environ.get("DISPLAY"):
        return
    try:
        from Xlib import X, display
    except ImportError:
        return
    try:
        d = display.Display()
        w = d.create_resource_object("window", int(win_id))
        atom = d.intern_atom("_KDE_NET_WM_BLUR_BEHIND_REGION")
        if enable:
            w.change_property(atom, d.intern_atom("CARDINAL"), 32, [], X.PropModeReplace)
        else:
            w.delete_property(atom)
        d.flush()
        d.close()
    except Exception:  # noqa: BLE001 — blur is cosmetic, never fatal
        pass
