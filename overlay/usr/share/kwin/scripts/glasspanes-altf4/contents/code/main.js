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
