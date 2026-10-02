#!/usr/bin/env bash
# Downloads the third-party, freely licensed pieces Glass Panes ships (pinned versions) into
# build/cache/ext. Safe to re-run: anything already downloaded is kept.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

EXT="build/cache/ext"
mkdir -p "$EXT"

# name  url  (tarballs are unpacked into $EXT/<name>, other files are saved as-is)
SOURCES=(
  "win11os-kde https://codeload.github.com/yeyushengfan258/Win11OS-kde/tar.gz/9f021c3e71da7baf59a0614ab858d53b1e455fd5"
  "win11-icons https://codeload.github.com/yeyushengfan258/Win11-icon-theme/tar.gz/a5b460a407da143b32f19a503d7fcebb3edf2371"
  "we10xos-cursors https://codeload.github.com/yeyushengfan258/We10XOS-cursors/tar.gz/b971891cc016ba780af791ac9872a15406695ad8"
  "selawik.zip https://github.com/microsoft/Selawik/releases/download/1.01/Selawik_Release.zip"
  "wine-mono-9.4.0-x86.msi https://dl.winehq.org/wine/wine-mono/9.4.0/wine-mono-9.4.0-x86.msi"
  "wine-gecko-2.47.4-x86.msi https://dl.winehq.org/wine/wine-gecko/2.47.4/wine-gecko-2.47.4-x86.msi"
  "wine-gecko-2.47.4-x86_64.msi https://dl.winehq.org/wine/wine-gecko/2.47.4/wine-gecko-2.47.4-x86_64.msi"
)

for entry in "${SOURCES[@]}"; do
  read -r name url <<<"$entry"
  if [[ -e $EXT/$name ]]; then
    continue
  fi
  echo "Downloading $name"
  if [[ $url == https://codeload.github.com/* ]]; then
    mkdir -p "$EXT/$name.tmp"
    curl -fsSL "$url" | tar -xz -C "$EXT/$name.tmp" --strip-components=1
    mv "$EXT/$name.tmp" "$EXT/$name"
  else
    curl -fsSL -o "$EXT/$name.tmp" "$url"
    mv "$EXT/$name.tmp" "$EXT/$name"
  fi
done
echo "Third-party assets ready in $EXT"
