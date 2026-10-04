#!/usr/bin/env python3
"""Make Plasma's right-click menus behave like Windows: patch-qml.py PART STOCK OUT

STOCK (one of Plasma's QML files) is copied to OUT with the changes listed for PART:
  taskmanager-menu  right-clicking Start opens the Win+X menu, "Task Manager" becomes "taskbar",
                    "Close" says what it closes, and the KDE widget and panel settings are left out
  folderview        the desktop and the Recycle Bin icon open glass-shell's Windows menus
  folderitem        desktop icons say where a link points, so the Recycle Bin can be recognised
  trayitem          the network, volume and battery icons open glass-shell's Quick Settings (and its
                    right-click menus) instead of their own KDE pop-ups
  panel             right-clicking an empty part of the taskbar opens glass-shell's taskbar menu
Every change must apply, or the build stops."""
import sys


def shell_call(member, indent):
    pad = " " * indent
    return (f'{pad}DBus.SessionBus.asyncCall({{service: "org.glasspanes.Shell", path: "/Shell",\n'
            f'{pad}                           iface: "org.glasspanes.Shell", member: "{member}"}});\n')


TASKMANAGER_SHOW = ('''    function show(): void {
        if (/(^|[:\\/])glass-start\\.desktop$/.test(get(atm.LauncherUrlWithoutIcon).toString())) {
''' + shell_call("PowerUserMenu", 12) + '''            menu.destroy();
            return;
        }
        Plasmoid.contextualActionsAboutToShow();''')

FOLDER_EMPTY_STOCK = '''                    // If it's the desktop, fall through to the desktop context menu plugin
                    if (!dir.usedByContainment) {
                        dir.openContextMenu(main, mouse.modifiers);
                        mouse.accepted = true;
                    }
'''
FOLDER_EMPTY = ('''                    if (dir.usedByContainment) {
''' + shell_call("DesktopMenu", 24) + '''                    } else {
                        dir.openContextMenu(main, mouse.modifiers);
                    }
                    mouse.accepted = true;
''')

FOLDER_ITEM_STOCK = '''                        clearPressState();

                        dir.openContextMenu(hoveredItem, mouse.modifiers);
                        mouse.accepted = true;
'''
FOLDER_ITEM = ('''                        clearPressState();

                        if (dir.usedByContainment && hoveredItem.linkTarget === "trash:/" && !gridView.ctrlPressed) {
''' + shell_call("RecycleBinMenu", 28) + '''                        } else {
                            dir.openContextMenu(hoveredItem, mouse.modifiers);
                        }
                        mouse.accepted = true;
''')

PANEL_DROP_STOCK = '''    DragDrop.DropArea {
        id: dropArea
'''
PANEL_DROP = ('''    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.RightButton
        enabled: !Plasmoid.corona.editMode
        onClicked: mouse => {
''' + shell_call("TaskbarMenu", 12) + '''        }
    }

''' + PANEL_DROP_STOCK)

# Sits above the applet's own MouseArea; wheel and middle-click still reach the applet.
TRAY_END_STOCK = '''        restoreMode: Binding.RestoreBinding
    }
}
'''
TRAY_END = ('''        restoreMode: Binding.RestoreBinding
    }

    MouseArea {
        anchors.fill: parent
        z: 1000
        enabled: ["org.kde.plasma.networkmanagement", "org.kde.plasma.volume",
                  "org.kde.plasma.battery"].includes(plasmoidContainer.itemId)
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: mouse => {
            if (mouse.button === Qt.LeftButton) {
''' + shell_call("QuickSettings", 16) + '''            } else {
                DBus.SessionBus.asyncCall({service: "org.glasspanes.Shell", path: "/Shell", iface: "org.glasspanes.Shell",
                                           member: "TrayMenu", arguments: [plasmoidContainer.itemId]});
            }
        }
    }
}
''')

DBUS = "import org.kde.plasma.workspace.dbus as DBus\n"

PATCHES = {
    "taskmanager-menu": [
        ("\nimport org.kde.taskmanager as TaskManager\n", "\n" + DBUS + "import org.kde.taskmanager as TaskManager\n", 1),
        ("    function show(): void {\n        Plasmoid.contextualActionsAboutToShow();", TASKMANAGER_SHOW, 1),
        ('text: i18n("&Pin to Task Manager")', 'text: i18n("Pin to taskbar")', 2),
        ('text: i18n("Unpin from Task Manager")', 'text: i18n("Unpin from taskbar")', 1),
        ("        visible: configureAction && configureAction.visible\n", "        visible: false\n", 1),
        ("        visible: editModeAction && editModeAction.visible\n", "        visible: false\n", 1),
        ('text: get(atm.IsGroupParent) ? i18nc("@item:inmenu", "&Close All") : i18n("&Close")',
         'text: get(atm.IsGroupParent) ? i18n("Close all windows") : i18n("Close window")', 1),
    ],
    "folderview": [
        ("\nimport org.kde.private.desktopcontainment.folder as Folder\n",
         "\n" + DBUS + "import org.kde.private.desktopcontainment.folder as Folder\n", 1),
        ("                return root.isPopup ? (Qt.LeftButton | Qt.MiddleButton | Qt.BackButton) : Qt.LeftButton;\n",
         "                return root.isPopup ? (Qt.LeftButton | Qt.MiddleButton | Qt.BackButton)\n"
         "                    : (Qt.LeftButton | Qt.RightButton);\n", 1),
        (FOLDER_EMPTY_STOCK, FOLDER_EMPTY, 1),
        (FOLDER_ITEM_STOCK, FOLDER_ITEM, 1),
    ],
    "folderitem": [
        ("    property bool selected:      model.blank ? false : model.selected\n",
         "    property bool selected:      model.blank ? false : model.selected\n"
         '    property string linkTarget:  model.blank ? "" : String(model.linkDestinationUrl)\n', 1),
    ],
    "trayitem": [
        ("\nimport org.kde.plasma.plasmoid\n", "\nimport org.kde.plasma.plasmoid\n" + DBUS, 1),
        (TRAY_END_STOCK, TRAY_END, 1),
    ],
    "panel": [
        ("\nimport org.kde.draganddrop 2.0 as DragDrop\n", "\nimport org.kde.draganddrop 2.0 as DragDrop\n" + DBUS, 1),
        (PANEL_DROP_STOCK, PANEL_DROP, 1),
    ],
}


def main():
    part, stock, out = sys.argv[1:4]
    qml = open(stock, encoding="utf-8").read()
    for old, new, count in PATCHES[part]:
        found = qml.count(old)
        if found != count:
            sys.exit(f"{stock}: expected {count} of {old.strip()[:60]!r}, found {found}")
        qml = qml.replace(old, new)
    with open(out, "w", encoding="utf-8") as f:
        f.write(qml)


if __name__ == "__main__":
    main()
