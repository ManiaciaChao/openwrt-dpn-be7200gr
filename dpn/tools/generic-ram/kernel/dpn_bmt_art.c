// SPDX-License-Identifier: GPL-2.0-only
/* Read-only logical view over an ALREADY read-only physical MTD.
 * Does not enable a controller or attach any vendor rebuilding backend.
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/mtd/mtd.h>
#include <linux/mtd/spinand.h>
#include <linux/slab.h>
#include <linux/nvmem-provider.h>
#include <linux/platform_device.h>
#include <linux/etherdevice.h>
#include "../../../drafts/nand/dpn_bmt_v1_ro.h"

static int physical_index = -1;
module_param(physical_index, int, 0400);
static struct mtd_info *source;
static struct mtd_info view;
static struct dpn_bmt_v1 *state;
static struct nvmem_device *art_nvmem;

static int read_exact(loff_t offset, void *buf, size_t size)
{
	size_t done = 0;
	int err = mtd_read(source, offset, size, &done, buf);
	if (err && !mtd_is_bitflip(err))
		return err;
	return done == size ? 0 : -EIO;
}

static int logical_read(struct mtd_info *mtd, loff_t from, size_t len,
	size_t *retlen, u_char *buf)
{
	u64 physical;
	unsigned span;
	int err, corrected = 0;
	*retlen = 0;
	if (from < 0 || from > mtd->size || len > mtd->size - from)
		return -EINVAL;
	while (len) {
		size_t done = 0, take;
		if (dpn_bmt_v1_translate(state, from, &physical, &span))
			return -EIO;
		take = min_t(size_t, span, len);
		err = mtd_read(source, physical, take, &done, buf);
		if (err && !mtd_is_bitflip(err))
			return err;
		corrected |= mtd_is_bitflip(err);
		if (done != take)
			return -EIO;
		*retlen += done; from += done; buf += done; len -= done;
	}
	return corrected ? -EUCLEAN : 0;
}

static int logical_isbad(struct mtd_info *mtd, loff_t offset)
{
	u64 physical;
	unsigned span;
	int err;
	if (offset < 0 || offset >= mtd->size)
		return -EINVAL;
	err = dpn_bmt_v1_translate(state, offset, &physical, &span);
	return err == DPN_UNMAPPED_BAD_BLOCK ? 1 : err ? -EIO : 0;
}

/* ART offsets are logical vendor addresses, translated through the validated
 * BMT. All cells are read-only; no repair, unlock, erase or write callback. */
static int art_read(void *context, unsigned int offset, void *buf, size_t bytes)
{
 size_t done = 0;
 int err;
 if (offset > 0x380000 || bytes > 0x380000 - offset) return -EINVAL;
 err = logical_read(&view, 0x1bc80000ULL + offset, bytes, &done, buf);
 if (err && !mtd_is_bitflip(err)) return err;
 return done == bytes ? 0 : -EIO;
}
static int register_art(struct device *dev)
{
 struct device_node *node = of_find_node_by_path("/dpn-art");
 struct nvmem_config cfg = { .dev = dev, .name = "dpn-art",
  .id = NVMEM_DEVID_NONE, .owner = THIS_MODULE, .read_only = true,
  .root_only = true, .size = 0x380000, .word_size = 1, .stride = 1,
  .reg_read = art_read };
 u8 eeprom[2], mac[ETH_ALEN]; char ascii[18] = {0}; int err;
 if (!node) return -EINVAL;
 cfg.of_node = node;
 err = art_read(NULL, 0x40000, eeprom, 2);
 if (!err && (eeprom[0] != 0x92 || eeprom[1] != 0x79)) err = -EINVAL;
 if (!err) err = art_read(NULL, 0x301055, ascii, 17);
 if (!err && (!mac_pton(ascii, mac) || !is_valid_ether_addr(mac))) err = -EINVAL;
 if (!err) {
  art_nvmem = nvmem_register(&cfg);
  if (IS_ERR(art_nvmem)) { err = PTR_ERR(art_nvmem); art_nvmem = NULL; }
 }
 of_node_put(node);
 return err;
}

/* Writing is deliberately limited to identity-mapped supported devices.
 * Nonempty mappings remain readable for recovery, but are not reinterpreted
 * as permission to program firmware or update the vendor BMT. */
bool dpn_factory_write_eligible(void);
bool dpn_factory_write_eligible(void)
{
 unsigned b;
 struct spinand_device *chip;
 if (!state || state->mappings || state->raw_bad_count) return false;
 /* The physical source is the SPI-NAND master, not a partition or BMT view.
  * Qualification covers this exact chip/ECC/OOB combination only. */
 chip=mtd_to_spinand(source);
 if(chip->id.len!=3||chip->id.data[0]!=0xcd||chip->id.data[1]!=0x53||chip->id.data[2]!=0x53||source->ecc_strength!=8||source->ecc_step_size!=512)return false;
 for (b = 2; b < 74; b++) if (state->bad[b]) return false;
 for (b = 202; b < 274; b++) if (state->bad[b]) return false;
 return true;
}
EXPORT_SYMBOL_GPL(dpn_factory_write_eligible);

