"""Settings pages that Start's search can find (kept free of Qt imports so it loads instantly)."""

# (title, page, icon, keywords)
ENTRIES = [
    ("Display", "display", "desktop", "screen resolution scale monitor brightness night light orientation"),
    ("Sound", "sound", "speaker_2", "volume audio speakers headphones microphone output input"),
    ("Notifications", "notifications", "alert", "do not disturb focus alerts"),
    ("Power & battery", "power", "battery_10", "sleep battery saver power mode energy screen off"),
    ("Storage", "storage", "hard_drive", "disk space cleanup free up"),
    ("Multitasking", "multitasking", "window_multiple", "snap windows alt tab virtual desktops"),
    ("About", "about", "info", "device specifications pc name rename computer version system info"),
    ("Bluetooth & devices", "bluetooth", "bluetooth", "pair add device mouse keyboard printers"),
    ("Printers & scanners", "printers", "print", "printer scanner add printer"),
    ("Mouse", "mouse", "cursor", "pointer speed scroll buttons touchpad"),
    ("Wi-Fi", "network", "wifi_1", "wireless network internet ethernet airplane mode hotspot vpn proxy"),
    ("Network & internet", "network", "globe", "network internet ethernet vpn proxy"),
    ("Background", "background", "image", "wallpaper desktop picture personalize personalise"),
    ("Colours", "colors", "color", "dark mode light mode accent colour color theme transparency"),
    ("Dark mode", "colors", "dark_theme", "dark theme night colours"),
    ("Themes", "colors", "paint_brush", "theme cursor icons"),
    ("Lock screen", "lockscreen", "lock_closed", "lock screen sign in picture"),
    ("Taskbar", "taskbar", "window_apps", "taskbar alignment left center pinned"),
    ("Start", "start", "grid", "start menu pinned recommended"),
    ("Installed apps", "installedapps", "apps_list", "uninstall programs remove software add remove programs"),
    ("Default apps", "defaultapps", "apps", "default browser open with file type"),
    ("Startup apps", "startup", "rocket", "startup autostart sign in apps"),
    ("Your info", "yourinfo", "person_circle", "account picture name user profile"),
    ("Sign-in options", "signin", "person", "password change password pin"),
    ("Other users", "otherusers", "people", "add user family"),
    ("Date & time", "time_date", "clock", "time zone date clock sync 24 hour"),
    ("Language & region", "language", "local_language", "language region keyboard layout input"),
    ("Accessibility", "accessibility", "accessibility", "text size magnifier contrast narrator mouse pointer"),
    ("Privacy & security", "privacy", "shield", "privacy location camera microphone firewall"),
    ("Glass Update", "update", "arrow_sync_circle", "windows update updates check for updates upgrade"),
    ("Windows apps", "windowsapps", "window_apps", "wine exe msi windows programs compatibility"),
]


def search(query, limit=6):
    q = query.lower().strip()
    if not q:
        return []
    out = []
    for title, page, icon, kw in ENTRIES:
        t = title.lower()
        if t.startswith(q):
            score = 90
        elif q in t:
            score = 70
        elif any(w.startswith(q) for w in kw.split()):
            score = 50
        elif q in kw:
            score = 30
        else:
            continue
        out.append((score, title, page, icon))
    out.sort(key=lambda x: -x[0])
    return [(t, p, i) for _s, t, p, i in out[:limit]]
