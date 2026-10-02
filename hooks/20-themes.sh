#!/bin/sh
# Runs inside the chroot. Installs the Windows 11 look: window borders, colours, Plasma theme,
# Kvantum widget style, icons, cursors, the Selawik font, and Wine's .NET/HTML add-ons.
# Sources were fetched by scripts/fetch-ext.sh into /tmp/ext.
set -eu
EXT=/tmp/ext

# Win11OS-kde (GPL-3.0). Its look-and-feel package and wallpapers are not used.
K="$EXT/win11os-kde"
mkdir -p /usr/share/aurorae/themes /usr/share/color-schemes /usr/share/plasma/desktoptheme /usr/share/Kvantum
cp -r "$K"/aurorae/* /usr/share/aurorae/themes/
cp "$K"/color-schemes/*.colors /usr/share/color-schemes/
cp -r "$K"/plasma/desktoptheme/* /usr/share/plasma/desktoptheme/
cp -r "$K"/Kvantum/* /usr/share/Kvantum/

# Win11 icon theme (GPL-3.0): installs Win11, Win11-dark (and -light).
bash "$EXT/win11-icons/install.sh" -d /usr/share/icons >/dev/null
for t in /usr/share/icons/Win11*; do
  gtk-update-icon-cache -q -f "$t" 2>/dev/null || true
done

# We10XOS cursors (GPL-3.0), made the system default pointer.
rm -rf /usr/share/icons/We10XOS-cursors
cp -r "$EXT/we10xos-cursors/dist" /usr/share/icons/We10XOS-cursors
sed -i 's/^Name=.*/Name=We10XOS Cursors/' /usr/share/icons/We10XOS-cursors/index.theme
update-alternatives --install /usr/share/icons/default/index.theme x-cursor-theme \
  /usr/share/icons/We10XOS-cursors/index.theme 90
update-alternatives --set x-cursor-theme /usr/share/icons/We10XOS-cursors/index.theme

# Selawik (OFL-1.1): Microsoft's open, Segoe UI-compatible font.
mkdir -p /usr/share/fonts/truetype/selawik
python3 - <<'EOF'
import zipfile
with zipfile.ZipFile("/tmp/ext/selawik.zip") as z:
    for n in z.namelist():
        if n.lower().endswith(".ttf"):
            with open("/usr/share/fonts/truetype/selawik/" + n.rsplit("/", 1)[-1], "wb") as f:
                f.write(z.read(n))
EOF
fc-cache -f >/dev/null

# Wine's Mono (.NET) and Gecko (web pages inside apps) so Windows apps work offline.
install -D -m 644 "$EXT"/wine-mono-*-x86.msi -t /usr/share/wine/mono/
install -D -m 644 "$EXT"/wine-gecko-*-x86.msi "$EXT"/wine-gecko-*-x86_64.msi -t /usr/share/wine/gecko/

# System-wide KDE defaults: our settings plus the Win11 light colours, so even the very first
# session (before glass-firstlogin runs) has the right colours.
python3 - <<'EOF'
import configparser

def load(path):
    cp = configparser.RawConfigParser(strict=False, interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    return cp

out = load("/usr/share/color-schemes/Win11OSLight.colors")
for sec in ("General", "KDE"):
    out.remove_section(sec)
mine = load("/etc/xdg/kdeglobals.in")
for sec in mine.sections():
    if not out.has_section(sec):
        out.add_section(sec)
    for k, v in mine.items(sec):
        out.set(sec, k, v)
with open("/etc/xdg/kdeglobals", "w", encoding="utf-8") as f:
    out.write(f, space_around_delimiters=False)
EOF
rm -f /etc/xdg/kdeglobals.in