static int dpn_art_probe(struct platform_device *pdev)
{
	u8 *bad = NULL, *retired = NULL, *bmt = NULL, *rawb = NULL, *page = NULL;
	unsigned block, p, bmt_block = 0, rawb_block = 0, bmts = 0, rawbs = 0;
	int err = -EINVAL, pool;
	if (!of_machine_is_compatible("dlink,dpn-be7200gr-ram") || physical_index < 0)
		return -ENODEV;
	source = get_mtd_device(NULL, physical_index);
	if (IS_ERR(source)) { err = PTR_ERR(source); source = NULL; return err; }
	if (!source->name || strcmp(source->name, "dpn-physical-nand-ro") || source->flags & MTD_WRITEABLE ||
	    source->size != (u64)DPN_BLOCKS * DPN_BLOCK_SIZE ||
	    source->erasesize != DPN_BLOCK_SIZE || source->writesize != DPN_PAGE_SIZE ||
	    source->oobsize != DPN_SPARE_SIZE)
		goto out;
	state = kzalloc(sizeof(*state), GFP_KERNEL);
	bad = kcalloc(DPN_BLOCKS, 1, GFP_KERNEL); retired = kcalloc(DPN_BLOCKS, 1, GFP_KERNEL);
	bmt = kmalloc(DPN_BMT_BYTES, GFP_KERNEL); rawb = kmalloc(DPN_RAWB_BYTES, GFP_KERNEL);
	page = kmalloc(DPN_BMT_BYTES, GFP_KERNEL);
	if (!state || !bad || !retired || !bmt || !rawb || !page) { err = -ENOMEM; goto out; }
	for (block = 0; block < DPN_BLOCKS; block++) {
		for (p = 0; p < 2; p++) {
			u8 markers[2];
			struct mtd_oob_ops ops = { .mode = MTD_OPS_PLACE_OOB,
				.ooblen = sizeof(markers), .oobbuf = markers };
			err = mtd_read_oob(source, (u64)block * DPN_BLOCK_SIZE + p * DPN_PAGE_SIZE, &ops);
			if ((err && !mtd_is_bitflip(err)) || ops.oobretlen != sizeof(markers)) {
				err = err ? err : -EIO; goto out;
			}
			bad[block] |= markers[0] != 0xff;
			retired[block] |= markers[1] != 0xff;
		}
	}
	pool = dpn_pool_start(bad);
	if (pool < 0) { err = -EINVAL; goto out; }
	for (block = pool; block < DPN_BLOCKS; block++) {
		if (bad[block] || retired[block])
			continue;
		err = read_exact((u64)block * DPN_BLOCK_SIZE, page, DPN_BMT_BYTES);
		if (err)
			goto out;
		if (!memcmp(page, "BMT", 3)) {
			if (++bmts != 1) { err = -ENOTUNIQ; goto out; }
			memcpy(bmt, page, DPN_BMT_BYTES); bmt_block = block;
		}
		if (!memcmp(page, "RAWB", 4)) {
			if (++rawbs != 1) { err = -ENOTUNIQ; goto out; }
			memcpy(rawb, page, DPN_RAWB_BYTES); rawb_block = block;
		}
	}
	if (bmts != 1 || rawbs != 1) { err = -ENODATA; goto out; }
	err = dpn_bmt_v1_parse(state, bmt, DPN_BMT_BYTES, rawb, DPN_RAWB_BYTES,
		bad, retired, bmt_block, rawb_block);
	if (err) { pr_err("dpn-bmt-v1-ro: invalid metadata (%d), no repair attempted\n", err); err = -EINVAL; goto out; }
	view = (struct mtd_info) { .name = "dpn-vendor-logical-ro", .type = MTD_NANDFLASH,
		.flags = MTD_NO_ERASE, .size = (u64)DPN_LOGICAL_BLOCKS * DPN_BLOCK_SIZE,
		.erasesize = DPN_BLOCK_SIZE, .writesize = DPN_PAGE_SIZE, .writebufsize = DPN_PAGE_SIZE,
		.owner = THIS_MODULE, ._read = logical_read, ._block_isbad = logical_isbad };
	/* Deliberately no erase, write, OOB write or metadata-update callbacks. */
	view.dev.parent = &source->dev;
	{
		static const char * const no_parsers[] = { NULL };
		err = mtd_device_parse_register(&view, no_parsers, NULL, NULL, 0);
	}
	if (!err) {
		err = register_art(&pdev->dev);
		if (err) mtd_device_unregister(&view);
	}
	if (!err)
		pr_info("dpn-bmt-v1-ro: verified BMT=%u RAWB=%u pool=%u+%u, read-only logical view\n",
			bmt_block, rawb_block, state->pool_start, state->pool_blocks);
out:
	kfree(page); kfree(rawb); kfree(bmt); kfree(retired); kfree(bad);
	if (err) { kfree(state); state = NULL; put_mtd_device(source); source = NULL; }
	return err;
}

static void dpn_art_remove(struct platform_device *pdev)
{
	nvmem_unregister(art_nvmem);
	mtd_device_unregister(&view);
	kfree(state);
	put_mtd_device(source);
}
static const struct of_device_id dpn_art_match[] = {
 { .compatible = "dlink,dpn-be7200gr-art" }, {}
};
MODULE_DEVICE_TABLE(of, dpn_art_match);
static struct platform_driver dpn_art_driver = {
 .probe = dpn_art_probe, .remove = dpn_art_remove,
 .driver = { .name = "dpn-bmt-art", .of_match_table = dpn_art_match },
};
module_platform_driver(dpn_art_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("DPN vendor BMT v1 fail-closed read-only logical MTD view");
