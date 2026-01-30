#!/bin/bash
# Start Xorg :0 with NVIDIA driver for VirtualGL when GPU is present.
# If no NVIDIA GPU, sleep forever so supervisord does not keep retrying.
set -e
if ! nvidia-smi &>/dev/null; then
  echo "No NVIDIA GPU detected; skipping X :0 (VirtualGL will not be used)."
  exec sleep infinity
fi
BUS_ID_RAW="$(nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader 2>/dev/null | head -n 1 | tr -d '[:space:]')"
CONFIG_SRC="/etc/X11/xorg.conf.nvidia"
CONFIG_TMP="/tmp/xorg.conf.nvidia"
if [ -n "$BUS_ID_RAW" ]; then
  # Convert 00000000:01:00.0 -> PCI:1:0:0
  BUS_ID_FMT="PCI:$(echo "$BUS_ID_RAW" | awk -F'[:.]' '{printf("%d:%d:%d", strtonum("0x"$2), strtonum("0x"$3), strtonum("0x"$4))}')"
  echo "Using NVIDIA BusID: $BUS_ID_FMT"
  awk -v busid="$BUS_ID_FMT" '
    $0 ~ /Section "Device"/ {print; in_dev=1; next}
    in_dev && $0 ~ /Driver "nvidia"/ {print; print "  BusID \"" busid "\""; next}
    $0 ~ /EndSection/ && in_dev {in_dev=0}
    {print}
  ' "$CONFIG_SRC" > "$CONFIG_TMP"
else
  echo "No BusID detected; using default Xorg config."
  cp "$CONFIG_SRC" "$CONFIG_TMP"
fi
exec /usr/bin/Xorg :0 -config "$CONFIG_TMP" -keeptty -novtswitch -sharevts
