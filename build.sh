#!/usr/bin/env bash
# Builds the Glass Panes live ISO on top of Debian.
#   sudo ./build.sh              full build -> out/<id>-<version>-<arch>.iso
#   sudo ./build.sh --clean      remove build output (keeps the download caches)
#   sudo ./build.sh --distclean  remove everything, including the caches
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
# shellcheck source=config/os.conf
source config/os.conf

WORK="$ROOT_DIR/build"
ROOTFS="$WORK/rootfs"
ISO_DIR="$WORK/iso"
CACHE="$WORK/cache"
EXT="$CACHE/ext"
OUT_DIR="$ROOT_DIR/out"
ISO="$OUT_DIR/${OS_ID}-${OS_VERSION}-${ARCH}.iso"
ISO_LABEL="$(printf '%s_%s' "$OS_ID" "$OS_VERSION" | tr 'a-z.-' 'A-Z__' | cut -c1-32)"

log() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

in_chroot() {
  chroot "$ROOTFS" /usr/bin/env -i \
    HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin TERM="${TERM:-xterm}" \
    LC_ALL=C DEBIAN_FRONTEND=noninteractive "$@"
}

mount_rootfs() {
  mount -t proc proc "$ROOTFS/proc"
  mount -t sysfs sys "$ROOTFS/sys"
  mount --bind /dev "$ROOTFS/dev"
  mount --bind /dev/pts "$ROOTFS/dev/pts"
  mount -t tmpfs tmpfs "$ROOTFS/run"
  mount --bind "$CACHE/apt" "$ROOTFS/var/cache/apt/archives"
}

unmount_rootfs() {
  local m
  for m in var/cache/apt/archives run dev/pts dev sys proc; do
    if mountpoint -q "$ROOTFS/$m" 2>/dev/null; then
      umount -l "$ROOTFS/$m"
    fi
  done
}

# --one-file-system stops rm from ever descending into a still-mounted /dev or /proc.
remove_tree() { unmount_rootfs; rm -rf --one-file-system "$@"; }

read_packages() { sed 's/#.*//' "$@" | tr -s '[:space:]' '\n' | sed '/^$/d'; }
read_groups() { sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$@"; }

[[ $EUID -eq 0 ]] || die "needs root: run 'sudo ./build.sh' (or 'make build-docker')"

case "${1:-}" in
  --clean) remove_tree "$ROOTFS" "$ISO_DIR" "$OUT_DIR"; echo "Cleaned."; exit 0 ;;
  --distclean) remove_tree "$WORK" "$OUT_DIR"; echo "Cleaned everything."; exit 0 ;;
  "") ;;
  *) die "unknown option: $1" ;;
esac

for tool in debootstrap mksquashfs grub-mkrescue xorriso mcopy apt-ftparchive curl strip; do
  command -v "$tool" >/dev/null || die "missing '$tool' — run 'make deps'"
done
[[ -f /usr/share/keyrings/debian-archive-keyring.gpg ]] || die "missing Debian keyring — run 'make deps'"
[[ -d /usr/lib/grub/i386-pc ]] || echo "warning: grub-pc-bin not installed, the ISO will only boot on UEFI" >&2

PACKAGE_LISTS=(config/packages/base.list config/packages/desktop.list config/packages/wine.list)
[[ $INSTALLER == yes ]] && PACKAGE_LISTS+=(config/packages/installer.list)
mapfile -t PACKAGES < <(read_packages "${PACKAGE_LISTS[@]}")

log "Fetching third-party themes, fonts and Wine add-ons"
./scripts/fetch-ext.sh

log "Drawing artwork"
python3 scripts/make-artwork.py "$WORK/art" \
  || die "could not draw artwork (are python3-pil and python3-numpy installed? run 'make deps')"

trap unmount_rootfs EXIT

log "Cleaning previous build"
remove_tree "$ROOTFS" "$ISO_DIR"
mkdir -p "$ROOTFS" "$ISO_DIR/live" "$ISO_DIR/boot/grub" \
  "$CACHE/debootstrap" "$CACHE/apt/partial" "$OUT_DIR"

