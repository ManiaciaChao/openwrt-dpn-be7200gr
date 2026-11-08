# SPDX-License-Identifier: GPL-2.0-only
# Bind the recovery LAN zone to its saved device before netifd starts.
# The owner configuration on Flash stays read-only. This edits the RAM copy.
# A DHCP-pending LAN must not leave key-only recovery dependent on a later lease.
dpn_recovery_bind_firewall() {
 local config="${1:-/etc/config}" device section networks found= count=0 devices
 device=$(uci -q -c "$config" get network.lan.device) || return 1
 [ -n "$device" ] && [ "${#device}" -le 15 ] || return 1
 case "$device" in lo|*[!a-zA-Z0-9_.:-]*) return 1;; esac
 for section in $(uci -q -c "$config" show firewall | sed -n 's/^firewall\.\([^=]*\)=zone$/\1/p'); do
  networks=$(uci -q -c "$config" get "firewall.$section.network") || continue
  case " $networks " in *' lan '*) found="$section"; count=$((count+1));; esac
 done
 [ "$count" = 1 ] || return 1
 devices=$(uci -q -c "$config" get "firewall.$found.device") || devices=
 case " $devices " in *" $device "*) ;; *) uci -q -c "$config" add_list "firewall.$found.device=$device" || return 1;; esac
 uci -q -c "$config" commit firewall
}
