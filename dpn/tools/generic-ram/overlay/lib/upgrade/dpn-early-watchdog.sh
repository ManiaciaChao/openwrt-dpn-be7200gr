# SPDX-License-Identifier: GPL-2.0-only
# Keep long NAND preflight/initialization alive, then use procd's WDTFD handoff.
dpn_watchdog_start() {
 [ -c /dev/watchdog ] || return 0
 exec 9>/dev/watchdog || return 1
 export WDTFD=9
 (
  while :; do printf . >&9 || exit 1; sleep 2; done
 ) &
 DPN_WATCHDOG_KEEPER=$!
}
dpn_watchdog_handoff() {
 [ -z "${DPN_WATCHDOG_KEEPER:-}" ] || kill "$DPN_WATCHDOG_KEEPER" 2>/dev/null
 # Descriptor 9 stays open across exec; procd adopts and feeds the same fd.
 return 0
}
