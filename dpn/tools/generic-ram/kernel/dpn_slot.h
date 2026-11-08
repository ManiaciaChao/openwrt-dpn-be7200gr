/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_SLOT_H
#define DPN_SLOT_H
/* Root views may read either slot. This never expands any write permission. */
#define DPN_SLOT_BYTES 0x3200000U
#define DPN_PRIMARY_START 0x80000U
#define DPN_BACKUP_START 0x3280000U
#define DPN_PREFIX_BYTES 0x1200000U
static inline int dpn_slot_root(unsigned main_offset, unsigned bytes,
                                unsigned slot, unsigned *physical)
{
 unsigned relative;
 if (slot > 1 || main_offset < DPN_PRIMARY_START || !bytes)
  return -1;
 relative = main_offset - DPN_PRIMARY_START;
 if (relative >= DPN_PREFIX_BYTES || bytes > DPN_PREFIX_BYTES - relative)
  return -1;
 *physical = (slot ? DPN_BACKUP_START : DPN_PRIMARY_START) + relative;
 return 0;
}
#endif
