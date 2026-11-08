# SPDX-License-Identifier: GPL-2.0-only
# Bundle contents are generic; each target supplies its own factory wrapper.
# Refuse before programming if a normal upgrade would lose key-only recovery.
dpn_owner_recovery_keys_ready() {
 local dir="${1:-/etc/dropbear}"
 [ -f "$dir/authorized_keys" ] && [ ! -L "$dir/authorized_keys" ] && [ -s "$dir/authorized_keys" ] || return 1
 [ -f "$dir/dropbear_ed25519_host_key" ] && [ ! -L "$dir/dropbear_ed25519_host_key" ] && [ -s "$dir/dropbear_ed25519_host_key" ] || return 1
 grep -Ev '^[[:space:]]*(#|$)' "$dir/authorized_keys" | grep -Eq '(^|[[:space:]])(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))[[:space:]]+[A-Za-z0-9+/=]+([[:space:]]|$)' || return 1
 dropbearkey -y -f "$dir/dropbear_ed25519_host_key" >/dev/null 2>&1
}
dpn_owner_backup_ready() {
 local archive="$1" dir="${2:-/etc/dropbear}" tar_bin="${3:-/usr/libexec/tar-gnu}" file check rc=0
 check=$(mktemp /tmp/dpn-owner-backup.XXXXXX) || return 1
 chmod 600 "$check" || { rm -f "$check"; return 1; }
 for file in authorized_keys dropbear_ed25519_host_key; do
  "$tar_bin" --warning=no-timestamp -xOzf "$archive" "etc/dropbear/$file" > "$check" 2>/dev/null && cmp -s "$check" "$dir/$file" || { rc=1; break; }
 done
 rm -f "$check"
 return "$rc"
}
dpn_generic_extract() {
 local names control
 names=$(/usr/libexec/tar-gnu -tf "$1") || return 1
 [ "$names" = "$(printf 'sysupgrade-dpn-be7200gr/CONTROL\nsysupgrade-dpn-be7200gr/kernel')" ] || return 1
 control=$(/usr/libexec/tar-gnu -xOf "$1" sysupgrade-dpn-be7200gr/CONTROL) || return 1
 [ "$control" = "$(printf 'BOARD=dlink_dpn-be7200gr\nDPN_UPGRADE_LAYOUT=3\nPAYLOAD=generic-fit')" ] || return 1
 /usr/libexec/tar-gnu -xOf "$1" sysupgrade-dpn-be7200gr/kernel > "$2" || return 1
 /usr/libexec/dpn-install --check-fit "$2"
}
dpn_generic_check_bundle() {
 local file rc
 file=$(mktemp /tmp/dpn-fit.XXXXXX) || return 1
 dpn_generic_extract "$1" "$file"; rc=$?
 rm -f "$file"
 return "$rc"
}
dpn_generic_abort() {
 printf "%s\n" "$*" > /tmp/dpn-upgrade-abort-reason
 echo "DPN_GENERIC_UPGRADE_ABORT: $*; staying in RAM" > /dev/console
 mkdir -p /root /var/run
 /usr/sbin/dropbear -P /tmp/dpn-upgrade-dropbear.pid -E -s -g -r /etc/dropbear/dropbear_ed25519_host_key 2>/tmp/dpn-upgrade-dropbear.log
 # The standard upgraded PID 1 continues servicing the watchdog.
 while :; do sleep 60; done
}
dpn_generic_nodes() {
 local i dev
 for i in 2 3; do
  dev=$(cat /sys/class/mtd/mtd$i/dev) || return 1
  [ "$dev" = "90:$((i*2))" ] || return 1
  if [ ! -c /dev/mtd$i ]; then mknod /dev/mtd$i c 90 "$((i*2))" || return 1; fi
  chmod 600 /dev/mtd$i || return 1
 done
}
dpn_generic_upgrade() {
 local recovery_upper update_slot firmware_block fit=/tmp/dpn-upgrade.itb fip=/tmp/dpn-upgrade.fip guard=/tmp/dpn-target-guard.bin
 [ -n "$UPGRADE_BACKUP" ] && [ -f "$UPGRADE_BACKUP" ] || dpn_generic_abort missing-owner-configuration
 dpn_owner_recovery_keys_ready || dpn_generic_abort missing-owner-recovery-key
 dpn_owner_backup_ready "$UPGRADE_BACKUP" || dpn_generic_abort owner-keys-not-preserved-in-backup
 dpn_generic_extract "$1" "$fit" || dpn_generic_abort invalid-bundle
 if [ -f /etc/dpn-network-recovery ]; then
  [ "$(cat /sys/module/dpn_storage/parameters/config_readonly)" = Y ] || dpn_generic_abort recovery-config-not-readonly
  [ "$(cat /sys/class/ubi/ubi0/ro_mode)" = 1 ] || dpn_generic_abort recovery-ubi-not-readonly
  mkdir -m 700 /tmp/dpn-recovery-owner || dpn_generic_abort recovery-backup-directory
  mkdir /tmp/dpn-recovery-owner/source || dpn_generic_abort recovery-source-directory
  mount -t ubifs -o ro ubi0:rootfs_data /tmp/dpn-recovery-owner/source || dpn_generic_abort recovery-source-mount
  recovery_upper=$(cat /etc/dpn-recovery-upper)
  case "$recovery_upper" in upper|dpn-upgrade-old-upper) ;; *) dpn_generic_abort recovery-upper-name;; esac
  [ -d "/tmp/dpn-recovery-owner/source/$recovery_upper" ] && [ ! -L "/tmp/dpn-recovery-owner/source/$recovery_upper" ] || dpn_generic_abort recovery-upper-missing
  (umask 077; /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -C "/tmp/dpn-recovery-owner/source/$recovery_upper" -cpf /tmp/dpn-recovery-owner/upper.tar .) || dpn_generic_abort recovery-upper-backup
  /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -C "/tmp/dpn-recovery-owner/source/$recovery_upper" -dpf /tmp/dpn-recovery-owner/upper.tar || dpn_generic_abort recovery-upper-backup-verify
  umount /tmp/dpn-recovery-owner/source || dpn_generic_abort recovery-source-unmount
 fi
 update_slot=$(cat /sys/module/dpn_storage/parameters/root_slot 2>/dev/null) || dpn_generic_abort update-slot-unavailable
 case "$update_slot" in 0) firmware_block=2;; 1) firmware_block=202;; *) dpn_generic_abort update-slot-invalid;; esac
 ubidetach -m 3 || dpn_generic_abort config-still-busy
 rmmod dpn_storage || dpn_generic_abort storage-still-busy
 insmod /lib/modules/6.18.60/dpn_storage.ko install=1 root_slot="$update_slot" || dpn_generic_abort installer-view-refused
 dpn_generic_nodes || dpn_generic_abort mtd-nodes
 /usr/libexec/dpn-install --snapshot "$guard" || dpn_generic_abort guard-snapshot
 dd if=/dev/mtd0 of=/tmp/dpn-previous-prefix.bin bs=262144 skip="$firmware_block" count=72 2>/dev/null || dpn_generic_abort previous-prefix-backup
 chmod 600 /tmp/dpn-previous-prefix.bin
 /usr/libexec/dpn-install --check-restore /tmp/dpn-previous-prefix.bin "$guard" || dpn_generic_abort previous-prefix-verification
 /usr/libexec/dpn-install --assemble-fit "$fit" "$guard" "$fip" || dpn_generic_abort target-wrapper
 /usr/libexec/dpn-install --write "$fip" "$guard" || dpn_generic_abort firmware-write
 ubiattach -m 3 -d 0 || dpn_generic_abort config-reattach
 mkdir -p /tmp/dpn-config-stage
 mount -t ubifs ubi0:rootfs_data /tmp/dpn-config-stage || dpn_generic_abort config-mount
 if [ -f /etc/dpn-network-recovery ]; then
  for name in upper dpn-upgrade-old-upper dpn-upgrade-next dpn-upgrade.pending; do
   [ ! -L "/tmp/dpn-config-stage/$name" ] || dpn_generic_abort recovery-transaction-symlink
  done
  /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -C "/tmp/dpn-config-stage/$recovery_upper" -dpf /tmp/dpn-recovery-owner/upper.tar || dpn_generic_abort recovery-source-changed
  if [ -e /tmp/dpn-config-stage/dpn-upgrade.pending ]; then
   [ "$(cat /tmp/dpn-config-stage/dpn-upgrade.pending)" = v1 ] || dpn_generic_abort recovery-unknown-transaction
  else
   [ ! -e /tmp/dpn-config-stage/dpn-upgrade-next ] && [ ! -e /tmp/dpn-config-stage/dpn-upgrade-old-upper ] || dpn_generic_abort recovery-unexplained-staging
  fi
  [ ! -e /tmp/dpn-config-stage/dpn-recovery-obsolete-upper ] || dpn_generic_abort recovery-obsolete-directory-exists
  if [ "$recovery_upper" = dpn-upgrade-old-upper ]; then
   if [ -e /tmp/dpn-config-stage/upper ]; then
    mv /tmp/dpn-config-stage/upper /tmp/dpn-config-stage/dpn-recovery-obsolete-upper || dpn_generic_abort recovery-preserve-incomplete-upper
   fi
   mv /tmp/dpn-config-stage/dpn-upgrade-old-upper /tmp/dpn-config-stage/upper || dpn_generic_abort recovery-restore-old-upper
  fi
  # The selected intact upper remains in place while the new copy is prepared.
  rm -rf /tmp/dpn-config-stage/dpn-upgrade-next || dpn_generic_abort recovery-remove-incomplete-staging
  rm -f /tmp/dpn-config-stage/dpn-upgrade.pending || dpn_generic_abort recovery-remove-old-marker
  sync
  rm -rf /tmp/dpn-config-stage/dpn-recovery-obsolete-upper || dpn_generic_abort recovery-obsolete-cleanup
 fi
 [ ! -e /tmp/dpn-config-stage/dpn-upgrade.pending ] || dpn_generic_abort config-already-pending
 [ ! -e /tmp/dpn-config-stage/dpn-upgrade-next ] || dpn_generic_abort config-already-staged
 mkdir -p /tmp/dpn-config-stage/dpn-upgrade-next/upper || dpn_generic_abort config-staging
 if [ -f /etc/dpn-network-recovery ]; then
  /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -xpf /tmp/dpn-recovery-owner/upper.tar -C /tmp/dpn-config-stage/dpn-upgrade-next/upper || dpn_generic_abort recovery-config-restore
  /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' --numeric-owner -C /tmp/dpn-config-stage/dpn-upgrade-next/upper -dpf /tmp/dpn-recovery-owner/upper.tar || dpn_generic_abort recovery-config-restore-verify
 else
  /usr/libexec/tar-gnu --warning=no-timestamp --xattrs --xattrs-include='*' -xzf "$UPGRADE_BACKUP" -C /tmp/dpn-config-stage/dpn-upgrade-next/upper || dpn_generic_abort config-restore
 fi
 test -s /tmp/dpn-config-stage/dpn-upgrade-next/upper/etc/dropbear/authorized_keys || dpn_generic_abort owner-public-key-missing
 test -s /tmp/dpn-config-stage/dpn-upgrade-next/upper/etc/dropbear/dropbear_ed25519_host_key || dpn_generic_abort owner-host-key-missing
 sync
 echo v1 > /tmp/dpn-config-stage/dpn-upgrade.pending
 sync
 umount /tmp/dpn-config-stage || dpn_generic_abort config-unmount
 ubidetach -m 3 || dpn_generic_abort config-detach
 echo DPN_GENERIC_SYSUPGRADE_COMPLETE > /dev/console
 sync
 echo b > /proc/sysrq-trigger
 dpn_generic_abort restart-returned
}
