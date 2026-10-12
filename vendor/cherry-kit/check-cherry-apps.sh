#!/usr/bin/env bash
# Checks that Cherry Move and the Cherry Store are installed exactly as Cherry OS 1.0.20 has them
# (or newer, once the Cherry Store has updated them).
# Usage: ./check-cherry-apps.sh                  the running system (a VM of your built image)
#        sudo ./check-cherry-apps.sh --root DIR  an image's root filesystem
# Every line must say PASS (WARN lines are worth fixing). Exits non-zero if anything FAILs.
set -uo pipefail
root=/
[[ ${1:-} == --root ]] && root="$(realpath "${2:?usage: $0 [--root DIR]}")"
want=1.0.20
fails=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails + 1)); }
warn() { echo "WARN  $*"; }
status() { dpkg-query --admindir="$root/var/lib/dpkg" -W -f='${db:Status-Status} ${Version}' "$1" 2>/dev/null; }
in_root() { if [[ $root == / ]]; then "$@"; else chroot "$root" "$@"; fi; }

declare -A updated
for p in cherry-move cherry-store-client; do
  s="$(status "$p")"
  case "$s" in
    "installed $want") pass "$p $want is installed" ;;
    installed*)
      if dpkg --compare-versions "${s#installed }" gt "$want"; then
        updated[$p]=1
        pass "$p is ${s#installed }, newer than the kit's $want (updated through the Cherry Store)"
      else
        fail "$p is version ${s#installed }, but Cherry OS uses $want: install the one in install-into-image/"
      fi ;;
    *) fail "$p is not installed: run install-cherry-apps.sh" ;;
  esac
done
[[ $(status cherry-desktop) == installed* ]] &&
  fail "cherry-desktop is installed: it's Cherry OS's own package, not for other systems. Remove it." ||
  pass "cherry-desktop (Cherry OS only) is not installed"
[[ $(status cherry-move-app) == installed* ]] &&
  fail "cherry-move-app is installed: that's the app for people's OLD computers, which only goes on the install USB as a file. Remove it." ||
  pass "cherry-move-app (old-computer app) is not installed"

# The same files as the kit's packages, so nothing was rebuilt, patched or swapped for another version.
# A package the store has updated has newer files, which the store checked against Cherry OS's signature.
while read -r pkg sum file; do
  if [[ -n ${updated[$pkg]:-} ]]; then
    continue
  elif [[ ! -e $root/$file ]]; then
    fail "/$file is missing"
  elif [[ $(sha256sum < "$root/$file" | cut -d' ' -f1) != "$sum" ]]; then
    fail "/$file differs from Cherry OS $want's copy: reinstall the packages from install-into-image/"
  else
    pass "/$file matches Cherry OS $want"
  fi
