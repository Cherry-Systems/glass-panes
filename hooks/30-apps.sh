#!/bin/sh
# Runs inside the chroot. Gives the apps their Windows names (File Explorer, Notepad, Paint...),
# hides the developer tools a Windows user wouldn't expect, wires up the Windows keyboard
# shortcuts, and makes the X11 Plasma session the only one.
set -eu

# --- Windows names -------------------------------------------------------------------------------
# Same desktop-file IDs in /usr/local/share/applications (earlier in XDG_DATA_DIRS) override the
# originals, so taskbar pins and running windows still match up.
LOCAL=/usr/local/share/applications
mkdir -p "$LOCAL"
rename_app() {  # ID "Name" "Generic name" icon
  src="/usr/share/applications/$1"
  [ -f "$src" ] || { echo "  (skipping $1: not installed)"; return 0; }
  sed -e '/^Name\[/d' -e '/^GenericName\[/d' -e '/^X-GNOME-FullName/d' \
      -e "0,/^Name=.*/s//Name=$2/" "$src" > "$LOCAL/$1"
  if grep -q '^GenericName=' "$LOCAL/$1"; then
    sed -i "0,/^GenericName=.*/s//GenericName=$3/" "$LOCAL/$1"
  else
    sed -i "0,/^Name=.*/s//&\nGenericName=$3/" "$LOCAL/$1"
  fi
  [ -n "$4" ] && sed -i "0,/^Icon=.*/s//Icon=$4/" "$LOCAL/$1"
  return 0
}
rename_app org.kde.dolphin.desktop        "File Explorer"      "File Explorer"      system-file-manager
rename_app org.kde.kwrite.desktop         "Notepad"            "Text editor"        accessories-text-editor
rename_app org.kde.konsole.desktop        "Terminal"           "Command prompt"     utilities-terminal
rename_app org.kde.spectacle.desktop      "Snipping Tool"      "Screenshots"        ""
rename_app org.kde.gwenview.desktop       "Photos"             "Photo viewer"       image-viewer
rename_app org.kde.okular.desktop         "PDF Reader"         "Document viewer"    ""
rename_app org.kde.kcalc.desktop          "Calculator"         "Calculator"         accessories-calculator
rename_app org.kde.kolourpaint.desktop    "Paint"              "Paint"              ""
rename_app org.kde.haruna.desktop         "Media Player"       "Video and music"    multimedia-video-player
rename_app org.kde.discover.desktop       "Store"              "Get apps"           ""
rename_app systemsettings.desktop         "Control Panel"      "Advanced settings"  preferences-desktop
rename_app org.kde.kcharselect.desktop    "Character Map"      "Special characters" ""
rename_app org.kde.partitionmanager.desktop "Disk Management"  "Disks and drives"   ""
rename_app org.kde.kinfocenter.desktop    "System Information" "System information" ""
rename_app org.kde.ark.desktop            "Compressed Folders" "Zip files"          ""
rename_app firefox-esr.desktop            "Firefox"            "Web browser"        ""
# Win+E opens File Explorer.
echo "X-KDE-Shortcuts=Meta+E" >> "$LOCAL/org.kde.dolphin.desktop"

hide_app() {
  for id in "$@"; do
    src="/usr/share/applications/$id"
    [ -f "$src" ] || continue
    [ -f "$LOCAL/$id" ] || cp "$src" "$LOCAL/$id"
    sed -i '/^NoDisplay=/d' "$LOCAL/$id"
    sed -i "0,/^\[Desktop Entry\]/s//&\nNoDisplay=true/" "$LOCAL/$id"
  done
}
hide_app org.kde.kmenuedit.desktop org.kde.plasma.emojier.desktop xterm.desktop debian-xterm.desktop \
  debian-uxterm.desktop wine.desktop org.kde.kwalletmanager.desktop org.kde.drkonqi.coredump.gui.desktop \
  org.kde.plasma-systemmonitor.desktop kvantummanager.desktop org.kde.kdebugsettings.desktop \
  org.kde.plasma.themeexplorer.desktop winetricks.desktop display-im6.q16.desktop \
  org.kde.knewstuff-dialog6.desktop org.kde.kded6.desktop org.kde.plasma-welcome.desktop \
  vim.desktop htop.desktop nm-connection-editor.desktop org.kde.ksystemlog.desktop \
  org.freedesktop.IBus.Setup.desktop kdesystemsettings.desktop

