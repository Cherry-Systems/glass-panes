# Glass Panes

A Linux distribution that looks and works like Windows 11: centred taskbar, Start menu, Settings,
Task Manager, File Explorer, Win+R, Win+X, Ctrl+Alt+Del, and Windows programs (`.exe` / `.msi`) that
install and run with a double-click. Underneath it's Debian 13 ("trixie") with KDE Plasma, so it's
light, fast, free of adverts and bloatware, and never restarts itself for updates.

No Microsoft logos, Edge or Copilot: Glass Panes has its own logo and artwork.

## What's in it

| Windows | Glass Panes |
| --- | --- |
| Start, Search, Task View | Glass Panes shell (`desktop/lib/glasspanes/start.py`, `shell.py`) |
| Settings | Glass Panes Settings (`settings/`), with the KDE Control Panel for advanced options |
| Task Manager (Ctrl+Shift+Esc) | `taskmgr.py` |
| Run (Win+R), Win+X menu, Ctrl+Alt+Del screen | `rundialog.py`, `shell.py`, `security.py` |
| Windows Update | Glass Update (Debian security updates and Store app updates) |
| Microsoft Store | Store (KDE Discover with Flathub) |
| File Explorer, Notepad, Paint, Photos, Snipping Tool, Calculator, Terminal | Dolphin, KWrite, KolourPaint, Gwenview, Spectacle, KCalc, Konsole, renamed |
| Running Windows programs | Wine 10, with .NET (Mono) and Gecko included for offline use |

Keyboard shortcuts match Windows: Win (Start), Win+S, Win+E, Win+I, Win+R, Win+X, Win+L, Win+D,
Win+Tab, Win+Up/Down, Win+Shift+S, Alt+Tab, Alt+F4, Ctrl+Esc, Ctrl+Shift+Esc and Ctrl+Alt+Del.

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
