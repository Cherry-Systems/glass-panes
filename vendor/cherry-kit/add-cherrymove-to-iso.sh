#!/usr/bin/env bash
# Puts the Cherry Move app for people's OLD computers (Windows, Mac, other Linux) at the top of your ISO, as plain
# files they open from the USB stick before installing your OS. These are never installed or run on your OS.
# Usage: ./add-cherrymove-to-iso.sh ISO_TREE "Your OS name"
#   ISO_TREE is the folder that becomes the top of the ISO (live-build: config/includes.binary).
set -euo pipefail
tree="${1:?usage: $0 ISO_TREE \"Your OS name\"}"
name="${2:?usage: $0 ISO_TREE \"Your OS name\"}"
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$tree"
rm -rf "$tree/CherryMove"
tar -C "$tree" -xf "$kit/for-the-usb-stick/CherryMove.tar"
NAME="$name" perl -pi -e 's/Cherry OS/$ENV{NAME}/g' "$tree/CherryMove/README.txt"
echo "Added $tree/CherryMove/ ($(du -sh "$tree/CherryMove" | cut -f1)). Its README.txt now says \"$name\"."
