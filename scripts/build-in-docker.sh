#!/usr/bin/env bash
# Runs build.sh inside a privileged Debian container, so the build tools don't have to be installed on
# the host and no sudo password is needed (only membership of the docker group, which is effectively
# root). Same options as build.sh.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

exec docker run --rm --privileged --name glasspanes-build \
  -v "$PWD:$PWD" -w "$PWD" -e SUDO_UID="$(id -u)" -e SUDO_GID="$(id -g)" -e TERM \
  debian:trixie bash -c '
    set -e
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debootstrap debian-archive-keyring \
      squashfs-tools xorriso apt-utils binutils grub-pc-bin grub-efi-amd64-bin mtools curl ca-certificates \
      python3-pil python3-numpy fonts-dejavu-core >/dev/null
    exec ./build.sh "$@"' build-in-docker "$@"
