# SPDX-License-Identifier: GPL-2.0-only
# Vendor U-Boot passes bootflag + root together. Refuse ambiguous handoffs;
# do not use a mutable ART flag as evidence of the currently executing slot.
dpn_boot_slot() {
 local arg flag= root= flags=0 roots=0
 for arg in $1; do
  case "$arg" in
   bootflag=*) flags=$((flags+1)); flag=${arg#bootflag=};;
   root=*) roots=$((roots+1)); root=${arg#root=};;
  esac
 done
 [ "$flags" = 1 ] && [ "$roots" = 1 ] || return 1
 case "$flag:$root" in
  0:/dev/mtdblock3) echo 0;;
  1:/dev/mtdblock6) echo 1;;
  *) return 1;;
 esac
}
