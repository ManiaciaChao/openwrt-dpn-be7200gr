/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_STOCK_RETURN_POLICY_H
#define DPN_STOCK_RETURN_POLICY_H
#include "dpn_slot_policy.h"
/* A separate rescue profile: no CFG, ART, bootloader, or other-slot writes. */
#define DPN_STOCK_SLOT_BYTES 0x3200000ULL
static inline int dpn_stock_return_range(unsigned long long off,
                                       unsigned long long bytes, int slot)
{
 unsigned long long base;
 if(slot<0 || slot>1 || !bytes)return 0;
 base=dpn_firmware_base((unsigned)slot);
 return off>=base && off<base+DPN_STOCK_SLOT_BYTES &&
        bytes<=base+DPN_STOCK_SLOT_BYTES-off;
}
static inline int dpn_stock_return_row(unsigned long long row,int erase,int slot)
{
 if(row>=131072 || (erase && row%64))return 0;
 return dpn_stock_return_range(row*4096,erase?262144:4096,slot);
}
#endif
