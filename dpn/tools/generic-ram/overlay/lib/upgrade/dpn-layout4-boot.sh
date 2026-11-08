# SPDX-License-Identifier: GPL-2.0-only
# No implicit formatting. A corrupt/missing UBI root must enter vault recovery.
dpn_layout4_normal_boot() {
 local node=/sys/firmware/devicetree/base/dpn-layout4 expected actual
 [ "$(tr -d '\000' < "$node/write-profile")" = normal ] || return 1
 [ ! -e /sys/class/mtd/mtd2 ] || return 1
 expected=$(hexdump -v -e '1/1 "%02x"' "$node/rootfs-sha256") || return 1
 [ "${#expected}" = 64 ] || return 1
 # Validate static volume bytes before opening the data view for writes.
 insmod /lib/modules/6.18.60/dpn_layout4_storage.ko || return 1
 [ "$(cat /sys/class/mtd/mtd8/name)" = dpn-layout4-data ] || return 1
 [ "$(cat /sys/class/mtd/mtd8/size)" = 427819008 ] || return 1
 ubiattach -m 8 -d 0 || return 1
 [ "$(cat /sys/class/ubi/ubi0_0/name)" = rootfs ] || return 1
 [ "$(cat /sys/class/ubi/ubi0_0/type)" = static ] || return 1
 [ "$(cat /sys/class/ubi/ubi0_1/name)" = rootfs_data ] || return 1
 [ "$(cat /sys/class/ubi/ubi0_1/type)" = dynamic ] || return 1
 actual=$(sha256sum /dev/ubi0_0) || return 1
 [ "${actual%% *}" = "$expected" ] || return 1
 if [ -e /sys/class/block/ubiblock0_0 ]; then ubiblock --remove /dev/ubi0_0 || return 1; fi
 ubidetach -d 0 || return 1
 rmmod dpn_layout4_storage || return 1
 insmod /lib/modules/6.18.60/dpn_layout4_storage.ko data_write=1 || return 1
 ubiattach -m 8 -d 0 || return 1
 actual=$(sha256sum /dev/ubi0_0) || return 1
 [ "${actual%% *}" = "$expected" ] || return 1
 if [ ! -e /sys/class/block/ubiblock0_0 ]; then ubiblock --create /dev/ubi0_0 || return 1; fi
 [ -b /dev/ubiblock0_0 ] || return 1
 mkdir -p /newroot /config-stage || return 1
 mount -t squashfs -o ro /dev/ubiblock0_0 /newroot || return 1
 mount -t ubifs ubi0:rootfs_data /config-stage || return 1
 # A physical reset stages defaults on the existing data volume. Finish its
 # directory transaction before mounting overlay, without formatting UBI.
 . /lib/upgrade/dpn-config-commit.sh
 dpn_config_commit /config-stage || return 1
 # Configuration must already have been committed by the migration installer.
 [ -d /config-stage/upper ] && [ -d /config-stage/work ] || return 1
 [ "$(readlink /config-stage/.fs_state)" = 2 ] || return 1
 umount /config-stage || return 1
 unset INITRAMFS
 mount --move /dev /newroot/dev || return 1
 mount --move /sys /newroot/sys || return 1
 mount --move /proc /newroot/proc || return 1
 echo DPN_LAYOUT4_SWITCH_TO_UBI_SQUASHFS_STANDARD_OVERLAY
 dpn_watchdog_handoff
 exec switch_root /newroot /sbin/init
}

dpn_layout4_failure_cleanup() {
 # Never layer rescue over an active main UBI. Failure here stays at console.
 grep -q ' /config-stage ' /proc/mounts && umount /config-stage
 grep -q ' /newroot ' /proc/mounts && umount /newroot
 if [ -e /dev/ubiblock0_0 ]; then ubiblock --remove /dev/ubi0_0 || return 1; fi
 if [ -e /sys/class/ubi/ubi0 ]; then ubidetach -d 0 || return 1; fi
 if [ -e /sys/module/dpn_layout4_storage ]; then rmmod dpn_layout4_storage || return 1; fi
 return 0
}
