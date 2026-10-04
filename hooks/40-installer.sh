#!/bin/sh
# Runs inside the chroot. Rebrands Debian's Calamares installer setup and adapts it to this ISO.
set -eu
[ -d /etc/calamares ] || exit 0

ART="/usr/share/$OS_ID/artwork"
BRANDING="/etc/calamares/branding/$OS_ID"
DESC="$BRANDING/branding.desc"

cp -a /etc/calamares/branding/debian "$BRANDING"
set_key() { sed -i "s|^\( *$1: *\).*|\1$2|" "$DESC"; }
set_key componentName "$OS_ID"
set_key productName "$OS_NAME"
set_key shortProductName "$OS_NAME"
set_key version "$OS_VERSION"
set_key shortVersion "$OS_VERSION"
set_key versionedName "\"$OS_NAME $OS_VERSION\""
set_key shortVersionedName "\"$OS_NAME $OS_VERSION\""
set_key bootloaderEntryName "\"$OS_NAME\""
set_key welcomeStyleCalamares false
set_key SidebarBackground '"#f3f3f3"'
set_key SidebarText '"#1a1a1a"'
set_key SidebarTextCurrent '"#ffffff"'
set_key SidebarBackgroundCurrent '"#0067c0"'
sed -i 's|debian-logo.png|logo.png|' "$DESC"
rm -f "$BRANDING/debian-logo.png"
cp "$ART/logo.png" "$BRANDING/logo.png"
cp "$ART/welcome.png" "$BRANDING/welcome.png"
for i in 1 2 3; do cp "$ART/slide$i.png" "$BRANDING/slide$i.png"; done
cp "$ART/logo.png" /usr/share/pixmaps/install-debian.png

cat > "$BRANDING/show.qml" <<'EOF'
import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    Timer {
        interval: 9000
        repeat: true
        running: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide { Image { source: "welcome.png"; anchors.fill: parent; fillMode: Image.PreserveAspectFit } }
    Slide { Image { source: "slide1.png"; anchors.fill: parent; fillMode: Image.PreserveAspectFit } }
    Slide { Image { source: "slide2.png"; anchors.fill: parent; fillMode: Image.PreserveAspectFit } }
    Slide { Image { source: "slide3.png"; anchors.fill: parent; fillMode: Image.PreserveAspectFit } }
}
EOF

# Calamares' own UI languages have no Australian English, so the welcome page would say "American
# English" while installing the live language (shown on the Location page); hide that list.
cat > "$BRANDING/stylesheet.qss" <<'EOF'
#languageWidget, #languageIcon {
    min-width: 0px; max-width: 0px; min-height: 0px; max-height: 0px;
    margin: 0px; padding: 0px; border: none; background: transparent;
}
EOF

# Sizes in MB (counted in 1024s, as Windows does) instead of MiB.
mkdir -p /usr/share/calamares/lang
python3 /usr/share/glasspanes/installer/ts2qm.py /usr/share/glasspanes/installer/calamares_en.ts \
  /usr/share/calamares/lang/calamares_en.qm
rm -r /usr/share/glasspanes/installer

sed -i -e "s|^branding: .*|branding: $OS_ID|" -e "s|^prompt-install: .*|prompt-install: true|" \
  /etc/calamares/settings.conf
sed -i 's|^\(show[A-Za-z]*Url: *\)true|\1false|' /etc/calamares/modules/welcome.conf

# Debian's signed GRUB (used with Secure Boot) only finds its config under EFI/debian.
echo 'efiBootloaderId: "debian"' >> /etc/calamares/modules/bootloader.conf

sed -i "s|^\( *\)- 'calamares-settings-debian'|&\n\1- 'calamares'|" /etc/calamares/modules/packages.conf
# Offline, apt only knows the packages on the ISO and stops at any other name, so only list the
# live packages that are installed.
for pkg in $(sed -n "s|^ *- '\(.*\)'\$|\1|p" /etc/calamares/modules/packages.conf); do
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed" ||
    sed -i "/^ *- '$pkg'\$/d" /etc/calamares/modules/packages.conf
done

sed -i "s|^RELEASE=.*|RELEASE=\"$DEBIAN_SUITE\"|" /usr/share/calamares/helpers/calamares-sources-media
cat > /usr/share/calamares/helpers/calamares-sources-final <<'EOF'
#!/bin/sh
# The installed system keeps /etc/apt/sources.list.d/debian.sources from the live image.
CHROOT=$(mount | grep proc | grep calamares | awk '{print $3}' | sed -e "s#/proc##g")
rm -f "$CHROOT/etc/apt/sources.list"
exit 0
EOF

sed -i "s|Install Debian|Install $OS_NAME|; s|Installer for Debian Live|Installer for $OS_NAME|" \
  /usr/share/applications/calamares-install-debian.desktop /usr/bin/add-calamares-desktop-icon
sed -i "s|^Icon=.*|Icon=$OS_ID-logo|" /usr/share/applications/calamares-install-debian.desktop
# pkexec drops LANG, so the installer would start in American English instead of the live language.
sed -i 's|^pkexec calamares$|if sudo -n true 2>/dev/null; then sudo -n env LANG="$LANG" LANGUAGE="$LANGUAGE" DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" QT_AUTO_SCREEN_SCALE_FACTOR=1 calamares; else pkexec calamares; fi|' \
  /usr/bin/calamares-install-debian
grep -q '^if sudo -n true' /usr/bin/calamares-install-debian
# Like a Windows local account, any password is accepted (weak ones with a warning).
sed -i 's|^\( *\)- minclass=0$|&\n\1- dictcheck=0|' /etc/calamares/modules/users.conf
grep -q 'dictcheck=0' /etc/calamares/modules/users.conf
printf 'allowWeakPasswords: true\nallowWeakPasswordsDefault: true\n' >> /etc/calamares/modules/users.conf
# Suggest a PC name like "sam-PC" rather than one built from the hardware model ("sam-standardpc").
if grep -q '^hostname:' /etc/calamares/modules/users.conf; then
  echo "users.conf already has a hostname section" >&2
  exit 1
fi
printf 'hostname:\n  location: EtcFile\n  writeHostsFile: true\n  template: "${first}-PC"\n' \
  >> /etc/calamares/modules/users.conf

# "Erase disk" names the system partition "Local Disk" (filesystem label and GPT name), which is
# what File Explorer shows for it, instead of "root".
# Debian ships no partition.conf (Calamares' built-in defaults apply), so any other key stays default.
if [ -f /etc/calamares/modules/partition.conf ]; then
  echo "partition.conf exists now; merge partitionLayout into it" >&2
  exit 1
fi
cat > /etc/calamares/modules/partition.conf <<'EOF'
---
partitionLayout:
  - name: "Local Disk"
    filesystem: "unknown"
    mountPoint: "/"
    size: 100%
EOF

cat > /etc/calamares/modules/locale.conf <<EOF
---
# The live system's timezone (from config/os.conf), since offline installs can't look it up.
useSystemTimezone: true
region: "${TIMEZONE%%/*}"
zone: "${TIMEZONE#*/}"
localeGenPath: "/etc/locale.gen"
EOF
# Debian's script ends in a broken preload loop ("): do", "ionice -C") that errors at every login.
sed -i -e 's/ionice -C Idle/ionice -c 3/' -e "s/}'): do\$/}'); do/" /usr/bin/add-calamares-desktop-icon
# glass-firstlogin puts the "Install Glass Panes" shortcut on the desktop itself.
rm -f /etc/xdg/autostart/calamares-desktop-icon.desktop
