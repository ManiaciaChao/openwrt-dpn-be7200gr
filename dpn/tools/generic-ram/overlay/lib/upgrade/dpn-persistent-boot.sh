# SPDX-License-Identifier: GPL-2.0-only
# Called by PID 1. Existing data is preserved; first boot formats only ALL-FF.
dpn_persistent_boot() {
 slot=0
 module_args=
 if [ -e /sys/firmware/devicetree/base/dpn-flash-layout/slot-relative-root ]; then
  . /lib/upgrade/dpn-boot-slot.sh
  slot=$(dpn_boot_slot "$(cat /proc/cmdline)") || return 1
  module_args="root_slot=$slot"
 fi
 first_boot=0
 if [ -e /sys/firmware/devicetree/base/dpn-flash-layout/factory-first-boot ]; then first_boot=1; fi
 if [ "$first_boot" = 1 ]; then
  insmod /lib/modules/6.18.60/dpn_storage.ko $module_args config_readonly=1 || return 1
 else
  insmod /lib/modules/6.18.60/dpn_storage.ko $module_args || return 1
 fi
 echo "$slot" > /tmp/dpn-boot-slot
 if [ -e /sys/firmware/devicetree/base/dpn-flash-layout/network-recovery-self-test ]; then
  echo DPN_RECOVERY_SELF_TEST_ROOT_UNAVAILABLE
  return 1
 fi
 [ "$(cat /sys/class/mtd/mtd2/name)" = dpn-rootfs ] || return 1
 [ "$(cat /sys/class/mtd/mtd3/name)" = dpn-config ] || return 1
 expected=$(hexdump -v -e '1/1 "%02x"' /sys/firmware/devicetree/base/dpn-flash-layout/rootfs-sha256) || return 1
 mkdir -p /newroot /config-stage || return 1
 # Hash validation precedes any configuration initialization.
 if [ -e /sys/firmware/devicetree/base/dpn-flash-layout/ram-root ]; then
  actual=$(sha256sum /initrd.image) || return 1
 else
  actual=$(sha256sum /dev/mtd2ro) || return 1
 fi
 [ "${#expected}" -eq 64 ] && [ "${actual%% *}" = "$expected" ] || return 1
 if [ "$first_boot" = 1 ]; then
  . /lib/upgrade/dpn-first-boot.sh
  dpn_prepare_configuration || return 1
 fi
 if [ -e /sys/firmware/devicetree/base/dpn-flash-layout/ram-root ]; then
  actual=$(sha256sum /initrd.image) || return 1
  [ "${#expected}" -eq 64 ] && [ "${actual%% *}" = "$expected" ] || return 1
  mount -t squashfs -o loop,ro /initrd.image /newroot || return 1
 else
  actual=$(sha256sum /dev/mtd2ro) || return 1
  [ "${#expected}" -eq 64 ] && [ "${actual%% *}" = "$expected" ] || return 1
  mount -t squashfs -o ro /dev/mtdblock2 /newroot || return 1
 fi
 if [ "$first_boot" != 1 ]; then
  ubiattach -m 3 -d 0 || return 1
  DPN_FIRST_BOOT_VOLUME=rootfs_data
 fi
 mount -t ubifs "ubi0:$DPN_FIRST_BOOT_VOLUME" /config-stage || return 1
 if [ "$first_boot" = 1 ] && [ "$DPN_FIRST_BOOT_NEW" != 0 ]; then
  if [ ! -e /config-stage/upper ]; then dpn_fresh_configuration /newroot /config-stage || return 1; fi
  [ -s /config-stage/upper/etc/dropbear/dropbear_ed25519_host_key ] || return 1
  dropbearkey -y -f /config-stage/upper/etc/dropbear/dropbear_ed25519_host_key >/dev/null || return 1
  umount /config-stage || return 1
  ubirename /dev/ubi0 dpn-first-setup rootfs_data || return 1
  mount -t ubifs ubi0:rootfs_data /config-stage || return 1
 fi
 . /lib/upgrade/dpn-config-commit.sh
 dpn_config_commit /config-stage || return 1
 umount /config-stage || return 1
 unset INITRAMFS
 mount --move /dev /newroot/dev || return 1
 mount --move /sys /newroot/sys || return 1
 mount --move /proc /newroot/proc || return 1
 echo DPN_GENERIC_SWITCH_TO_SQUASHFS
 dpn_watchdog_handoff
 exec switch_root /newroot /sbin/init
}
