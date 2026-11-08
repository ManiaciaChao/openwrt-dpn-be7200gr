# SPDX-License-Identifier: GPL-2.0-only
# The factory package boots its installer in RAM. No configuration bank is
# attached or formatted here. Persistence is an explicit later transaction.
dpn_factory_ram_boot() {
 local node=/sys/firmware/devicetree/base/dpn-layout4 slot expected
 [ "$(tr -d '\000' < "$node/write-profile")" = provision ] || return 1
 [ -e "$node/factory-first-install" ] || return 1
 [ ! -e /sys/class/ubi/ubi0 ] && [ ! -e /sys/module/dpn_storage ] || return 1
 . /lib/upgrade/dpn-boot-slot.sh
 slot=$(dpn_boot_slot "$(cat /proc/cmdline)") || return 1
 expected=$(hexdump -v -e '1/1 "%02x"' "$node/installer-rootfs-sha256") || return 1
 [ "${#expected}" = 64 ] || return 1
 /usr/libexec/dpn-factory-read /dev/mtd0 "$slot" "$expected" /tmp/dpn-installer.squashfs || return 1
 mkdir -p /factory-rom /newroot || return 1
 mount -t squashfs -o ro,loop /tmp/dpn-installer.squashfs /factory-rom || return 1
 mount -t tmpfs -o mode=755 tmpfs /newroot || return 1
 cp -a /factory-rom/. /newroot/ || return 1
 umount /factory-rom || return 1
 # The pinned BusyBox mount creates AUTOCLEAR loop devices. Unmounting releases
 # this mapping; no losetup applet (or global loop-device detach) is required.
 rm /tmp/dpn-installer.squashfs || return 1
 [ -f /newroot/etc/dpn-factory-installer ] || return 1
 mount --move /dev /newroot/dev || return 1
 mount --move /sys /newroot/sys || return 1
 mount --move /proc /newroot/proc || return 1
 export INITRAMFS=1
 echo DPN_FACTORY_RAM_INSTALLER_NO_FLASH_MUTATIONS
 dpn_watchdog_handoff
 exec switch_root /newroot /sbin/init
}
