#!/usr/bin/env bash
# Boots Glass Panes in a QEMU virtual machine.
#   run-qemu.sh               live ISO, BIOS firmware
#   run-qemu.sh --uefi        live ISO, UEFI firmware
#   run-qemu.sh --disks       also attach a blank 128 GB virtual SSD to install onto
#   run-qemu.sh --installed   boot the virtual SSD without the ISO, to test the installed system
#   run-qemu.sh --offline     no network (rehearse installs like a PC without Wi-Fi set up)
#   run-qemu.sh --headless    no window; drive it through the QMP socket (scripts/qmp.py)
#   run-qemu.sh --gl          3D-accelerated virtual GPU, so window blur and transparency work
#   run-qemu.sh --iso FILE    boot another ISO (e.g. a copy, so a rebuild can't replace it mid-test)
#   run-qemu.sh --vm-dir DIR  keep this VM's disks, UEFI vars and QMP socket in DIR (default build/vm)
# Anything after `--` goes straight to QEMU.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# shellcheck source=../config/os.conf
source config/os.conf

ISO="out/${OS_ID}-${OS_VERSION}-${ARCH}.iso"
VM_DIR="build/vm"
DISK_SIZE="128G"
OVMF_CODE="/usr/share/OVMF/OVMF_CODE_4M.fd"
OVMF_VARS="/usr/share/OVMF/OVMF_VARS_4M.fd"

uefi=no disks=no installed=no offline=no headless=no gl=no
extra=()
while (($#)); do
  case "$1" in
    --uefi) uefi=yes ;;
    --disks) disks=yes ;;
    --installed) installed=yes disks=yes ;;
    --offline) offline=yes ;;
    --headless) headless=yes ;;
    --gl) gl=yes ;;
    --iso) ISO="$2"; shift ;;
    --vm-dir) VM_DIR="$2"; shift ;;
    --) shift; extra=("$@"); break ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

mkdir -p "$VM_DIR"
# The USB tablet lets the pointer move in and out of the window without being grabbed.
gpu=virtio-vga
[[ $gl == yes ]] && gpu=virtio-vga-gl
args=(-machine q35 -m 4G -smp 4 -vga none -device "$gpu,xres=1600,yres=900"
      -device qemu-xhci -device usb-tablet -device intel-hda -device hda-duplex
      -name "$OS_NAME" -qmp "unix:$VM_DIR/qmp.sock,server=on,wait=off")

if [[ $headless == yes && $gl == yes ]]; then
  args+=(-display egl-headless)
elif [[ $headless == yes ]]; then
  args+=(-display none)
elif [[ $gl == yes ]]; then
  args+=(-display gtk,gl=on,zoom-to-fit=on)
else
  args+=(-display gtk,zoom-to-fit=on)
fi

if [[ $offline == yes ]]; then
  args+=(-nic none)
else
  args+=(-nic user,model=virtio-net-pci)
fi

if [[ -w /dev/kvm ]]; then
  args+=(-enable-kvm -cpu host)
else
  echo "warning: /dev/kvm not accessible, the VM will be very slow" >&2
fi

if [[ $uefi == yes ]]; then
  [[ -f $VM_DIR/uefi-vars.fd ]] || cp "$OVMF_VARS" "$VM_DIR/uefi-vars.fd"
  args+=(-drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE"
         -drive "if=pflash,format=raw,file=$VM_DIR/uefi-vars.fd")
fi

if [[ $disks == yes ]]; then
  disk="$VM_DIR/ssd.qcow2"
  [[ -f $disk ]] || qemu-img create -q -f qcow2 "$disk" "$DISK_SIZE"
  args+=(-drive "file=$disk,if=none,id=ssd,format=qcow2" -device "nvme,drive=ssd,serial=glassssd")
fi

if [[ $installed == yes ]]; then
  if [[ ! -f $VM_DIR/ssd.qcow2 ]]; then
    echo "No virtual SSD yet — install first with 'make run-install'." >&2
    exit 1
  fi
else
  [[ -f $ISO ]] || { echo "No ISO at $ISO — run 'make build-docker' first." >&2; exit 1; }
  args+=(-cdrom "$ISO" -boot once=d)
fi

exec qemu-system-x86_64 "${args[@]}" "${extra[@]}"
