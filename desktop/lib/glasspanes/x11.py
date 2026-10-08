"""Small X11 helpers: ask KWin to blur behind a translucent window (Windows 11 acrylic), and to
move or activate another app's window."""
import os


def _display():
    if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11" or not os.environ.get("DISPLAY"):
        return None
    try:
        from Xlib import display
        return display.Display()
    except Exception:  # noqa: BLE001 — no X server or no python3-xlib
        return None


def enable_blur(win_id, enable=True):
    d = _display()
    if d is None:
        return
    try:
        from Xlib import X
        w = d.create_resource_object("window", int(win_id))
        atom = d.intern_atom("_KDE_NET_WM_BLUR_BEHIND_REGION")
        if enable:
            w.change_property(atom, d.intern_atom("CARDINAL"), 32, [], X.PropModeReplace)
        else:
            w.delete_property(atom)
        d.flush()
    except Exception:  # noqa: BLE001 — blur is cosmetic, never fatal
        pass
    finally:
        d.close()


def active_window():
    """The X11 id of the active window, or 0."""
    d = _display()
    if d is None:
        return 0
    try:
        prop = d.screen().root.get_full_property(d.intern_atom("_NET_ACTIVE_WINDOW"), 0)
        return int(prop.value[0]) if prop and len(prop.value) else 0
    except Exception:  # noqa: BLE001
        return 0
    finally:
        d.close()


def _send(d, win, name, data):
    from Xlib import X
    from Xlib.protocol import event
    ev = event.ClientMessage(window=win, client_type=d.intern_atom(name), data=(32, (data + [0] * 5)[:5]))
    d.screen().root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)


def unmaximize(win_id):
    d = _display()
    if d is None:
        return
    try:
        win = d.create_resource_object("window", int(win_id))
        _send(d, win, "_NET_WM_STATE", [0, d.intern_atom("_NET_WM_STATE_MAXIMIZED_VERT"),
                                        d.intern_atom("_NET_WM_STATE_MAXIMIZED_HORZ"), 2])
        d.flush()
    except Exception:  # noqa: BLE001
        pass
    finally:
        d.close()


def place_window(win_id, x, y, w, h):
    """Moves a window so its frame (title bar and borders included) covers x, y, w, h, and
    activates it. Call unmaximize() a moment before, or KWin keeps it maximised."""
    d = _display()
    if d is None:
        return
    try:
        from Xlib import X
        win = d.create_resource_object("window", int(win_id))
        prop = win.get_full_property(d.intern_atom("_NET_FRAME_EXTENTS"), 0)
        left, right, top, bottom = (list(prop.value) + [0] * 4)[:4] if prop else (0, 0, 0, 0)
        # NorthWest gravity puts the frame's corner at x, y; the size is the app's own area.
        flags = 1 | (0xF << 8) | (2 << 12)
        _send(d, win, "_NET_MOVERESIZE_WINDOW",
              [flags, x, y, max(1, w - left - right), max(1, h - top - bottom)])
        _send(d, win, "_NET_ACTIVE_WINDOW", [2, X.CurrentTime, 0])
        d.flush()
    except Exception:  # noqa: BLE001
        pass
    finally:
        d.close()