# --- window titles ---------------------------------------------------------------------------------
# KDE apps put their name in every window title ("Home — Dolphin"). A small English (Australia)
# translation catalog renames them there too, built from the stock British English catalog.
apt-get install -y --no-install-recommends gettext >/dev/null
retitle() {  # domain old new
  gb="/usr/share/locale/en_GB/LC_MESSAGES/$1.mo"
  [ -f "$gb" ] || return 0
  msgunfmt "$gb" -o /tmp/cat.po 2>/dev/null || return 0
  OLD="$2" NEW="$3" python3 - <<'EOF'
import os, re
old, new = os.environ["OLD"], os.environ["NEW"]
text = open("/tmp/cat.po", encoding="utf-8").read()
def fix(m):
    msgid, rest = m.group(1), m.group(2)
    if msgid == old:
        return f'msgid "{msgid}"\nmsgstr "{new}"'
    return m.group(0)
text = re.sub(r'msgid "(.*)"\nmsgstr "(.*)"', fix, text)
open("/tmp/cat.po", "w", encoding="utf-8").write(text)
EOF
  for lang in en_AU en_NZ; do
    mkdir -p "/usr/share/locale/$lang/LC_MESSAGES"
    msgfmt /tmp/cat.po -o "/usr/share/locale/$lang/LC_MESSAGES/$1.mo" 2>/dev/null || true
  done
  rm -f /tmp/cat.po
}
retitle dolphin "Dolphin" "File Explorer"
retitle kwrite "KWrite" "Notepad"
retitle konsole "Konsole" "Terminal"
retitle gwenview "Gwenview" "Photos"
retitle okular "Okular" "PDF Reader"
retitle kcalc "KCalc" "Calculator"
retitle kolourpaint "KolourPaint" "Paint"
retitle spectacle "Spectacle" "Snipping Tool"
retitle haruna "Haruna" "Media Player"
retitle plasma-discover "Discover" "Store"
retitle systemsettings "System Settings" "Control Panel"
retitle kcharselect "KCharSelect" "Character Map"
retitle partitionmanager "KDE Partition Manager" "Disk Management"
retitle ark "Ark" "Compressed Folders"
apt-get purge -y gettext >/dev/null
apt-get autoremove -y --purge >/dev/null

# --- keyboard shortcuts ------------------------------------------------------------------------------
# kglobalaccel registers X-KDE-Shortcuts from desktop files in this folder (Win+R, Win+X,
# Ctrl+Alt+Del, Ctrl+Shift+Esc, Win+I, Win+S, Win+E, Ctrl+Esc).
mkdir -p /usr/share/kglobalaccel
for f in glass-start glass-search glass-settings glass-taskmgr glass-run glass-winx glass-security; do
  ln -sf "/usr/share/applications/$f.desktop" "/usr/share/kglobalaccel/$f.desktop"
done
ln -sf "$LOCAL/org.kde.dolphin.desktop" /usr/share/kglobalaccel/org.kde.dolphin.desktop

# --- one session: Plasma on X11, called Glass Panes ----------------------------------------------------
# live-config's autologin always asks for "plasma.desktop", which is normally the Wayland session.
if [ -f /usr/share/xsessions/plasmax11.desktop ]; then
  dpkg-divert --local --rename --divert /usr/share/wayland-sessions/plasma.desktop.disabled \
    --add /usr/share/wayland-sessions/plasma.desktop
  dpkg-divert --local --rename --divert /usr/share/xsessions/plasmax11.desktop.disabled \
    --add /usr/share/xsessions/plasmax11.desktop
  sed -e '/^Name\[/d' -e '/^Comment\[/d' -e "s/^Name=.*/Name=$OS_NAME/" \
    /usr/share/xsessions/plasmax11.desktop.disabled > /usr/share/xsessions/plasma.desktop
fi
update-alternatives --set x-session-manager /usr/bin/startplasma-x11 2>/dev/null || true

# Start menu folders for Windows programs installed through Wine show up in Start.
mkdir -p /etc/skel/.local/share/applications

update-desktop-database -q /usr/share/applications "$LOCAL" 2>/dev/null || true
