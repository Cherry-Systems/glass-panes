#!/bin/sh
# Runs inside the chroot. Replaces Debian's identity with Glass Panes.
set -eu
ART="/usr/share/$OS_ID/artwork"

# Divert so Debian's base-files upgrades don't put its os-release back.
dpkg-divert --local --rename --add /usr/lib/os-release
cat > /usr/lib/os-release <<EOF
PRETTY_NAME="$OS_NAME $OS_VERSION"
NAME="$OS_NAME"
VERSION="$OS_VERSION ($OS_EDITION)"
VERSION_ID="$OS_VERSION"
VARIANT="$OS_EDITION"
VARIANT_ID=$(echo "$OS_EDITION" | tr 'A-Z ' 'a-z-')
ID=$OS_ID
ID_LIKE=debian
VERSION_CODENAME=$DEBIAN_SUITE
LOGO=$OS_ID-logo
EOF
ln -sf ../usr/lib/os-release /etc/os-release

printf '%s %s \\n \\l\n\n' "$OS_NAME" "$OS_VERSION" > /etc/issue
printf '%s %s\n' "$OS_NAME" "$OS_VERSION" > /etc/issue.net
printf '\n   %s %s %s\n\n' "$OS_NAME" "$OS_EDITION" "$OS_VERSION" > /etc/motd

# The logo as an icon: system information pages, the Start button, the installer.
for px in 16 24 32 48 64 128 256; do
  install -D -m 644 "$ART/logo-$px.png" "/usr/share/icons/hicolor/${px}x${px}/apps/$OS_ID-logo.png"
  install -D -m 644 "$ART/logo-$px.png" "/usr/share/icons/hicolor/${px}x${px}/apps/$OS_ID-start.png"
done
install -D -m 644 "$ART/logo.png" /usr/share/pixmaps/$OS_ID-logo.png
gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true

# Installed systems start straight into Glass Panes like Windows: no boot menu unless Esc is held.
mkdir -p /etc/default/grub.d
cat > /etc/default/grub.d/$OS_ID.cfg <<EOF
GRUB_DISTRIBUTOR="$OS_NAME"
GRUB_TIMEOUT=2
GRUB_TIMEOUT_STYLE=hidden
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=3"
GRUB_BACKGROUND="$ART/grub.png"
GRUB_GFXMODE=1024x768,auto
EOF

# Default account picture for new users.
install -D -m 644 "$ART/user.png" /usr/share/sddm/faces/.face.icon
install -D -m 644 "$ART/user.png" /etc/skel/.face.icon
