// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include "kernel/dpn_install_guard.h"
int main(void)
{
 for (u64 row=0; row<131072; row++) {
  u64 off=row*4096;
  bool allowed=(off>=0x80000&&off<0x1280000)||
               (off>=0xb800000&&off<0x1b800000);
  assert(dpn_install_row(row,false)==allowed);
  assert(dpn_install_row(row,true)==(allowed&&!(row%64)));
  assert(dpn_install_range(off,4096)==allowed);
  assert(!dpn_install_range(off,0));
 }
 assert(!dpn_install_row(131072,false));
 assert(!dpn_install_row(UINT64_MAX,true));
 assert(!dpn_install_range(UINT64_MAX,1));
 assert(!dpn_install_range(0x80000,UINT64_MAX));
 assert(!dpn_install_range(0x127f000,8192));
 assert(!dpn_install_range(0x1b7ff000,8192));
 assert(!dpn_install_range(0x1280000,1));
 assert(!dpn_install_range(0x3280000,0x3200000));
 assert(!dpn_install_range(0x1bc80000,0x380000));
 return 0;
}
