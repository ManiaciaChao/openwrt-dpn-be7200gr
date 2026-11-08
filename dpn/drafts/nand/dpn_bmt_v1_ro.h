/* SPDX-License-Identifier: GPL-2.0-only */
/* DPN-BE7200GR vendor BMT v1/RAWB parser. No IO or mutation callbacks.
 * Wire offsets/checksums independently checked against this board's dump and
 * the Airoha algorithm; do not interpret this as a NAND programming backend.
 */
#ifndef DPN_BMT_V1_RO_H
#define DPN_BMT_V1_RO_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/string.h>
#else
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#endif

#define DPN_BLOCKS 2048
#define DPN_LOGICAL_BLOCKS 1792
#define DPN_BLOCK_SIZE 262144U
#define DPN_PAGE_SIZE 4096U
#define DPN_SPARE_SIZE 256U
#define DPN_TABLE_MAX 250
#define DPN_BMT_BYTES (20 + DPN_TABLE_MAX * 4)
#define DPN_RAWB_BYTES 512

enum dpn_bmt_error {
	DPN_OK, DPN_BAD_POOL, DPN_BAD_LENGTH, DPN_BAD_SIGNATURE,
	DPN_BAD_VERSION, DPN_BAD_COUNT, DPN_BAD_CHECKSUM, DPN_BAD_BLOCK,
	DPN_DUPLICATE, DPN_BAD_TARGET, DPN_NOT_VALID, DPN_OUT_OF_RANGE,
	DPN_UNMAPPED_BAD_BLOCK
};

struct dpn_bmt_v1 {
	u16 map[DPN_LOGICAL_BLOCKS];
	u8 bad[DPN_BLOCKS];
	u16 pool_start, pool_blocks, bmt_block, rawb_block;
	u16 mappings, raw_bad_count;
	bool valid;
};

static inline u16 dpn_le16(const u8 *p) { return p[0] | (u16)p[1] << 8; }
static inline u32 dpn_le32(const u8 *p)
{
	return p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24;
}

/* Caller scans byte0 of BOTH first pages, as specified by F35SQB004G. */
static inline bool dpn_bad_markers(u8 first, u8 second)
{
	return first != 0xff || second != 0xff;
}

static inline int dpn_pool_start(const u8 bad[DPN_BLOCKS])
{
	unsigned good = 0;
	int block;
	for (block = DPN_BLOCKS - 1; block >= 0; block--) {
		if (!bad[block] && ++good == DPN_BLOCKS * 8 / 100) {
			if (block < DPN_LOGICAL_BLOCKS || DPN_BLOCKS - block > DPN_TABLE_MAX)
				return -1;
			return block;
		}
	}
	return -1;
}

/* On every error valid remains false, including when reusing a prior state. */
static inline int dpn_bmt_v1_parse(struct dpn_bmt_v1 *s,
	const u8 *bmt, unsigned bmt_len, const u8 *rawb, unsigned rawb_len,
	const u8 physical_bad[DPN_BLOCKS], const u8 *retired_bad,
	unsigned bmt_block, unsigned rawb_block)
{
	unsigned i, j, sum, count, from, to;
	int start;
	s->valid = false;
	start = dpn_pool_start(physical_bad);
	if (start < 0)
		return DPN_BAD_POOL;
	s->pool_start = start;
	s->pool_blocks = DPN_BLOCKS - start;
	if (bmt_len < 20U + s->pool_blocks * 4U || rawb_len < DPN_RAWB_BYTES)
		return DPN_BAD_LENGTH;
	if (memcmp(bmt, "BMT", 3) || memcmp(rawb, "RAWB", 4))
		return DPN_BAD_SIGNATURE;
	if (bmt[3] != 1 || rawb[8] != 1)
		return DPN_BAD_VERSION;
	if (bmt[5] > s->pool_blocks || rawb[9] > DPN_TABLE_MAX)
		return DPN_BAD_COUNT;
	if (bmt_block < (unsigned)start || bmt_block >= DPN_BLOCKS ||
	    rawb_block < (unsigned)start || rawb_block >= DPN_BLOCKS ||
	    bmt_block == rawb_block || physical_bad[bmt_block] || physical_bad[rawb_block] ||
	    (retired_bad && (retired_bad[bmt_block] || retired_bad[rawb_block])))
		return DPN_BAD_BLOCK;
	sum = bmt[3] + bmt[5];
	for (i = 20; i < 20U + s->pool_blocks * 4U; i++)
		sum += bmt[i];
	if ((sum & 255) != bmt[6])
		return DPN_BAD_CHECKSUM;
	sum = rawb[8] + rawb[9];
	for (i = 12; i < DPN_RAWB_BYTES; i++)
		sum += rawb[i];
	if ((sum & 65535) != dpn_le32(rawb + 4))
		return DPN_BAD_CHECKSUM;
	memcpy(s->bad, physical_bad, sizeof(s->bad));
	if (retired_bad)
		for (i = 0; i < DPN_BLOCKS; i++)
			s->bad[i] |= retired_bad[i];
	for (i = 0; i < rawb[9]; i++) {
		from = dpn_le16(rawb + 12 + i * 2);
		if (from >= DPN_BLOCKS || from == bmt_block || from == rawb_block)
			return DPN_BAD_BLOCK;
		for (j = 0; j < i; j++)
			if (from == dpn_le16(rawb + 12 + j * 2))
				return DPN_DUPLICATE;
		s->bad[from] = 1;
	}
	for (i = 0; i < DPN_LOGICAL_BLOCKS; i++)
		s->map[i] = i;
	count = bmt[5];
	for (i = 0; i < count; i++) {
		from = dpn_le16(bmt + 20 + i * 4);
		to = dpn_le16(bmt + 22 + i * 4);
		if (from >= (unsigned)start || to < (unsigned)start || to >= DPN_BLOCKS ||
		    to == bmt_block || to == rawb_block || s->bad[to])
			return DPN_BAD_TARGET;
		for (j = 0; j < i; j++)
			if (from == dpn_le16(bmt + 20 + j * 4) ||
			    to == dpn_le16(bmt + 22 + j * 4))
				return DPN_DUPLICATE;
		if (from < DPN_LOGICAL_BLOCKS)
			s->map[from] = to;
	}
	s->mappings = count;
	s->raw_bad_count = rawb[9];
	s->bmt_block = bmt_block;
	s->rawb_block = rawb_block;
	s->valid = true;
	return DPN_OK;
}

static inline int dpn_bmt_v1_translate(const struct dpn_bmt_v1 *s, u64 logical,
	u64 *physical, unsigned *contiguous)
{
	unsigned block, offset, target;
	if (!s->valid)
		return DPN_NOT_VALID;
	if (logical >= (u64)DPN_LOGICAL_BLOCKS * DPN_BLOCK_SIZE)
		return DPN_OUT_OF_RANGE;
	block = logical / DPN_BLOCK_SIZE;
	offset = logical % DPN_BLOCK_SIZE;
	target = s->map[block];
	if (target >= DPN_BLOCKS || target == s->bmt_block || target == s->rawb_block)
		return DPN_BAD_TARGET;
	if (s->bad[target])
		return DPN_UNMAPPED_BAD_BLOCK;
	*physical = (u64)target * DPN_BLOCK_SIZE + offset;
	*contiguous = DPN_BLOCK_SIZE - offset;
	return DPN_OK;
}
#endif
