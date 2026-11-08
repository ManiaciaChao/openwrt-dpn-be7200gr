/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <limits.h>
#include "kernel/dpn_slot.h"
#include "kernel/dpn_install_guard.h"
int main(void) {
 unsigned physical=0;
 assert(!dpn_slot_root(0x100000,0x773000,0,&physical) && physical==0x100000);
 assert(!dpn_slot_root(0x100000,0x773000,1,&physical) && physical==0x3300000);
 assert(!dpn_slot_root(0x80000,0x1200000,1,&physical) && physical==0x3280000);
 assert(!dpn_install_range(physical,4096));
 assert(!dpn_slot_root(0x127ffff,1,1,&physical) && physical==0x447ffff);
 assert(dpn_slot_root(0x127ffff,2,1,&physical));
 assert(dpn_slot_root(0x1280000,1,0,&physical));
 assert(dpn_slot_root(0x7ffff,1,0,&physical));
 assert(dpn_slot_root(0x80000,0,0,&physical));
 assert(dpn_slot_root(0x80000,UINT_MAX,0,&physical));
 assert(dpn_slot_root(UINT_MAX,1,1,&physical));
 assert(dpn_slot_root(0x80000,1,2,&physical));
 assert(dpn_install_range(0x80000,0x1200000));
 assert(dpn_install_range(0xb800000,0x10000000));
 assert(!dpn_install_range(0x3280000,4096));
 assert(!dpn_install_range(0x1bfc0000,4096));
 return 0;
}
