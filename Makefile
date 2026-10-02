.PHONY: deps build build-docker fetch run run-uefi run-install run-installed reset-vm artwork test \
	try-start try-settings try-taskmgr try-run clean distclean

HOST_PACKAGES = debootstrap debian-archive-keyring squashfs-tools xorriso apt-utils curl \
	grub-pc-bin grub-efi-amd64-bin mtools qemu-system-x86 qemu-utils ovmf python3-pil python3-numpy

# Run the desktop apps from the source tree with a throwaway home, so trying them on this PC never
# touches your real settings. Needs PyQt6 (build/venv is used if present: `make venv`).
PY = $(if $(wildcard build/venv/bin/python3),build/venv/bin/python3,python3)
TRY_ENV = HOME=$(CURDIR)/build/try-home GLASSPANES_DATA=$(CURDIR)/desktop PYTHONPATH=$(CURDIR)/desktop/lib

deps:
	sudo apt-get install -y $(HOST_PACKAGES)

venv:
	python3 -m venv build/venv && build/venv/bin/pip install -q PyQt6 psutil pillow numpy

build:
	sudo ./build.sh

# Same build inside a Debian container: no host build tools or sudo needed, just Docker.
build-docker:
	./scripts/build-in-docker.sh

fetch:
	./scripts/fetch-ext.sh

run:
	./scripts/run-qemu.sh

run-uefi:
	./scripts/run-qemu.sh --uefi

# Rehearse a real install: UEFI, a blank 128 GB virtual SSD, and no network.
run-install:
	./scripts/run-qemu.sh --uefi --disks --offline

# Boot what was installed by run-install, without the ISO.
run-installed:
	./scripts/run-qemu.sh --uefi --installed

# Wipe the virtual SSD and UEFI settings to start the install rehearsal over.
reset-vm:
	rm -rf build/vm

artwork:
	python3 scripts/make-artwork.py build/art

test:
	PYTHONPATH=desktop/lib $(PY) -m unittest discover -s tests -v

try-start:
	$(TRY_ENV) $(PY) -m glasspanes.start --show

try-settings:
	$(TRY_ENV) $(PY) -m glasspanes.settings

try-taskmgr:
	$(TRY_ENV) $(PY) -m glasspanes.taskmgr

try-run:
	$(TRY_ENV) $(PY) -m glasspanes.rundialog

clean:
	sudo ./build.sh --clean

distclean:
	sudo ./build.sh --distclean
