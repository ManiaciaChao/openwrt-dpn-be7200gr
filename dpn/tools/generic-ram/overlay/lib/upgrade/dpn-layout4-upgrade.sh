# SPDX-License-Identifier: GPL-2.0-only
# Layout4: unchanged original bootloader and independent REC16/VLT4.
dpn_l4_extract() {
 local image="$1" dir="$2" names control
 names=$(/usr/libexec/tar-gnu -tf "$image") || return 1
 [ "$names" = "$(printf 'sysupgrade-dpn-be7200gr/CONTROL\nsysupgrade-dpn-be7200gr/kernel\nsysupgrade-dpn-be7200gr/root')" ] || return 1
 control=$(/usr/libexec/tar-gnu -xOf "$image" sysupgrade-dpn-be7200gr/CONTROL) || return 1
 [ "$control" = "$(printf 'BOARD=dlink_dpn-be7200gr\nDPN_UPGRADE_LAYOUT=4\nPAYLOAD=thin-fip-and-ubi-root')" ] || return 1
 /usr/libexec/tar-gnu -xOf "$image" sysupgrade-dpn-be7200gr/kernel > "$dir/kernel" || return 1
 /usr/libexec/tar-gnu -xOf "$image" sysupgrade-dpn-be7200gr/root > "$dir/root" || return 1
 /usr/libexec/dpn-image4-check "$dir/kernel" "$dir/root" normal
}
dpn_l4_check_bundle() {
 local dir rc
 dir=$(mktemp -d /tmp/dpn-l4-check.XXXXXX) || return 1
 dpn_l4_extract "$1" "$dir"; rc=$?
 rm -rf "$dir"
 return "$rc"
}
dpn_l4_reload() {
 [ ! -e /sys/class/ubi/ubi0 ] || return 1
 if [ -e /sys/module/dpn_layout4_storage ]; then rmmod dpn_layout4_storage || return 1; fi
 insmod /lib/modules/6.18.60/dpn_layout4_storage.ko "$@"
}
dpn_l4_select() {
 dpn_l4_reload flag_write=1 || return 1
 /usr/libexec/dpn-bootflag-select "$1" /dev/mtd4 /dev/mtd0 "$DPN_L4_ART_SHA"
}
# Upper becomes the merged filesystem root: it must remain traversable by
# unprivileged services. A private staging umask must not leak into it or into
# tar-created implicit /etc parent directories. Archive file modes are retained.
dpn_l4_restore_config() {
 local backup="$1" data="$2"
 mkdir -m 755 "$data/upper" || return 1
 mkdir -m 700 "$data/work" || return 1
 (umask 022; /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' -xzf "$backup" -C "$data/upper") || return 1
 /usr/libexec/tar-gnu --warning=no-timestamp -dzf "$backup" -C "$data/upper" || return 1
 ln -s 2 "$data/.fs_state"
}
# Explicit RAM-only installer shared by migration and standard sysupgrade.
# No implicit first-boot format and no bootloader/vault write permissions.
dpn_l4_install() {
 local fip="$1" root="$2" backup="$3" work="$4" rootsha recsha size pad count path
 [ -f "$backup" ] && [ ! -L "$backup" ] || return 1
 [ ! -e /sys/class/ubi/ubi0 ] || return 1
 ! grep -Eq ' (squashfs|ubifs|overlay) ' /proc/mounts || return 1
 /usr/libexec/dpn-image4-check "$fip" "$root" normal || return 1
 dpn_l4_reload || return 1
 /usr/libexec/dpn-vault-check --check /dev/mtd3ro /sys/bus/nvmem/devices/dpn-art/nvmem || return 1
 dd if=/dev/mtd0 of="$work/ART" bs=262144 skip=1778 count=14 2>/dev/null || return 1
 printf 0 | dd of="$work/ART" bs=1 seek=3407872 conv=notrunc 2>/dev/null || return 1
 DPN_L4_ART_SHA=$(sha256sum "$work/ART");DPN_L4_ART_SHA=${DPN_L4_ART_SHA%% *}
 recsha=$(sha256sum /dev/mtd2ro);recsha=${recsha%% *}
 # Fully validate the independent recovery image before selecting it.
 dd if=/dev/mtd2ro of="$work/recovery16" bs=262144 count=64 2>/dev/null || return 1
 /usr/libexec/dpn-image4-check "$work/recovery16" - recovery || return 1
 rm -f "$work/recovery16" "$work/ART"
 # Config backup is produced by sysupgrade, never includes lower image code.
 /usr/libexec/tar-gnu -tzf "$backup" > "$work/config-list" || return 1
 while IFS= read -r path; do
  case "$path" in etc/*) ;; *) return 1;; esac
  case "/$path/" in */../*|*/./*) return 1;; esac
  case "$path" in etc/dpn-upgrade-layout|etc/dpn-build-id) return 1;; esac
 done < "$work/config-list"
 for path in authorized_keys dropbear_ed25519_host_key; do
  /usr/libexec/tar-gnu -xOzf "$backup" "etc/dropbear/$path" > "$work/$path" || return 1
  [ -s "$work/$path" ] || return 1
 done
 dropbearkey -y -f "$work/dropbear_ed25519_host_key" >/dev/null 2>&1 || return 1
 dpn_l4_select 1 || return 1
 echo LAYOUT4_RECOVERY_SELECTED_BEFORE_DATA_REBUILD
 dpn_l4_reload data_write=1 || return 1
 [ "$(cat /sys/class/mtd/mtd8/name)" = dpn-layout4-data ] && [ "$(cat /sys/class/mtd/mtd8/size)" = 427819008 ] || return 1
 ubiformat /dev/mtd8 -y || return 1
 ubiattach -m 8 -d 0 || return 1
 size=$(wc -c < "$root") || return 1
 ubimkvol /dev/ubi0 -n 0 -N rootfs -t static -s "$size" || return 1
 ubiupdatevol /dev/ubi0_0 "$root" || return 1
 rootsha=$(sha256sum "$root");rootsha=${rootsha%% *}
 [ "$(sha256sum /dev/ubi0_0 | cut -d ' ' -f 1)" = "$rootsha" ] || return 1
 ubimkvol /dev/ubi0 -n 1 -N rootfs_data -t dynamic -m || return 1
 mkdir "$work/data" || return 1
 mount -t ubifs ubi0:rootfs_data "$work/data" || return 1
 dpn_l4_restore_config "$backup" "$work/data" || return 1
 sync
 umount "$work/data" || return 1
 if [ -e /dev/ubiblock0_0 ]; then ubiblock --remove /dev/ubi0_0 || return 1; fi
 ubidetach -d 0 || return 1
 echo LAYOUT4_UBI_STATIC_ROOT_AND_STANDARD_CONFIGURATION_READBACK_VERIFIED
 dpn_l4_reload update=1 || return 1
 # Pad to a complete bounded target. No old slot tail enters the image.
 size=$(wc -c < "$fip");[ "$size" -le 16777216 ] || return 1
 pad=$((16777216-size));cp "$fip" "$work/normal16" || return 1
 if [ "$pad" -gt 0 ]; then
  # BusyBox tr is copied by the platform RAMFS list.
  dd if=/dev/zero bs=1 count="$pad" 2>/dev/null | tr '\000' '\377' >> "$work/normal16" || return 1
 fi
 size=$(wc -c < "$work/normal16");[ "$size" = 16777216 ] || return 1
 size=$(sha256sum "$work/normal16");size=${size%% *}
 /usr/libexec/dpn-normal16-write --snapshot "$work/normal16" "$root" "$size" "$recsha" "$work/guard" || return 1
 /usr/libexec/dpn-normal16-write --write "$work/normal16" "$root" "$size" "$recsha" "$work/guard" || return 1
 dpn_l4_select 0 || return 1
 dpn_l4_reload || return 1
 echo LAYOUT4_MAIN_COMMITTED_RECOVERY_VAULT_BOOTLOADER_PRESERVED
}
dpn_l4_upgrade() {
 local dir
 [ -n "$UPGRADE_BACKUP" ] && [ -f "$UPGRADE_BACKUP" ] || dpn_generic_abort missing-standard-config-backup
 dpn_owner_recovery_keys_ready || dpn_generic_abort missing-owner-keys
 dpn_owner_backup_ready "$UPGRADE_BACKUP" || dpn_generic_abort keys-not-in-backup
 dir=$(mktemp -d /tmp/dpn-l4-upgrade.XXXXXX) || dpn_generic_abort staging
 dpn_l4_extract "$1" "$dir" || dpn_generic_abort invalid-layout4-image
 if [ -e /dev/ubiblock0_0 ]; then ubiblock --remove /dev/ubi0_0 || dpn_generic_abort root-block-busy; fi
 ubidetach -d 0 || dpn_generic_abort data-still-busy
 dpn_l4_install "$dir/kernel" "$dir/root" "$UPGRADE_BACKUP" "$dir" || dpn_generic_abort layout4-install-refused-recovery-retained
 sync
 echo b > /proc/sysrq-trigger
 dpn_generic_abort restart-returned
}