log "Bootstrapping Debian $DEBIAN_SUITE ($ARCH)"
debootstrap --arch="$ARCH" --variant=minbase \
  --cache-dir="$CACHE/debootstrap" \
  --keyring=/usr/share/keyrings/debian-archive-keyring.gpg \
  --include=debian-archive-keyring,ca-certificates \
  --components=main,contrib,non-free,non-free-firmware \
  "$DEBIAN_SUITE" "$ROOTFS" "$DEBIAN_MIRROR"

log "Configuring APT sources"
rm -f "$ROOTFS/etc/apt/sources.list"
cat > "$ROOTFS/etc/apt/sources.list.d/debian.sources" <<EOF
Types: deb
URIs: $DEBIAN_MIRROR
Suites: $DEBIAN_SUITE $DEBIAN_SUITE-updates
Components: main contrib non-free non-free-firmware

Types: deb
URIs: http://security.debian.org/debian-security
Suites: $DEBIAN_SUITE-security
Components: main contrib non-free non-free-firmware
EOF

# Keep package installs from trying to start services inside the chroot.
printf '#!/bin/sh\nexit 101\n' > "$ROOTFS/usr/sbin/policy-rc.d"
chmod 755 "$ROOTFS/usr/sbin/policy-rc.d"
rm -f "$ROOTFS/etc/resolv.conf"
cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf"

echo "$OS_HOSTNAME" > "$ROOTFS/etc/hostname"
cat > "$ROOTFS/etc/hosts" <<EOF
127.0.0.1 localhost
127.0.1.1 $OS_HOSTNAME
::1       localhost ip6-localhost ip6-loopback
EOF

mount_rootfs

log "Installing ${#PACKAGES[@]} packages"
in_chroot dpkg --add-architecture i386
in_chroot apt-get update
in_chroot apt-get install -y --no-install-recommends "${PACKAGES[@]}"

log "Installing the Cherry Store and Cherry Move"
CHERRY_DEBS=(vendor/cherry/cherry-store.deb vendor/cherry/cherry-move_*_all.deb)
for f in "${CHERRY_DEBS[@]}" vendor/cherry/CherryMove/{CherryMove-Setup.exe,CherryMove.dmg,README.txt}; do
  [[ -f $f ]] || die "missing $f (copy the Cherry kit into vendor/cherry/)"
done
for deb in "${CHERRY_DEBS[@]}"; do
  cp "$deb" "$ROOTFS/tmp/"
done
in_chroot apt-get install -y --no-install-recommends "${CHERRY_DEBS[@]/#vendor\/cherry//tmp}"
rm -f "${CHERRY_DEBS[@]/#vendor\/cherry/$ROOTFS/tmp}"

