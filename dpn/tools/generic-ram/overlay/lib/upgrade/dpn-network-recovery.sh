# SPDX-License-Identifier: GPL-2.0-only
# Runs in early RAM only, before a persistent root was mounted. No format/write,
# password fallback, public shared key, ART update or factory-slot operation.
dpn_network_recovery() {
 local flags file path upper
 [ "$(cat /sys/class/mtd/mtd2/name)" = dpn-rootfs ] || return 1
 [ "$(cat /sys/class/mtd/mtd3/name)" = dpn-config ] || return 1
 # If a later persistent-boot step attached UBI, stop instead of reinterpreting it.
 [ ! -e /sys/class/ubi/ubi0 ] || return 1
 grep -q ' /newroot ' /proc/mounts && return 1
 rmmod dpn_storage || return 1
 insmod /lib/modules/6.18.60/dpn_storage.ko root_slot="$slot" config_readonly=1 || return 1
 flags=$(cat /sys/class/mtd/mtd3/flags) || return 1
 [ "$((flags & 1024))" = 0 ] || return 1
 ubiattach -m 3 -d 0 || return 1
 [ "$(cat /sys/class/ubi/ubi0/ro_mode)" = 1 ] || return 1
 [ "$(cat /sys/class/ubi/ubi0_0/name)" = rootfs_data ] || return 1
 mkdir -p /recover-config || return 1
 mount -t ubifs -o ro ubi0:rootfs_data /recover-config || return 1
 . /lib/upgrade/dpn-recovery-state.sh
 upper=$(dpn_recovery_upper /recover-config) || return 1
 path=/recover-config/$upper/etc
 echo "$upper" > /etc/dpn-recovery-upper
 [ -s "$path/dropbear/authorized_keys" ] && [ -s "$path/dropbear/dropbear_ed25519_host_key" ] || return 1
 [ ! -L "$path/dropbear/authorized_keys" ] && [ ! -L "$path/dropbear/dropbear_ed25519_host_key" ] || return 1
 [ -s "$path/config/network" ] && [ ! -L "$path/config/network" ] || return 1
 mkdir -p /etc/config /etc/dropbear || return 1
 # Copy configuration files only, never executable overrides or startup scripts.
 for file in "$path"/config/*; do
  [ -f "$file" ] && [ ! -L "$file" ] || continue
  cp "$file" "/etc/config/${file##*/}" || return 1
 done
 for file in passwd shadow group shells uhttpd.crt uhttpd.key; do
  [ ! -f "$path/$file" ] || { [ ! -L "$path/$file" ] && cp "$path/$file" "/etc/$file"; } || return 1
 done
 cp "$path/dropbear/authorized_keys" /etc/dropbear/authorized_keys || return 1
 cp "$path/dropbear/dropbear_ed25519_host_key" /etc/dropbear/dropbear_ed25519_host_key || return 1
 chmod 700 /etc/dropbear
 chmod 600 /etc/dropbear/*
 dropbearkey -y -f /etc/dropbear/dropbear_ed25519_host_key >/dev/null || return 1
 # Leave the owner's config byte-identical. A separate recovery-only service
 # forces public-key authentication without rewriting the saved configuration.
 for file in /etc/rc.d/*dropbear; do
  [ ! -e "$file" ] && [ ! -L "$file" ] || rm "$file" || return 1
 done
 ln -s ../init.d/dpn_recovery_ssh /etc/rc.d/S89dpn_recovery_ssh || return 1
 . /lib/upgrade/dpn-recovery-firewall.sh
 dpn_recovery_bind_firewall || return 1
 # Recovery must not rerun package migrations against the RAM configuration.
 rm -f /etc/uci-defaults/* || return 1
 umount /recover-config || return 1
 echo ROOT_FILESYSTEM_UNAVAILABLE > /etc/dpn-network-recovery
 echo DPN_READONLY_WIRED_NETWORK_RECOVERY
 export INITRAMFS=1
 dpn_watchdog_handoff
 exec /sbin/init
}
