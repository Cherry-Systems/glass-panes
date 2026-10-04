#!/usr/bin/env python3
"""Make the taskbar's right-click menu for apps read like Windows: patch-context-menu.py STOCK OUT

Plasma's ContextMenu.qml (STOCK) is copied to OUT with these changes: right-clicking Start opens
the Win+X menu, "Task Manager" becomes "taskbar", "Close" says what it closes, and the KDE widget
and panel settings are left out. Every change must apply, or the build stops."""
import sys

START_MENU = '''    function show(): void {
        if (/(^|[:\\/])glass-start\\.desktop$/.test(get(atm.LauncherUrlWithoutIcon).toString())) {
            DBus.SessionBus.asyncCall({service: "org.glasspanes.Shell", path: "/Shell",
                                       iface: "org.glasspanes.Shell", member: "PowerUserMenu"});
            menu.destroy();
            return;
        }
        Plasmoid.contextualActionsAboutToShow();'''

CHANGES = [
    ("\nimport org.kde.taskmanager as TaskManager\n",
     "\nimport org.kde.plasma.workspace.dbus as DBus\nimport org.kde.taskmanager as TaskManager\n", 1),
    ("    function show(): void {\n        Plasmoid.contextualActionsAboutToShow();", START_MENU, 1),
    ('text: i18n("&Pin to Task Manager")', 'text: i18n("Pin to taskbar")', 2),
    ('text: i18n("Unpin from Task Manager")', 'text: i18n("Unpin from taskbar")', 1),
    ("        visible: configureAction && configureAction.visible\n", "        visible: false\n", 1),
    ("        visible: editModeAction && editModeAction.visible\n", "        visible: false\n", 1),
    ('text: get(atm.IsGroupParent) ? i18nc("@item:inmenu", "&Close All") : i18n("&Close")',
     'text: get(atm.IsGroupParent) ? i18n("Close all windows") : i18n("Close window")', 1),
]


def main():
    stock, out = sys.argv[1], sys.argv[2]
    qml = open(stock, encoding="utf-8").read()
    for old, new, count in CHANGES:
        found = qml.count(old)
        if found != count:
            sys.exit(f"{stock}: expected {count} of {old.strip()[:60]!r}, found {found}")
        qml = qml.replace(old, new)
    with open(out, "w", encoding="utf-8") as f:
        f.write(qml)


if __name__ == "__main__":
    main()
