#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Stage configuration before a first installation. Does not write firmware.
# Requires a verified per-target guard and dpn_storage install=1 already loaded.
set -eu
mode=${1:-};guard=${2:-};tool=${3:-/usr/libexec/dpn-install}
case "$mode" in fresh|migrate|finish|commit|rollback) ;; *) exit 64;; esac
[ "$mode" = commit ] || [ "$mode" = rollback ] || command -v dropbearkey >/dev/null
[ -f "$guard" ] && [ -x "$tool" ]
[ "$(cat /sys/class/mtd/mtd2/name)" = dpn-firmware-update ]
[ "$(cat /sys/class/mtd/mtd3/name)" = dpn-config ]
[ "$(cat /sys/class/mtd/mtd3/size)" = 268435456 ]
cfg=/tmp/dpn-first-config
if [ "$mode" = finish ] && [ -e /sys/class/ubi/ubi0 ]; then
 [ "$(cat /sys/class/ubi/ubi0/mtd_num)" = 3 ]
else
 [ ! -e /sys/class/ubi/ubi0 ]
 if [ "$mode" = fresh ]; then
 "$tool" --check-config-blank
 ubiformat /dev/mtd3 -y
 ubiattach -m 3 -d 0
 ubimkvol /dev/ubi0 -N rootfs_data -m
elif [ "$mode" = migrate ]; then
 "$tool" --probe-current "$guard"
 ubiattach -m 3 -d 0
 else
 ubiattach -m 3 -d 0
 fi
fi
set -- /sys/class/ubi/ubi0_*/name
[ "$#" = 1 ] && [ "$(cat "$1")" = rootfs_data ]
mkdir -p /tmp/dpn-first-config
if [ "$mode" = finish ] && grep -q '^ubi0:rootfs_data /tmp/dpn-first-config ubifs ' /proc/mounts; then
 :
else
 mount -t ubifs ubi0:rootfs_data "$cfg"
fi
if [ "$mode" = rollback ]; then
 [ "$(cat "$cfg/dpn-upgrade-next/.dpn-first-prepared")" = "$(cat /tmp/dpn-session)" ]
 [ ! -e "$cfg/dpn-upgrade-old-upper" ]
 if [ -e "$cfg/dpn-upgrade.pending" ]; then
  [ "$(cat "$cfg/dpn-upgrade.pending")" = v1 ]
  rm "$cfg/dpn-upgrade.pending"
 fi
 rm -rf "$cfg/dpn-upgrade-next"
elif [ "$mode" = finish ]; then
 [ "$(cat "$cfg/dpn-upgrade-next/.dpn-first-prepared")" = "$(cat /tmp/dpn-session)" ]
 [ ! -e "$cfg/dpn-upgrade.pending" ]
 if [ -d "$cfg/upper" ]; then
  for file in etc/config/network etc/config/wireless etc/config/dhcp etc/config/dropbear etc/config/system etc/shadow etc/dropbear/authorized_keys etc/dropbear/dropbear_ed25519_host_key etc/uhttpd.crt etc/uhttpd.key; do
   [ ! -f "$cfg/upper/$file" ] || cmp "$cfg/upper/$file" "$cfg/dpn-upgrade-next/upper/$file"
  done
 fi
 dropbearkey -y -f "$cfg/dpn-upgrade-next/upper/etc/dropbear/dropbear_ed25519_host_key"
elif [ "$mode" = commit ]; then
 [ "$(cat "$cfg/dpn-upgrade-next/.dpn-first-prepared")" = "$(cat /tmp/dpn-session)" ]
 [ ! -e "$cfg/dpn-upgrade.pending" ]
 printf 'v1\n' > "$cfg/dpn-upgrade.pending.new"
 sync
 mv "$cfg/dpn-upgrade.pending.new" "$cfg/dpn-upgrade.pending"
else
 [ ! -e "$cfg/dpn-upgrade.pending" ]
 [ ! -e "$cfg/dpn-upgrade-next" ]
 mkdir -p "$cfg/dpn-upgrade-next/upper"
 if [ "$mode" = migrate ]; then
  [ -d "$cfg/upper" ]
  archive="${guard%/*}/owner-upper.tar"
  (umask 077; /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -C "$cfg/upper" -cpf "$archive" .)
  /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -C "$cfg/dpn-upgrade-next/upper" -xpf "$archive"
  /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -C "$cfg/dpn-upgrade-next/upper" -dpf "$archive"
  legacy="$cfg/dpn-upgrade-next/upper/etc/init.d/dpn_ram_ready"
  if [ -e "$legacy" ]; then
   sum=$(sha256sum "$legacy")
   [ "${sum%% *}" = babeb66e75fc82dad9bf2985bcde39c220a2def5daa2191e063214d77a03724e ]
   rm "$legacy"
   for link in "$cfg/dpn-upgrade-next/upper"/etc/rc.d/*dpn_ram_ready; do
    [ ! -e "$link" ] && [ ! -L "$link" ] || { [ "$(readlink "$link")" = ../init.d/dpn_ram_ready ] && rm "$link"; }
   done
   file="$cfg/dpn-upgrade-next/upper/etc/sysupgrade.conf"
   [ ! -f "$file" ] || sed -i '\|^/etc/init.d/dpn_ram_ready$|d' "$file"
  fi
 else
  mkdir -p "$cfg/dpn-upgrade-next/upper/etc/dropbear"
  cp /etc/dpn-provision/authorized_keys "$cfg/dpn-upgrade-next/upper/etc/dropbear/authorized_keys"
  cp /etc/dpn-provision/host_ed25519_key "$cfg/dpn-upgrade-next/upper/etc/dropbear/dropbear_ed25519_host_key"
  chmod 700 "$cfg/dpn-upgrade-next/upper/etc/dropbear"
  chmod 600 "$cfg/dpn-upgrade-next/upper/etc/dropbear/"*
 fi
 test -s "$cfg/dpn-upgrade-next/upper/etc/dropbear/authorized_keys"
 test -s "$cfg/dpn-upgrade-next/upper/etc/dropbear/dropbear_ed25519_host_key"
 cat /tmp/dpn-session > "$cfg/dpn-upgrade-next/.dpn-first-prepared"
 dropbearkey -y -f "$cfg/dpn-upgrade-next/upper/etc/dropbear/dropbear_ed25519_host_key"
fi
sync
umount "$cfg"
ubidetach -m 3
printf 'DPN_FIRST_CONFIG_%s_COMPLETE\n' "$mode"
