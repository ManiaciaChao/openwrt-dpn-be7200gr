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
#endif
