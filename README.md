# Glass Panes

A Linux distribution that looks and works like Windows 11: centred taskbar, Start menu, Settings,
Task Manager, File Explorer, Win+R, Win+X, Ctrl+Alt+Del, and Windows programs (`.exe` / `.msi`) that
install and run with a double-click. Underneath it's Debian 13 ("trixie") with KDE Plasma, so it's
light, fast, free of adverts and bloatware, and never restarts itself for updates.

No Microsoft logos, Edge or Copilot: Glass Panes has its own logo and artwork.

Download the PC install image: [glasspanes-1.0-amd64.iso](https://github.com/Cherry-Systems/glass-panes/releases/download/v1.0/glasspanes-1.0-amd64.iso)
(SHA-256 `f8b8dfa293f46564d4828188755aa37dd8b0c710bfdb7c26a570ca7188288eeb`).
Write it to a USB stick and boot from it. The product page is
https://cherry-systems.github.io/products/glass-panes/.

## What's in it

| Windows | Glass Panes |
| --- | --- |
| Start, Search, Task View | Glass Panes shell (`desktop/lib/glasspanes/start.py`, `shell.py`) |
| Settings | Glass Panes Settings (`settings/`), with the KDE Control Panel for advanced options |
| Task Manager (Ctrl+Shift+Esc) | `taskmgr.py` |
| Run (Win+R), Win+X menu, Ctrl+Alt+Del screen | `rundialog.py`, `shell.py`, `security.py` |
| Quick Settings (Win+A, or the network and volume icons): Wi-Fi, Bluetooth, night light, energy saver, volume, brightness | `quicksettings.py` |
| Snap layouts (Win+Z) | `snaplayouts.py` |
| Narrator (Win+Ctrl+Enter) | Orca screen reader (`narrator.py`) |
| Right-click menus for the taskbar, desktop and Recycle Bin | `shell.py`, with small patches to Plasma's QML (`overlay/usr/share/glasspanes/plasma/patch-qml.py`) |
| Sign-in and lock screens (Win+L) | SDDM theme and Plasma lock screen (`overlay/usr/share/sddm/themes/glasspanes`, `overlay/usr/share/glasspanes/lockscreen`) |
| Recycle Bin | KDE Trash, renamed |
| Windows Update | Glass Update (Debian security updates and Store app updates) |
| Microsoft Store | Store (KDE Discover with Flathub) |
| File Explorer, Notepad, Paint, Photos, Snipping Tool, Calculator, Terminal, Disk Management | Dolphin, KWrite, KolourPaint, Gwenview, Spectacle, KCalc, Konsole, KDE Partition Manager, renamed |
| Running Windows programs | Wine 10, with .NET (Mono) and Gecko included for offline use |
| Windows Easy Transfer / moving to a new PC | Cherry Move (`CherryMove/` on the install USB has the app for the old Windows, Mac or Linux computer) |

The Cherry Store (apps published by anyone, installed through apt) is included too, and Glass Update
keeps its apps up to date. Both Cherry apps come from Cherry Systems' kit in `vendor/cherry-kit/`.

Keyboard shortcuts match Windows: Win (Start), Win+S, Win+E, Win+I, Win+R, Win+X, Win+L, Win+D,
Win+M, Win+Shift+M, Win+Home, Win+Tab, Win+Up/Down/Left/Right, Win+Z, Win+Ctrl+D, Win+Ctrl+F4, Win+A,
Win+N, Win+Shift+S, Win+Ctrl+Enter, Alt+Tab, Alt+F4, Ctrl+Esc, Ctrl+Shift+Esc and Ctrl+Alt+Del.
Right-clicking Start opens the Win+X menu. Win+H says voice typing isn't available (there's no speech
recognition yet), and Win+K (Cast) isn't used.

## Building

The build runs in a privileged Docker container, so nothing needs installing on the host.
Being in the `docker` group is effectively root access, so only do this on your own PC.

```sh
make build-docker      # -> out/glasspanes-1.0-amd64.iso (about 25-40 minutes the first time)
make run               # try the ISO in QEMU (BIOS)
make run-install       # UEFI VM with a blank virtual disk, offline, to rehearse installing
make run-installed     # boot the installed virtual disk
make test              # unit tests for the shell logic
make try-start         # run the Start menu / Settings / Task Manager on this PC
make try-settings
make try-taskmgr
```

Configuration (name, edition, locale, Debian release) is in `config/os.conf`; the package lists
are in `config/packages/`.

The live session signs in automatically as `user`; its password is `live` (Debian's default), so
don't leave a live session unattended on a network you don't trust.

## How it's put together

- `build.sh` — debootstrap, packages, overlay, hooks, squashfs, hybrid BIOS/UEFI ISO.
- `config/` — OS identity, package lists, the boot menu, and the installer's offline package groups.
- `desktop/` — the Glass Panes apps (Python + PyQt6), launchers and autostart entries.
- `overlay/` — files copied into the image: Plasma defaults and taskbar layout, sign-in screen,
  boot splash, fonts, shortcuts, file associations, terminal profile.
- `hooks/` — scripts run inside the image: branding, themes, app renames, installer, boot splash.
- `scripts/` — artwork generator, third-party downloads, Docker and QEMU helpers.

## Credits and licences

Glass Panes' own code and artwork are GPL-3.0-or-later. It includes:

- [Win11OS-kde](https://github.com/yeyushengfan258/Win11OS-kde) by yeyushengfan258 — window
  borders, colours, Plasma and Kvantum themes (GPL-3.0). Its wallpapers are not included.
- [Win11 icon theme](https://github.com/yeyushengfan258/Win11-icon-theme) by yeyushengfan258 (GPL-3.0).
- [We10XOS cursors](https://github.com/yeyushengfan258/We10XOS-cursors) by yeyushengfan258 (GPL-3.0).
- [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) by Microsoft (MIT),
  used in Start, Settings and Task Manager.
- [Selawik](https://github.com/microsoft/Selawik) by Microsoft (SIL OFL 1.1), the interface font.
- [Wine](https://www.winehq.org/), [Wine Mono](https://gitlab.winehq.org/mono/wine-mono) and
  [Wine Gecko](https://gitlab.winehq.org/wine/wine-gecko) (LGPL and MPL).
- Debian, KDE Plasma and Calamares.

Windows is a trademark of Microsoft Corporation. Glass Panes is not affiliated with or endorsed by
Microsoft.
