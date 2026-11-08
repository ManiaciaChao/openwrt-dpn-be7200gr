# SPDX-License-Identifier: GPL-2.0-only
# Filesystem-only setup, called on a newly created/resumable private setup volume.
# Public SquashFS remains password-locked; the owner's direct-LAN first-setup
# overlay has no password until configured through LuCI. WAN and Wi-Fi stay off.
dpn_fresh_configuration() {
 local rom="$1" cfg="$2" upper file
 [ ! -e "$cfg/upper" ] || return 1
 [ ! -L "$cfg/dpn-upgrade-next" ] || return 1
 rm -rf "$cfg/dpn-upgrade-next" || return 1
 upper=$cfg/dpn-upgrade-next/upper
 mkdir -p "$upper/etc/config" "$upper/etc/dropbear" || return 1
 chmod 700 "$upper/etc/dropbear"
 for file in "$rom"/etc/config/*; do
  [ -f "$file" ] && [ ! -L "$file" ] || continue
  cp "$file" "$upper/etc/config/${file##*/}" || return 1
 done
 for file in passwd group shells; do cp "$rom/etc/$file" "$upper/etc/$file" || return 1; done
 (umask 077; sed 's/^root:[^:]*:/root::/' "$rom/etc/shadow" > "$upper/etc/shadow") || return 1
 grep -q '^root::' "$upper/etc/shadow" || return 1
 uci -c "$upper/etc/config" set network.lan.proto=static || return 1
 uci -c "$upper/etc/config" set network.lan.ipaddr=192.168.1.1 || return 1
 uci -c "$upper/etc/config" set network.lan.netmask=255.255.255.0 || return 1
 uci -c "$upper/etc/config" set dhcp.lan.ignore=0 || return 1
 uci -c "$upper/etc/config" set dhcp.lan.start=100 || return 1
 uci -c "$upper/etc/config" set dhcp.lan.limit=150 || return 1
 uci -c "$upper/etc/config" set dhcp.lan.leasetime=12h || return 1
 uci -c "$upper/etc/config" set 'dhcp.@dnsmasq[0].port=53' || return 1
 uci -c "$upper/etc/config" set 'dhcp.@dnsmasq[0].leasefile=/tmp/dhcp.leases' || return 1
 uci -c "$upper/etc/config" commit || return 1
 (umask 077; dropbearkey -t ed25519 -f "$upper/etc/dropbear/dropbear_ed25519_host_key" >/dev/null) || return 1
 chmod 600 "$upper/etc/dropbear/dropbear_ed25519_host_key"
 printf 'SET_PASSWORD_AND_OWNER_SSH_KEYS_ON_DIRECT_LAN\n' > "$upper/etc/dpn-first-setup"
 printf 'v1\n' > "$cfg/dpn-upgrade.pending"
 sync
 command -v dpn_config_commit >/dev/null || . /lib/upgrade/dpn-config-commit.sh
 dpn_config_commit "$cfg" || return 1
 ln -s 2 "$cfg/.fs_state" || return 1
 sync
}
# RO discovery occurs before the full SquashFS is mounted, so views can be
# replaced without disturbing a running filesystem. Only ALL-FF gets formatted.
dpn_prepare_configuration() {
 local name count
 DPN_FIRST_BOOT_NEW=0
 if ubiattach -m 3 -d 0; then
  set -- /sys/class/ubi/ubi0_*/name
  if [ "$#" = 1 ] && [ -f "$1" ]; then
   name=$(cat "$1") || return 1
   case "$name" in rootfs_data) DPN_FIRST_BOOT_VOLUME=rootfs_data;; dpn-first-setup) DPN_FIRST_BOOT_NEW=1; DPN_FIRST_BOOT_VOLUME=dpn-first-setup;; *) return 1;; esac
  elif [ "$#" = 1 ] && [ ! -e "$1" ]; then
   DPN_FIRST_BOOT_NEW=1; DPN_FIRST_BOOT_VOLUME=dpn-first-setup
  else return 1
  fi
  ubidetach -m 3 || return 1
 else
  [ ! -e /sys/class/ubi/ubi0 ] || return 1
  /usr/libexec/dpn-install --check-config-blank || return 1
  DPN_FIRST_BOOT_NEW=2; DPN_FIRST_BOOT_VOLUME=dpn-first-setup
 fi
 rmmod dpn_storage || return 1
 insmod /lib/modules/6.18.60/dpn_storage.ko $module_args || return 1
 if [ "$DPN_FIRST_BOOT_NEW" = 2 ]; then ubiformat /dev/mtd3 -y || return 1; fi
 ubiattach -m 3 -d 0 || return 1
 if [ "$DPN_FIRST_BOOT_NEW" != 0 ] && [ ! -e /sys/class/ubi/ubi0_0 ]; then
  ubimkvol /dev/ubi0 -n 0 -N dpn-first-setup -m || return 1
 fi
 [ "$(cat /sys/class/ubi/ubi0_0/name)" = "$DPN_FIRST_BOOT_VOLUME" ] || return 1
}