if [[ $INSTALLER == yes ]]; then
  log "Building the installer's offline package repository"
  mkdir -p "$ROOTFS/tmp/pool/partial"
  while read -r -a group; do
    in_chroot apt-get install -y --download-only -o Dir::Cache::archives=/tmp/pool "${group[@]}" </dev/null
  done < <(read_groups config/installer-pool.list)
  REPO_INDEX="$ISO_DIR/dists/$DEBIAN_SUITE/main/binary-$ARCH"
  mkdir -p "$ISO_DIR/pool/main" "$REPO_INDEX"
  mv "$ROOTFS"/tmp/pool/*.deb "$ISO_DIR/pool/main/"
  (cd "$ISO_DIR" && apt-ftparchive packages pool > "$REPO_INDEX/Packages")
  gzip -9kf "$REPO_INDEX/Packages"
  apt-ftparchive \
    -o APT::FTPArchive::Release::Suite="$DEBIAN_SUITE" \
    -o APT::FTPArchive::Release::Codename="$DEBIAN_SUITE" \
    -o APT::FTPArchive::Release::Components=main \
    -o APT::FTPArchive::Release::Architectures="$ARCH" \
    release "$ISO_DIR/dists/$DEBIAN_SUITE" > "$WORK/Release"
  mv "$WORK/Release" "$ISO_DIR/dists/$DEBIAN_SUITE/Release"
fi

log "Applying overlay"
cp -a --no-preserve=ownership overlay/. "$ROOTFS/"

log "Installing the Glass Panes desktop (Start, Settings, Task Manager, Windows app support)"
LIB="$ROOTFS/usr/lib/$OS_ID"
install -d "$LIB"
cp -r --no-preserve=ownership desktop/lib/glasspanes "$LIB/"
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +
install_all() {  # MODE DEST FILES... (no-op when a folder is empty)
  local mode=$1 dest=$2
  shift 2
  [[ $# -gt 0 && -e $1 ]] && install -D -m "$mode" "$@" -t "$dest"
  return 0
}
shopt -s nullglob
install_all 755 "$ROOTFS/usr/bin" desktop/bin/*
install_all 755 "$ROOTFS/usr/libexec/$OS_ID" desktop/libexec/*
install_all 644 "$ROOTFS/usr/share/polkit-1/actions" desktop/polkit/*.policy
install_all 644 "$ROOTFS/usr/share/applications" desktop/applications/*.desktop
install_all 644 "$ROOTFS/etc/xdg/autostart" desktop/autostart/*.desktop
shopt -u nullglob
install -d "$ROOTFS/usr/share/$OS_ID"
cp -r --no-preserve=ownership desktop/icons "$ROOTFS/usr/share/$OS_ID/"
install -D -m 644 "$WORK"/art/*.png -t "$ROOTFS/usr/share/$OS_ID/artwork/"
install -D -m 644 "$WORK"/art/wallpapers/*.png -t "$ROOTFS/usr/share/backgrounds/$OS_ID/"
install -D -m 644 "$WORK/art/grub.png" "$ISO_DIR/boot/grub/background.png"
install -D -m 644 "$WORK"/art/plymouth/*.png -t "$ROOTFS/usr/share/plymouth/themes/$OS_ID/"
install -D -m 644 "$WORK"/art/sddm/*.png -t "$ROOTFS/usr/share/sddm/themes/$OS_ID/"

log "Copying third-party themes into the image"
rm -rf "$ROOTFS/tmp/ext"
mkdir -p "$ROOTFS/tmp/ext"
cp -a --no-preserve=ownership "$EXT"/. "$ROOTFS/tmp/ext/"

HOOK_ENV=(
  "OS_NAME=$OS_NAME" "OS_ID=$OS_ID" "OS_VERSION=$OS_VERSION" "OS_EDITION=$OS_EDITION"
  "OS_CODENAME=$OS_CODENAME" "OS_HOSTNAME=$OS_HOSTNAME" "DEBIAN_SUITE=$DEBIAN_SUITE"
  "LIVE_USERNAME=$LIVE_USERNAME" "TIMEZONE=$TIMEZONE"
)
for hook in hooks/*.sh; do
  [[ -e $hook ]] || continue
  log "Running hook $(basename "$hook")"
  install -m 755 "$hook" "$ROOTFS/tmp/hook.sh"
  in_chroot "${HOOK_ENV[@]}" /tmp/hook.sh
  rm -f "$ROOTFS/tmp/hook.sh"
done

# The Cherry packages rely on these; trust and pending transfers are per machine, so nothing may
# be recorded in /var/lib/cherry, and Cherry OS's own cherry-desktop conflicts with the store.
log "Checking the Cherry Store and Cherry Move setup"
for pkg in cherry-store-client cherry-move rclone avahi-utils; do
  in_chroot dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed" || die "$pkg is not installed"
done
! in_chroot dpkg-query -W -f='${Status}' cherry-desktop 2>/dev/null | grep -q "ok installed" \
  || die "cherry-desktop is installed"
[[ -z "$(ls -A "$ROOTFS/var/lib/cherry" 2>/dev/null)" ]] || die "/var/lib/cherry is not empty"
[[ -L "$ROOTFS/etc/systemd/system/timers.target.wants/cherry-store-self-update.timer" ]] \
  || die "the Cherry Store's self-update timer isn't enabled"

# Debian ships Wine's Windows DLLs with debug info, and Wine copies them into every user's
# Windows folder: stripping takes them from about 1.3 GB to 450 MB.
log "Stripping debug info from Wine's Windows libraries"
find "$ROOTFS"/usr/lib/*-linux-gnu/wine/*-windows -type f -print0 \
  | xargs -0 -n 64 strip --strip-debug

# The Store lists apps from the AppStream catalogue that apt downloads alongside the package lists
# (the appstream package's apt hook, installed after the first update). Keep both in the image so
# the Store is full from the first boot, even offline.
log "Downloading the Store's app catalogue"
in_chroot apt-get update
in_chroot appstreamcli refresh-cache --force
APPS="$(in_chroot appstreamcli status 2>/dev/null | sed -n 's/.*information on \([0-9]\+\) software.*/\1/p' | head -n1)"
[[ ${APPS:-0} -gt 1000 ]] || die "the Store's app catalogue is missing or tiny (${APPS:-0} entries)"
log "Store catalogue: $APPS entries"

