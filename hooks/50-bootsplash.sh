#!/bin/sh
# Runs inside the chroot. Makes the Glass Panes logo with spinning dots the boot screen (Plymouth).
set -eu
command -v plymouth-set-default-theme >/dev/null || exit 0

plymouth-set-default-theme "$OS_ID"
update-initramfs -u -k all

if [ -d /etc/calamares/modules ]; then
  echo "plymouth_theme: $OS_ID" > /etc/calamares/modules/plymouthcfg.conf
fi
