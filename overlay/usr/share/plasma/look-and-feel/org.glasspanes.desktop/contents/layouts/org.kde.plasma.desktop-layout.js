// Glass Panes default desktop: a Windows 11 taskbar. Start, Search and Task View are the first
// pinned launchers so they sit centred with the apps; the tray and clock are on the right.
var WALLPAPER = "file:///usr/share/backgrounds/glasspanes/glass-bloom-light.png";

var panel = new Panel;
panel.location = "bottom";
panel.height = 48;
panel.hiding = "none";
panel.lengthMode = "fill";
try { panel.floating = false; } catch (e) {}

// Two flexible spacers centre the task strip on the screen.
panel.addWidget("org.kde.plasma.panelspacer");

var tasks = panel.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    "applications:glass-start.desktop",
    "applications:glass-search.desktop",
    "applications:glass-taskview.desktop",
    "applications:org.kde.dolphin.desktop",
    "applications:firefox-esr.desktop",
    "applications:org.kde.discover.desktop",
    "applications:glass-settings.desktop"
]);
tasks.writeConfig("fill", false);
tasks.writeConfig("iconSpacing", 1);
tasks.writeConfig("showOnlyCurrentDesktop", false);
tasks.writeConfig("showOnlyCurrentActivity", true);
tasks.writeConfig("indicateAudioStreams", true);
tasks.writeConfig("highlightWindows", false);

panel.addWidget("org.kde.plasma.panelspacer");

var tray = panel.addWidget("org.kde.plasma.systemtray");
try {
    var trayBox = desktopById(tray.readConfig("SystrayContainmentId"));
    if (trayBox) {
        trayBox.currentConfigGroup = ["General"];
        trayBox.writeConfig("shownItems", [
            "org.kde.plasma.networkmanagement",
            "org.kde.plasma.volume",
            "org.kde.plasma.battery"
        ]);
        trayBox.writeConfig("hiddenItems", [
            "org.kde.plasma.clipboard",
            "org.kde.plasma.keyboardindicator",
            "org.kde.plasma.keyboardlayout",
            "org.kde.plasma.manage-inputmethod",
            "org.kde.plasma.devicenotifier",
            "org.kde.plasma.printmanager",
            "org.kde.plasma.bluetooth",
            "org.kde.plasma.brightness",
            "org.kde.plasma.mediacontroller",
            "org.kde.kscreen",
            "org.kde.plasma.cameraindicator",
            "org.kde.plasma.weather",
            "org.kde.kdeconnect",
            "Discover Notifier_org.kde.DiscoverNotifier"
        ]);
    }
} catch (e) {}

var clock = panel.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", true);
clock.writeConfig("dateDisplayFormat", "BelowTime");
clock.writeConfig("dateFormat", "custom");
clock.writeConfig("customDateFormat", "d/MM/yyyy");
clock.writeConfig("autoFontAndSize", false);
clock.writeConfig("fontSize", 9);

var all = desktops();
for (var i = 0; i < all.length; i++) {
    var d = all[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", WALLPAPER);
    d.writeConfig("FillMode", 2);
    d.currentConfigGroup = ["General"];
    d.writeConfig("arrangement", 1);
    d.writeConfig("alignment", 0);
}
