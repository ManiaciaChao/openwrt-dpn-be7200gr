# Complete a staged configuration replacement. Each rename is atomic on UBIFS.
dpn_config_commit() {
 local root="$1"
 [ -f "$root/dpn-upgrade.pending" ] || return 0
 [ "$(cat "$root/dpn-upgrade.pending")" = v1 ] || return 1
 if [ -d "$root/dpn-upgrade-next/upper" ]; then
  if [ -d "$root/upper" ]; then
   [ ! -e "$root/dpn-upgrade-old-upper" ] || return 1
   mv "$root/upper" "$root/dpn-upgrade-old-upper" || return 1
  fi
  mv "$root/dpn-upgrade-next/upper" "$root/upper" || return 1
 fi
 [ -d "$root/upper" ] || return 1
 rm -rf "$root/work" "$root/dpn-upgrade-old-upper" "$root/dpn-upgrade-next" || return 1
 mkdir "$root/work" || return 1
 sync || return 1
 rm "$root/dpn-upgrade.pending" || return 1
 sync || return 1
}
