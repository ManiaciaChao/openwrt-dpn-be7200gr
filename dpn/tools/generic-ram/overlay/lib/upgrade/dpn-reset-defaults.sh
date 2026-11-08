# SPDX-License-Identifier: GPL-2.0-only
# Caller validates live layout and creates the private transaction parent.
dpn_reset_seed() {
 local stage="$1" owner="$2" defaults="$3"
umask 077
mkdir -m 755 "$stage" "$stage/etc" "$stage/etc/config"
mkdir -m 700 "$stage/etc/dropbear"
cp "$owner"/dropbear/authorized_keys "$owner"/dropbear/dropbear_ed25519_host_key "$stage/etc/dropbear/"
chmod 600 "$stage/etc/dropbear/"*
# Automatic installs generate a per-device recovery client key. Retain the
# owner's ability to export it after a normal physical factory reset as well.
if [ -d "$owner/dpn-recovery" ] && [ ! -L "$owner/dpn-recovery" ]; then
 cp -a "$owner/dpn-recovery" "$stage/etc/"
 chmod 700 "$stage/etc/dpn-recovery"
 printf '/etc/dpn-recovery/\n' > "$stage/etc/sysupgrade.conf"
fi
cp "$defaults"/config/network "$defaults"/config/dhcp "$stage/etc/config/"
uci -c "$stage/etc/config" -t "$stage/.uci" set network.lan.proto=static
uci -c "$stage/etc/config" -t "$stage/.uci" set network.lan.ipaddr=192.168.1.1
uci -c "$stage/etc/config" -t "$stage/.uci" set network.lan.netmask=255.255.255.0
uci -c "$stage/etc/config" -t "$stage/.uci" add_list network.lan.ip6addr=fe80::72:104/64
uci -c "$stage/etc/config" -t "$stage/.uci" set dhcp.lan.ignore=0
uci -c "$stage/etc/config" -t "$stage/.uci" set dhcp.lan.start=100
uci -c "$stage/etc/config" -t "$stage/.uci" set dhcp.lan.limit=150
uci -c "$stage/etc/config" -t "$stage/.uci" set dhcp.lan.leasetime=12h
uci -c "$stage/etc/config" -t "$stage/.uci" commit
rm -rf "$stage/.uci"
# LAN-only initial LuCI setup, as in the original RAM installer. Password SSH
# stays disabled; retained owner keys also keep the independent recovery usable.
sed 's/^root:[^:]*:/root::/' "$defaults"/shadow > "$stage/etc/shadow"
chmod 600 "$stage/etc/shadow"
}
