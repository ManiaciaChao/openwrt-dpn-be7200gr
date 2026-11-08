/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <limits.h>
#include <string.h>
#include "kernel/dpn_slot_policy.h"
int main(void) {
 assert(dpn_cmdline_slot("bootflag=0 root=/dev/mtdblock3 ro")==0);
 assert(dpn_cmdline_slot("root=/dev/mtdblock6 console=x bootflag=1")==1);
 assert(dpn_cmdline_slot("root=/dev/mtdblock6 bootflag=0")==-1);
 assert(dpn_cmdline_slot("bootflag=0 root=/dev/mtdblock3 bootflag=0")==-1);
 assert(dpn_cmdline_slot("bootflag=0 root=/dev/mtdblock3 root=/dev/mtdblock3")==-1);
 assert(dpn_cmdline_slot("xbootflag=0 root=/dev/mtdblock3")==-1);
 assert(dpn_cmdline_slot("bootflag=01 root=/dev/mtdblock3")==-1);
 assert(dpn_cmdline_slot("bootflag=1 root=/dev/mtdblock60")==-1);
 char huge[4100];memset(huge,'x',4099);huge[4099]=0;assert(dpn_cmdline_slot(huge)==-1);
 for(int slot=0;slot<2;slot++) {
  unsigned long long base=dpn_firmware_base(slot),other=dpn_firmware_base(1-slot);
  assert(dpn_slot_write_range(base,0x1200000,slot));
  assert(!dpn_slot_write_range(other,1,slot));
  assert(!dpn_slot_write_range(base-1,2,slot));
  assert(!dpn_slot_write_range(base+0x1200000-1,2,slot));
  assert(!dpn_slot_write_range(base,ULLONG_MAX,slot));
  assert(!dpn_slot_write_range(0,1,slot));
  assert(!dpn_slot_write_range(0x1bfc0000,1,slot));
  assert(dpn_slot_write_range(0xb800000,0x10000000,slot));
 }
 assert(!dpn_slot_write_range(0x80000,1,-1));
 assert(!dpn_slot_write_range(0x3280000,1,-1));
 assert(dpn_slot_write_range(0xb800000,0x10000000,-1));
 return 0;
}
