# SPDX-License-Identifier: GPL-2.0-only
# Automatic first installation. This file is sourced only by the explicit worker,
# never by sysupgrade's *.sh hook discovery (it defines functions, no actions).
dpn_auto_status() {
 printf '%s\n' "$1" > /tmp/dpn-factory-auto.status
 echo "DPN_FACTORY_AUTO_$1" > /dev/console
}
dpn_auto_preflight() {
 [ "$(cat /etc/dpn-factory-auto)" = automatic-v1 ] || return 1
 [ -f /etc/dpn-factory-installer ] || return 1
 [ -e /sys/firmware/devicetree/base/dpn-layout4/factory-first-install ] || return 1
 [ -e /sys/firmware/devicetree/base/dpn-layout4/factory-auto-install ] || return 1
 [ ! -e /sys/class/ubi/ubi0 ] && [ ! -e /sys/module/dpn_storage ] || return 1
 ! grep -Eq ' (squashfs|ubifs|overlay) ' /proc/mounts || return 1
 . /lib/upgrade/dpn-boot-slot.sh
 DPN_AUTO_SLOT=$(dpn_boot_slot "$(cat /proc/cmdline)") || return 1
 (cd /usr/share/dpn-install && sha256sum -c SHA256SUMS) || return 1
 /usr/libexec/dpn-image4-check /usr/share/dpn-install/normal.fip /usr/share/dpn-install/rootfs.squashfs normal || return 1
 /usr/libexec/dpn-image4-check /usr/share/dpn-install/recovery.fip - recovery || return 1
 # The kernel independently qualifies the NAND/BMT before exposing writes.
 dpn_l4_reload provision=1 || return 1
 dpn_l4_reload || return 1
}
dpn_auto_seed() {
 local work="$1" seed file
 seed=$work/seed
 mkdir -m 755 "$seed" "$seed/etc" "$seed/etc/config" || return 1
 mkdir -m 700 "$seed/etc/dropbear" "$seed/etc/dpn-recovery" || return 1
 for file in /etc/config/*; do
  [ -f "$file" ] && [ ! -L "$file" ] || continue
  cp "$file" "$seed/etc/config/" || return 1
 done
 for file in passwd group shells; do cp "/etc/$file" "$seed/etc/$file" || return 1; done
 # Standard direct-LAN OpenWrt initialization; no account is shared in images.
 sed 's/^root:[^:]*:/root::/' /etc/shadow > "$seed/etc/shadow" || return 1
 grep -q '^root::' "$seed/etc/shadow" || return 1
 chmod 600 "$seed/etc/shadow" || return 1
 dropbearkey -t ed25519 -f "$seed/etc/dropbear/dropbear_ed25519_host_key" >/dev/null 2>&1 || return 1
 dropbearkey -t ed25519 -f "$seed/etc/dpn-recovery/access.key" >/dev/null 2>&1 || return 1
 dropbearkey -y -f "$seed/etc/dpn-recovery/access.key" > "$work/recovery-public" || return 1
 grep '^ssh-ed25519 ' "$work/recovery-public" > "$seed/etc/dropbear/authorized_keys" || return 1
 chmod 600 "$seed/etc/dropbear/"* "$seed/etc/dpn-recovery/access.key" || return 1
 printf 'Per-device Dropbear recovery client key. Keep private. Export via LuCI configuration backup.\n' > "$seed/etc/dpn-recovery/README" || return 1
 if [ -f /etc/sysupgrade.conf ]; then cp /etc/sysupgrade.conf "$seed/etc/sysupgrade.conf" || return 1; fi
 printf '\n/etc/dpn-recovery/\n/etc/dpn-install-mode\n' >> "$seed/etc/sysupgrade.conf" || return 1
 printf 'automatic-v1; full original firmware backup is optional and must be made before flashing\n' > "$seed/etc/dpn-install-mode"
 /usr/libexec/tar-gnu --numeric-owner -czf "$work/config.tar.gz" -C "$seed" etc/config etc/dropbear etc/dpn-recovery etc/shadow etc/passwd etc/group etc/shells etc/sysupgrade.conf etc/dpn-install-mode || return 1
 /usr/libexec/tar-gnu -dzf "$work/config.tar.gz" -C "$seed" || return 1
}
dpn_auto_prepare() {
 local work="$1" seed
 seed=$work/seed
 /usr/libexec/dpn-vault-build --build /dev/mtd0 "$DPN_AUTO_SLOT" "$seed/etc/dropbear/authorized_keys" "$seed/etc/dropbear/dropbear_ed25519_host_key" "$work/vault" || return 1
 /usr/libexec/dpn-vault-check --check "$work/vault" /sys/bus/nvmem/devices/dpn-art/nvmem || return 1
 # Both the complete kernel and each unit's vault are in RAM before the OEM
 # installer slot can be overwritten. Public images never contain this vault.
 dd if=/dev/zero bs=262144 count=64 2>/dev/null | tr '\000' '\377' > "$work/recovery20" || return 1
 dd if=/usr/share/dpn-install/recovery.fip of="$work/recovery20" bs=262144 conv=notrunc 2>/dev/null || return 1
 cat "$work/vault" >> "$work/recovery20" || return 1
 [ "$(wc -c < "$work/recovery20")" = 20971520 ] || return 1
 DPN_AUTO_REC_SHA=$(sha256sum "$work/recovery20"); DPN_AUTO_REC_SHA=${DPN_AUTO_REC_SHA%% *}
}
dpn_auto_provision() {
 local work="$1"
 sh /lib/upgrade/dpn-factory-provision "$work/recovery20" "$DPN_AUTO_REC_SHA" || return 1
 [ -f /tmp/dpn-factory-provision.complete ] || return 1
 dd if=/dev/mtd0 of="$work/readback20" bs=262144 skip=202 count=80 2>/dev/null || return 1
 cmp -s "$work/recovery20" "$work/readback20" || return 1
 rm "$work/readback20" "$work/recovery20" "$work/vault" || return 1
}
dpn_auto_install() {
 local work="$1"
 mkdir "$work/install" || return 1
 # Use the standard RAM upgrade backend after full independent recovery/vault
 # readback. Unlike the legacy host workflow, no recovery reboot is inserted
 # here: all payloads remain in RAM and no browser/PC has to resume the job.
 dpn_l4_install /usr/share/dpn-install/normal.fip /usr/share/dpn-install/rootfs.squashfs "$work/config.tar.gz" "$work/install"
}
dpn_auto_run() {
 local work=/tmp/dpn-factory-auto
 # An exclusive directory is the transaction boundary, including failures.
 # procd has no respawn; do not retry writes or restart this job on errors.
 mkdir -m 700 "$work" || return 1
 dpn_auto_status CHECKING
 dpn_auto_preflight || return 1
 dpn_auto_status PREPARING
 dpn_auto_seed "$work" || return 1
 dpn_auto_prepare "$work" || return 1
 dpn_auto_status PROVISIONING_RECOVERY
 dpn_auto_provision "$work" || return 1
 dpn_auto_status INSTALLING
 dpn_auto_install "$work" || return 1
 dpn_auto_status COMPLETE
 sync || return 1
 echo b > /proc/sysrq-trigger
 return 1
}