done <<'EOF'
cherry-move c3ad2c24b2bb26eaf1f4e6df0b5575bb6f1cf1abec9658b549ec119890abb2ba  etc/xdg/autostart/cherry-move-pending.desktop
cherry-move 4603cd2d2e972ea05fd6cb9e3c8adcdb99c6b3017b0c62ae649a5c5a9740a339  etc/xdg/autostart/cherry-move-watch.desktop
cherry-move 72d75cdc0855cb39aac823f632e0ba5ccfced0a45966f1a1950295c8af38088e  usr/bin/cherry-move
cherry-move 3edc32e1d182dedc8ba5fda4f5d18aa8c700c35530b11b274647db3f71a9e9ac  usr/lib/cherry-move/cherryos/codes.py
cherry-move c440624c70e998e0ce6e1fb50f8d25a6812daf7460c5a88c3ad7b32e28b76bb6  usr/lib/cherry-move/cherryos/desktops.py
cherry-move 18a3c968b0debd8b491d41ba910dade83d815227bdee3061c4898e5fb1862959  usr/lib/cherry-move/cherryos/__init__.py
cherry-move e03bf8440787aac78dd8823bccc93141f233a31e92ce08ec85fae5f7f0888fa9  usr/lib/cherry-move/cherryos/remote.py
cherry-move 94a7e51fb7dd482a1d9017155ef6a25a697f2c3a683817372df1969fefb51f50  usr/lib/cherry-move/cherryos/secret_store.py
cherry-move a30e4e20fc3cd6db1d64bb57c2c87c1af74295b5bf0ee6b7a2d508f1cce3c825  usr/lib/cherry-move/cherryos/system_extras.py
cherry-move eea2b28f37c421ac869c4d9590782e04feb6493ab5c6f8f9d1e1d1d5c43dd9f8  usr/lib/cherry-move/cherryos/transfer.py
cherry-move bb5ca7714e9df70da6b5c18d0c2c7fee489e9f5a47f511fe620947bde7586674  usr/lib/cherry-move/cherryos/ui/__init__.py
cherry-move ae259056a38fb719c2a75215cde6ae3a38e354ac0aa2c1515a27da2ec5447161  usr/lib/cherry-move/cherryos/ui/move.py
cherry-move 0d4b8106a0f65c50f0d17f10702d7fbf603e6ed61573a36645059b183b6c0501  usr/share/applications/cherry-move.desktop
cherry-move 7aa8fc0241f0debaf3e7a55b97933c33299bf7a7097116b2ac99ad6478fabca8  usr/share/icons/hicolor/scalable/apps/cherry-logo.svg
cherry-move 5c28fa1db5d2384342618f61869558aa52df3589410d5f59b98597b56619c997  usr/share/icons/hicolor/scalable/apps/cherry-move.svg
cherry-store-client 4963f72997ff5bd7a05633b07e243f77d0e0fe2f83613cce883295798c8be84c  usr/bin/cherry
cherry-store-client 7320757bc32b00d1a6082ce483f623ba3e8029904895e152b0a86ddbdde96620  usr/bin/cherry-store
cherry-store-client cc6d8b610025a6782b657f9a3b3a10efb5cc5e2e4e314da4803584617df7f384  usr/lib/cherry/cherryos/cloud.py
cherry-store-client 18a3c968b0debd8b491d41ba910dade83d815227bdee3061c4898e5fb1862959  usr/lib/cherry/cherryos/__init__.py
cherry-store-client 92fbe935ebee3ce0a4d0f28a98749fbabf62413724afa535a1b81ce28353c554  usr/lib/cherry/cherryos/pkg.py
cherry-store-client bb5ca7714e9df70da6b5c18d0c2c7fee489e9f5a47f511fe620947bde7586674  usr/lib/cherry/cherryos/ui/__init__.py
cherry-store-client ba5315a3e93314e24104cb4a031a1d27d223e8d3e95431090de4e2bc78314015  usr/lib/cherry/cherryos/ui/store.py
cherry-store-client 5a56bbf9d2eabafd150909e754c5d2070e4dc1fce6fc419883288a4ffdabfd3f  usr/lib/systemd/system/cherry-store-self-update.service
cherry-store-client ebd3e084784d87225aa6e45764fea2db99569cc5536100fe02c7254629ea212c  usr/lib/systemd/system/cherry-store-self-update.timer
cherry-store-client 511ef7689331c36a0854a0f40aabaa9c31a714a2f9cb0cc85157db55246d4f1c  usr/share/applications/cherry-store.desktop
cherry-store-client 6d34bc4cf957e0fc52277ef3f4e81e31ee2bec8e49a8e12924f045d18c089e7b  usr/share/icons/hicolor/scalable/apps/cherry-store.svg
cherry-store-client 231e693a7352cf4eca3c7e6eabb27c9516b0d4c6d6cf955afb76d2d64b1e9192  usr/share/polkit-1/actions/org.cherryos.cherry.policy
EOF

grep -qx 'StartupWMClass=org.cherryos.Move' "$root/usr/share/applications/cherry-move.desktop" 2>/dev/null &&
grep -qx 'StartupWMClass=org.cherryos.Store' "$root/usr/share/applications/cherry-store.desktop" 2>/dev/null &&
  pass "menu entries keep their names (docks show the right icons)" ||
  fail "a menu entry's StartupWMClass was changed: keep org.cherryos.Move and org.cherryos.Store"
[[ -L $root/etc/systemd/system/timers.target.wants/cherry-store-self-update.timer ]] &&
  pass "daily self-update timer is enabled" ||
  fail "cherry-store-self-update.timer isn't enabled: run 'systemctl enable cherry-store-self-update.timer' in the image"
[[ -x $root/usr/bin/rclone ]] && pass "rclone is installed (cloud drives and NAS)" ||
  warn "rclone isn't installed: Cherry Move's cloud drive and NAS options are greyed out"
[[ -x $root/usr/bin/avahi-browse ]] && pass "avahi-utils is installed (finds NAS boxes)" ||
  warn "avahi-utils isn't installed: people have to type their NAS's address"
if [[ -n $(ls -A "$root/var/lib/cherry" 2>/dev/null) && $root != / ]]; then
  warn "/var/lib/cherry isn't empty in the image: trusted keys and pending transfers are per computer, so empty it"
fi

if [[ $root == / || $EUID -eq 0 ]]; then
  in_root cherry-move --help >/dev/null 2>&1 && pass "cherry-move runs" || fail "cherry-move --help fails: its dependencies are missing"
  in_root cherry --help >/dev/null 2>&1 && pass "cherry runs" || fail "cherry --help fails: its dependencies are missing"
else
  warn "not root, so cherry-move and cherry weren't started inside $root"
fi

echo
if ((fails)); then
  echo "$fails check(s) failed."
  exit 1
fi
echo "All checks passed: Cherry Move and the Cherry Store are installed the same way as on Cherry OS $want."
