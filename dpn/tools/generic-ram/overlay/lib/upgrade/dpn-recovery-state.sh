# SPDX-License-Identifier: GPL-2.0-only
# Select an intact configuration tree without completing or modifying a transaction.
dpn_recovery_upper() {
 local root="$1" name
 for name in upper dpn-upgrade-next dpn-upgrade-old-upper dpn-upgrade.pending; do
  [ ! -L "$root/$name" ] || return 1
 done
 if [ -e "$root/dpn-upgrade.pending" ]; then
  [ -f "$root/dpn-upgrade.pending" ] && [ "$(cat "$root/dpn-upgrade.pending")" = v1 ] || return 1
  if [ -d "$root/dpn-upgrade-old-upper" ]; then
   echo dpn-upgrade-old-upper
  elif [ -d "$root/upper" ]; then
   echo upper
  else
   return 1
  fi
 else
  [ ! -e "$root/dpn-upgrade-next" ] && [ ! -e "$root/dpn-upgrade-old-upper" ] || return 1
  [ -d "$root/upper" ] || return 1
  echo upper
 fi
}
