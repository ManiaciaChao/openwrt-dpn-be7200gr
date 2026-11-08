/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_PERSIST_GUARD_H
#define DPN_PERSIST_GUARD_H
#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <stdint.h>
#include <stdbool.h>
typedef uint64_t u64;
#endif
#define DPN_CFG_START 0x01280000ULL
#define DPN_CFG_END   0x03280000ULL
#define DPN_CFG_SIZE  (DPN_CFG_END - DPN_CFG_START)
#define DPN_CFG_PAGE 4096ULL
#define DPN_CFG_BLOCK 262144ULL
static inline bool dpn_cfg_range(u64 offset, u64 bytes)
{
 return bytes && offset >= DPN_CFG_START && offset < DPN_CFG_END && bytes <= DPN_CFG_END-offset;
}
static inline bool dpn_cfg_row(u64 row, bool erase)
{
 if (row < DPN_CFG_START / DPN_CFG_PAGE || row >= DPN_CFG_END / DPN_CFG_PAGE) return false;
 if (erase && row % (DPN_CFG_BLOCK / DPN_CFG_PAGE)) return false;
 return !erase || row <= (DPN_CFG_END-DPN_CFG_BLOCK) / DPN_CFG_PAGE;
}
#define DPN_FW_START 0x00080000ULL
#define DPN_FW_END DPN_CFG_START
#define DPN_FW_SIZE (DPN_FW_END-DPN_FW_START)
static inline bool dpn_fw_range(u64 off,u64 n) { return n && off>=DPN_FW_START && off<DPN_FW_END && n<=DPN_FW_END-off; }
static inline bool dpn_fw_row(u64 row,bool erase) {
 return row>=DPN_FW_START/DPN_CFG_PAGE && row<DPN_FW_END/DPN_CFG_PAGE &&
 (!erase || (!(row%(DPN_CFG_BLOCK/DPN_CFG_PAGE)) && row<=(DPN_FW_END-DPN_CFG_BLOCK)/DPN_CFG_PAGE));
}
#ifdef __KERNEL__
static inline bool dpn_write_range(u64 off,u64 n) {
 return dpn_cfg_range(off,n) || (of_machine_is_compatible("dlink,dpn-be7200gr-upgrade") && dpn_fw_range(off,n));
}
static inline bool dpn_write_row(u64 row,bool erase) {
 return dpn_cfg_row(row,erase) || (of_machine_is_compatible("dlink,dpn-be7200gr-upgrade") && dpn_fw_row(row,erase));
}
#endif
#endif