log "Cleaning up the root filesystem"
umount -l "$ROOTFS/var/cache/apt/archives"
in_chroot apt-get clean
rm -rf "$ROOTFS"/var/lib/apt/lists/partial/* "$ROOTFS"/tmp/* "$ROOTFS/var/lib/dbus/machine-id"
rm -f "$ROOTFS/usr/sbin/policy-rc.d" "$ROOTFS/etc/resolv.conf"
: > "$ROOTFS/etc/machine-id"
unmount_rootfs

log "Compressing root filesystem (this takes a few minutes)"
KERNEL="$(find "$ROOTFS/boot" -maxdepth 1 -name 'vmlinuz-*' | sort -V | tail -n1)"
[[ -n $KERNEL ]] || die "no kernel found in $ROOTFS/boot"
cp "$KERNEL" "$ISO_DIR/live/vmlinuz"
cp "$ROOTFS/boot/initrd.img-${KERNEL##*/vmlinuz-}" "$ISO_DIR/live/initrd.img"
mksquashfs "$ROOTFS" "$ISO_DIR/live/filesystem.squashfs" -noappend -comp zstd -Xcompression-level 19 -b 1M

log "Creating bootable ISO"
LIVE_ARGS="live-config.hostname=$OS_HOSTNAME live-config.username=$LIVE_USERNAME"
LIVE_ARGS+=" live-config.user-fullname=$LIVE_FULLNAME"
LIVE_ARGS+=" live-config.locales=$LOCALE live-config.timezone=$TIMEZONE"
LIVE_ARGS+=" live-config.keyboard-layouts=$KEYBOARD_LAYOUT"
sed -e "s|@OS_NAME@|$OS_NAME|g" -e "s|@OS_VERSION@|$OS_VERSION|g" -e "s|@LIVE_ARGS@|$LIVE_ARGS|g" \
  config/grub.cfg.in > "$ISO_DIR/boot/grub/grub.cfg"
# Cherry Move for the old computer, at the top of the USB stick where Windows and macOS show it.
cp -r --no-preserve=ownership vendor/cherry/CherryMove "$ISO_DIR/"
sed "s/Cherry OS/$OS_NAME/g" vendor/cherry/CherryMove/README.txt \
  | awk 'NR == 1 { title = length($0) } NR == 2 && /^=+$/ { $0 = ""; while (length($0) < title) $0 = $0 "=" } 1' \
  > "$ISO_DIR/CherryMove/README.txt"
# Joliet keeps long file names ("CherryMove-Setup.exe") readable on Windows.
grub-mkrescue -o "$ISO" "$ISO_DIR" -- -volid "$ISO_LABEL" -joliet on
chown "${SUDO_UID:-0}:${SUDO_GID:-0}" "$OUT_DIR" "$ISO"

log "Done: $ISO ($(du -h "$ISO" | cut -f1))"
echo "Boot it with: make run"
