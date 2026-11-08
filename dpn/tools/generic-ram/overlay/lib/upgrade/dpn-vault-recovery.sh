# SPDX-License-Identifier: GPL-2.0-only
# Independent wired key-only RAM recovery. Never mounts the main configuration.
dpn_vault_recovery() {
 local vault file flag count=0
 [ ! -e /sys/module/dpn_storage ] || return 1
 [ ! -e /sys/class/ubi/ubi0 ] || return 1
 for flag in $(cat /proc/cmdline); do
  case "$flag" in dpn_vault_selftest=1) count=$((count+1));; dpn_vault_selftest=*) return 1;; esac
 done
 if [ "$count" = 1 ] && [ -e /sys/firmware/devicetree/base/dpn-flash-layout/persistent-root ]; then
  # Explicit private RAM-session test; this file is never in public firmware.
  vault=/etc/dpn-provision/recovery.vault
  [ -f "$vault" ] && [ ! -L "$vault" ] || return 1
  echo RAM_SESSION_VAULT > /etc/dpn-vault-source
 elif [ "$count" = 0 ] && [ -d /sys/firmware/devicetree/base/dpn-layout4 ]; then
  # The dedicated driver exposes only typed RO views at recovery entry.
  # Device identity is checked by the native reader before any SSH key use.
  case "$(tr -d '\000' < /sys/firmware/devicetree/base/dpn-layout4/write-profile)" in
   normal|recovery) ;; *) return 1;;
  esac
  [ ! -e /sys/class/mtd/mtd2 ] || return 1
  insmod /lib/modules/6.18.60/dpn_layout4_storage.ko || return 1
  [ "$(cat /sys/class/mtd/mtd3/name)" = dpn-layout4-vault ] || return 1
  [ "$(cat /sys/class/mtd/mtd3/size)" = 4194304 ] || return 1
  [ "$(( $(cat /sys/class/mtd/mtd3/flags) & 1024 ))" = 0 ] || return 1
  vault=/dev/mtd3ro
  echo NAND_DEVICE_BOUND_VAULT > /etc/dpn-vault-source
 else
  return 1
 fi
 [ "$(wc -c < "$vault")" = 4194304 ] || return 1
 mkdir -p /etc/dropbear || return 1
 chmod 700 /etc/dropbear || return 1
 /usr/libexec/dpn-vault-check --extract-identity "$vault" /sys/bus/nvmem/devices/dpn-art/nvmem /etc/dropbear || return 1
 dropbearkey -y -f /etc/dropbear/dropbear_ed25519_host_key >/dev/null || return 1
 # Public-key-only service flags below prohibit both password and none auth.
 # A fresh RAM account needs no main-CFG password hash to accept owner keys.
 sed -i 's/^root:[^:]*:/root::/' /etc/shadow || return 1
 cat > /etc/config/network <<'DPN_NETWORK'
config interface 'loopback'
 option device 'lo'
 option proto 'static'
 option ipaddr '127.0.0.1'
 option netmask '255.0.0.0'
config device 'recovery_bridge'
 option name 'br-lan'
 option type 'bridge'
 option stp '0'
 list ports 'lan10'
 list ports 'ge1'
 list ports 'ge2'
 list ports 'ge3'
 list ports 'ge4'
config interface 'lan'
 option device 'br-lan'
 option proto 'static'
 option ipaddr '192.168.1.1'
 option netmask '255.255.255.0'
 list ip6addr 'fe80::72:104/64'
 option delegate '0'
config interface 'wan'
 option device 'wan10'
 option proto 'none'
 option delegate '0'
DPN_NETWORK
 # Keep DHCP, RA and DNS services disabled on the rescue LAN.
 cat > /etc/config/dhcp <<'DPN_DHCP'
config dnsmasq
 option port '0'
config dhcp 'lan'
 option interface 'lan'
 option ignore '1'
 option ra 'disabled'
 option dhcpv6 'disabled'
DPN_DHCP
 cat > /etc/config/firewall <<'DPN_FIREWALL'
config defaults
 option input 'REJECT'
 option output 'ACCEPT'
 option forward 'REJECT'
config zone
 option name 'lan'
 list network 'lan'
 option input 'ACCEPT'
 option output 'ACCEPT'
 option forward 'REJECT'
config zone
 option name 'wan'
 list network 'wan'
 option input 'REJECT'
 option output 'ACCEPT'
 option forward 'REJECT'
DPN_FIREWALL
 for file in /etc/rc.d/*dropbear; do
  [ ! -e "$file" ] && [ ! -L "$file" ] || rm "$file" || return 1
 done
 ln -s ../init.d/dpn_recovery_ssh /etc/rc.d/S89dpn_recovery_ssh || return 1
 rm -f /etc/uci-defaults/* || return 1
 echo INDEPENDENT_VAULT_RECOVERY > /etc/dpn-network-recovery
 echo DPN_INDEPENDENT_VAULT_WIRED_RECOVERY_NO_MAIN_CFG
 export INITRAMFS=1
 dpn_watchdog_handoff
 exec /sbin/init
}
