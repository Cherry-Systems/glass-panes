#!/usr/bin/env bash
# Checks that Cherry Move and the Cherry Store are installed exactly as Cherry OS 1.0.6 has them.
# Usage: ./check-cherry-apps.sh                  the running system (a VM of your built image)
#        sudo ./check-cherry-apps.sh --root DIR  an image's root filesystem
# Every line must say PASS (WARN lines are worth fixing). Exits non-zero if anything FAILs.
set -uo pipefail
root=/
[[ ${1:-} == --root ]] && root="$(realpath "${2:?usage: $0 [--root DIR]}")"
want=1.0.6
fails=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails + 1)); }
warn() { echo "WARN  $*"; }
status() { dpkg-query --admindir="$root/var/lib/dpkg" -W -f='${db:Status-Status} ${Version}' "$1" 2>/dev/null; }
in_root() { if [[ $root == / ]]; then "$@"; else chroot "$root" "$@"; fi; }

for p in cherry-move cherry-store-client; do
  s="$(status "$p")"
  case "$s" in
    "installed $want") pass "$p $want is installed" ;;
    installed*) fail "$p is version ${s#installed }, but Cherry OS uses $want: install the one in install-into-image/" ;;
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
while read -r sum file; do
  if [[ ! -e $root/$file ]]; then
    fail "/$file is missing"
  elif [[ $(sha256sum < "$root/$file" | cut -d' ' -f1) != "$sum" ]]; then
    fail "/$file differs from Cherry OS $want's copy: reinstall the packages from install-into-image/"
  else
    pass "/$file matches Cherry OS $want"
  fi
done <<'EOF'
c3ad2c24b2bb26eaf1f4e6df0b5575bb6f1cf1abec9658b549ec119890abb2ba  etc/xdg/autostart/cherry-move-pending.desktop
4603cd2d2e972ea05fd6cb9e3c8adcdb99c6b3017b0c62ae649a5c5a9740a339  etc/xdg/autostart/cherry-move-watch.desktop
786194a648419a9bcebae9aeeae3419e4e02d1f4d7481c8989858aafaac6662e  usr/bin/cherry
876c3d43bc5ecdbde89327a224aa6eeee0547cafda4121291513680bb3b97019  usr/bin/cherry-move
7320757bc32b00d1a6082ce483f623ba3e8029904895e152b0a86ddbdde96620  usr/bin/cherry-store
cc6d8b610025a6782b657f9a3b3a10efb5cc5e2e4e314da4803584617df7f384  usr/lib/cherry/cherryos/cloud.py
f5d8da105ef17da4eba98b5c59c2986bcf4df59e0220eb9561b9b8552881ab35  usr/lib/cherry/cherryos/__init__.py
92fbe935ebee3ce0a4d0f28a98749fbabf62413724afa535a1b81ce28353c554  usr/lib/cherry/cherryos/pkg.py
e77f97994f4094115c8bfccdfb6f73dc8f084353d80bb78363ac70b1ae103b6f  usr/lib/cherry/cherryos/ui/__init__.py
ba5315a3e93314e24104cb4a031a1d27d223e8d3e95431090de4e2bc78314015  usr/lib/cherry/cherryos/ui/store.py
3edc32e1d182dedc8ba5fda4f5d18aa8c700c35530b11b274647db3f71a9e9ac  usr/lib/cherry-move/cherryos/codes.py
237a7f4c7f3b0dd441cb0f414907b3715c7b10ac2e6028d3d93bdfdb0a5ca9e0  usr/lib/cherry-move/cherryos/desktops.py
f5d8da105ef17da4eba98b5c59c2986bcf4df59e0220eb9561b9b8552881ab35  usr/lib/cherry-move/cherryos/__init__.py
4721195a1dcbf4e68d7cc3611116b8ccbfe7a0b6491b4bc28bddcffaf3d51dc1  usr/lib/cherry-move/cherryos/remote.py
c1857fdc920f69822fec68c6621c5e96ff76185efb5beff4c47ef3c94257574e  usr/lib/cherry-move/cherryos/transfer.py
e77f97994f4094115c8bfccdfb6f73dc8f084353d80bb78363ac70b1ae103b6f  usr/lib/cherry-move/cherryos/ui/__init__.py
50af9adb814f8c9f0eb8fddcbda881e238a6211e510217dfe44bd3a63c3f3cd1  usr/lib/cherry-move/cherryos/ui/move.py
5a56bbf9d2eabafd150909e754c5d2070e4dc1fce6fc419883288a4ffdabfd3f  usr/lib/systemd/system/cherry-store-self-update.service
ebd3e084784d87225aa6e45764fea2db99569cc5536100fe02c7254629ea212c  usr/lib/systemd/system/cherry-store-self-update.timer
0d4b8106a0f65c50f0d17f10702d7fbf603e6ed61573a36645059b183b6c0501  usr/share/applications/cherry-move.desktop
511ef7689331c36a0854a0f40aabaa9c31a714a2f9cb0cc85157db55246d4f1c  usr/share/applications/cherry-store.desktop
7aa8fc0241f0debaf3e7a55b97933c33299bf7a7097116b2ac99ad6478fabca8  usr/share/icons/hicolor/scalable/apps/cherry-logo.svg
5c28fa1db5d2384342618f61869558aa52df3589410d5f59b98597b56619c997  usr/share/icons/hicolor/scalable/apps/cherry-move.svg
6d34bc4cf957e0fc52277ef3f4e81e31ee2bec8e49a8e12924f045d18c089e7b  usr/share/icons/hicolor/scalable/apps/cherry-store.svg
231e693a7352cf4eca3c7e6eabb27c9516b0d4c6d6cf955afb76d2d64b1e9192  usr/share/polkit-1/actions/org.cherryos.cherry.policy
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
