// Alt+F4 closes the active window, as usual. With nothing but the desktop or the taskbar active,
// Windows asks what the computer should do; the Glass shell shows that box.
registerShortcut("Glass Panes Close or Shut Down", "Close Window or Shut Down", "Alt+F4", function () {
    var w = workspace.activeWindow;
    if (w && !w.desktopWindow && !w.dock) {
        w.closeWindow();
        return;
    }
    callDBus("org.glasspanes.Shell", "/Shell", "org.glasspanes.Shell", "ShutDown");
});

function normalWindow() {
    var w = workspace.activeWindow;
    return w && w.normalWindow && !w.fullScreen ? w : null;
}

// maximizeMode: 0 restored, 1 vertically, 2 horizontally, 3 fully. A restored window can still be
// screen-sized, so the geometry says nothing.
function isMaximized(w) {
    return w.maximizeMode !== 0;
}

// KWin's own maximise toggles; on Windows Win+Up only ever maximises.
registerShortcut("Glass Panes Maximize", "Maximize Window", "Meta+Up", function () {
    var w = normalWindow();
    if (w && w.maximizable && w.maximizeMode !== 3)
        w.setMaximize(true, true);
});

// Win+Down restores a maximised window and minimises a restored one.
registerShortcut("Glass Panes Restore or Minimize", "Restore or Minimize Window", "Meta+Down", function () {
    var w = normalWindow();
    if (!w)
        return;
    if (isMaximized(w))
        w.setMaximize(false, false);
    else if (w.minimizable)
        w.minimized = true;
});

function minimizeOthers(keep) {
    var done = [];
    workspace.windowList().forEach(function (w) {
        if (w !== keep && w.normalWindow && w.minimizable && !w.minimized && !w.skipTaskbar
                && (w.onAllDesktops || w.desktops.indexOf(workspace.currentDesktop) >= 0)) {
            w.minimized = true;
            done.push(w);
        }
    });
    return done;
}

// windowList() is in stacking order, so the last window restored was the one in front.
function restore(list, activate) {
    var open = workspace.windowList();
    var last = null;
    list.forEach(function (w) {
        if (open.indexOf(w) >= 0) {
            w.minimized = false;
            last = w;
        }
    });
    if (activate && last)
        workspace.activeWindow = last;
    return [];
}

var minimizedByWinM = [];
var minimizedByWinHome = [];

registerShortcut("Glass Panes Minimize All", "Minimize All Windows", "Meta+M", function () {
    minimizedByWinM = minimizeOthers(null);
});

registerShortcut("Glass Panes Restore Minimized", "Restore Windows Minimized with Win+M", "Meta+Shift+M", function () {
    minimizedByWinM = restore(minimizedByWinM, true);
});

// Pressed again, Win+Home brings the other windows back.
registerShortcut("Glass Panes Minimize Others", "Minimize All but the Active Window", "Meta+Home", function () {
    var open = workspace.windowList();
    minimizedByWinHome = minimizedByWinHome.filter(function (w) {
        return open.indexOf(w) >= 0 && w.minimized;
    });
    if (minimizedByWinHome.length)
        minimizedByWinHome = restore(minimizedByWinHome, false);
    else if (normalWindow())
        minimizedByWinHome = minimizeOthers(workspace.activeWindow);
});

registerShortcut("Glass Panes New Desktop", "Add a Virtual Desktop and Switch to It", "Meta+Ctrl+D", function () {
    var n = workspace.desktops.length;
    workspace.createDesktop(n, "Desktop " + (n + 1));
    workspace.currentDesktop = workspace.desktops[n];
});

registerShortcut("Glass Panes Close Desktop", "Close the Current Virtual Desktop", "Meta+Ctrl+F4", function () {
    if (workspace.desktops.length > 1)
        workspace.removeDesktop(workspace.currentDesktop);
});
