# SPDX-License-Identifier: GPL-2.0-only
# Original bootloader, generic FIT payload, per-target FIP wrapper, layout 3.
REQUIRE_IMAGE_METADATA=1
RAMFS_COPY_BIN='dropbearkey /usr/libexec/tar-gnu sha256sum cmp mktemp insmod rmmod dropbear ubiattach ubidetach /usr/libexec/dpn-install'
RAMFS_COPY_DATA='/etc/passwd /etc/shadow /etc/group /etc/shells /etc/dropbear/authorized_keys /etc/dropbear/dropbear_ed25519_host_key /lib/modules/6.18.60/dpn_storage.ko /lib/upgrade/dpn-generic-upgrade.sh'
[ ! -f /etc/dpn-network-recovery ] || RAMFS_COPY_DATA="$RAMFS_COPY_DATA /etc/dpn-network-recovery /etc/dpn-recovery-upper"
. /lib/upgrade/dpn-generic-upgrade.sh
. /lib/upgrade/dpn-layout4-upgrade.sh
if [ -d /sys/firmware/devicetree/base/dpn-layout4 ]; then
 RAMFS_COPY_BIN="$RAMFS_COPY_BIN tr readlink ln /usr/libexec/dpn-image4-check /usr/libexec/dpn-normal16-write /usr/libexec/dpn-bootflag-select /usr/libexec/dpn-vault-check"
 RAMFS_COPY_DATA="$RAMFS_COPY_DATA /lib/modules/6.18.60/dpn_layout4_storage.ko /lib/upgrade/dpn-layout4-upgrade.sh /lib/upgrade/dpn-layout4-enter-recovery"
fi
platform_check_image() {
 if [ -f /etc/dpn-factory-installer ]; then
  echo 'Finish the backed-up first installation before using sysupgrade.' >&2
  return 1
 fi
 if [ -d /sys/firmware/devicetree/base/dpn-layout4 ]; then
  [ "$#" = 1 ] && [ "$(board_name)" = dlink,dpn-be7200gr ] && [ "${SAVE_CONFIG:-1}" != 0 ] || return 1
  dpn_owner_recovery_keys_ready || return 1
  dpn_l4_check_bundle "$1"
  return $?
 fi
 # Kernel and native writer independently bind updates to this running slot.
 if [ -e /sys/firmware/devicetree/base/dpn-flash-layout/slot-relative-root ]; then
  . /lib/upgrade/dpn-boot-slot.sh
  [ "$(dpn_boot_slot "$(cat /proc/cmdline)")" = "$(cat /sys/module/dpn_storage/parameters/root_slot)" ] || return 1
 fi
 [ "$#" = 1 ] && [ "$(board_name)" = dlink,dpn-be7200gr ] || return 1
 [ -e /sys/firmware/devicetree/base/dpn-flash-layout/persistent-root ] || return 1
 # A reset needs a separate owner provisioning flow; do not strand a key-only
 # installation by accepting sysupgrade -n with no credentials to restore.
 [ "${SAVE_CONFIG:-1}" != 0 ] || return 1
 dpn_owner_recovery_keys_ready || {
  echo 'Add your SSH public key in LuCI System > Administration before upgrading; wired recovery requires an owner key.' >&2
  return 1
 }
 dpn_generic_check_bundle "$1"
}
platform_do_upgrade() {
 if [ -d /sys/firmware/devicetree/base/dpn-layout4 ]; then dpn_l4_upgrade "$1"; return $?; fi
 dpn_generic_upgrade "$1"
}
