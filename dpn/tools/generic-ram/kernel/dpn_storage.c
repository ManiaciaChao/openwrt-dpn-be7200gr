// SPDX-License-Identifier: GPL-2.0-only
/* Read-only whole-chip source + bounded config and optional installer views.
 * No BMT updates, partition parser, unlock or writes outside the two windows.
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/mtd/mtd.h>
#include <linux/slab.h>
#include <linux/mutex.h>
#include <linux/namei.h>
#include <linux/magic.h>
#include <linux/statfs.h>
#include "../../../drafts/nand/dpn_bmt_v1_ro.h"
#include "../../../drafts/nand/dpn_persist_guard.h"
#include "dpn_slot.h"
#include "dpn_install_guard.h"
static struct mtd_info *source;
static struct mtd_info root, config;
static u32 root_start, root_size;
static u32 firmware_start=0x80000;
static u64 cfg_start=0xb800000,cfg_size=0x10000000;
static unsigned int root_slot;
module_param(root_slot,uint,0400);
static bool config_readonly;
module_param(config_readonly,bool,0400);
static bool install;
module_param(install,bool,0400);
extern bool dpn_factory_write_eligible(void);
static DEFINE_MUTEX(io_lock);
static const char * const no_parsers[]={NULL};
static int read_view(struct mtd_info *mtd,loff_t off,size_t len,size_t *ret,u_char *buf)
{
 u64 base=mtd==&config?cfg_start:(install?firmware_start:root_start);
 struct mtd_ecc_stats before;int r;
 *ret=0;if(off<0||off>mtd->size||len>mtd->size-off)return -EINVAL;
 mutex_lock(&io_lock);before=source->ecc_stats;
 r=mtd_read(source,base+off,len,ret,buf);
 mtd->ecc_stats.corrected+=source->ecc_stats.corrected-before.corrected;
 mtd->ecc_stats.failed+=source->ecc_stats.failed-before.failed;
 mutex_unlock(&io_lock);return r;
}
static bool range(loff_t off,u64 bytes)
{
 return off>=0&&bytes;
}
static int write_config(struct mtd_info *mtd,loff_t off,size_t len,size_t *ret,const u_char *buf)
{
 struct mtd_oob_ops ops={.mode=MTD_OPS_PLACE_OOB,.len=len,.datbuf=(u_char *)buf};
 int r;*ret=0;
 if(!range(off,len)||off>=mtd->size||len>mtd->size-off||off%4096||len%4096)return -EINVAL;
 /* Intentional direct callback: source remains RO to all generic users.
  * Core and SPI controller independently reject rows outside this window. */
 mutex_lock(&io_lock);r=source->_write_oob(source,(mtd==&config?cfg_start:firmware_start)+off,&ops);mutex_unlock(&io_lock);
 *ret=ops.retlen;return r;
}
static int erase_config(struct mtd_info *mtd,struct erase_info *e)
{
 struct erase_info physical=*e;int r;
 if(!range(e->addr,e->len)||e->addr>=mtd->size||e->len>mtd->size-e->addr||e->addr%262144||e->len%262144)return -EINVAL;
 physical.addr+=(mtd==&config?cfg_start:firmware_start);
 mutex_lock(&io_lock);r=source->_erase(source,&physical);mutex_unlock(&io_lock);
 if(r&&physical.fail_addr!=MTD_FAIL_ADDR_UNKNOWN)e->fail_addr=physical.fail_addr-(mtd==&config?cfg_start:firmware_start);
 return r;
}
static int config_isbad(struct mtd_info *mtd,loff_t off)
{
 u64 block;u8 mark[2];int p,r=0;
 if(off<0||off>=mtd->size)return -EINVAL;
 block=(mtd==&config?cfg_start:firmware_start)+(off&~(DPN_CFG_BLOCK-1));
 mutex_lock(&io_lock);
 for(p=0;p<2;p++) {
  struct mtd_oob_ops ops={.mode=MTD_OPS_PLACE_OOB,.ooblen=2,.oobbuf=mark};
  r=mtd_read_oob(source,block+p*4096,&ops);
  if(r&&!mtd_is_bitflip(r))break;
  if(ops.oobretlen!=2){r=-EIO;break;}
  r=(mark[0]!=255||mark[1]!=255);if(r)break;
 }
 mutex_unlock(&io_lock);return r;
}
static int config_markbad(struct mtd_info *mtd,loff_t off)
{
 int r;if(mtd!=&config||!range(off,1)||off>=cfg_size)return -EINVAL;
 off&=~(DPN_CFG_BLOCK-1);
 mutex_lock(&io_lock);r=source->_block_markbad(source,cfg_start+off);mutex_unlock(&io_lock);return r;
}

static int __init start(void)
{
 struct device_node *node;int r=-EINVAL;
 /* Recovery may read owner identity before detaching UBI. It must never
  * expose the usual writable CFG or 18 MiB installation view. */
 if(of_machine_is_compatible("dlink,dpn-be7200gr-stock-return") &&
    (!config_readonly || install))return -EPERM;
 if(!of_machine_is_compatible("dlink,dpn-be7200gr-install")||!IS_ENABLED(CONFIG_MTD_PARTITIONED_MASTER))return -ENODEV;
 if(root_slot>1 || (install && config_readonly))return -EINVAL;
 if(install && dpn_kernel_write_slot()!=(int)root_slot)return -EPERM;
 firmware_start=dpn_firmware_base(root_slot);
 if(install) {
  struct path path;
  struct kstatfs st;
  r=kern_path("/",LOOKUP_FOLLOW,&path);
  if(r)return r;
  r=vfs_statfs(&path,&st);path_put(&path);
  if(r)return r;
  if(st.f_type!=TMPFS_MAGIC&&st.f_type!=RAMFS_MAGIC)return -EPERM;
 }
 if(!dpn_factory_write_eligible())return -EOPNOTSUPP;
 if(!install) {
  node=of_find_node_by_path("/dpn-flash-layout");if(!node)return -EINVAL;
  r=of_property_read_u32(node,"rootfs-offset",&root_start);
  if(!r)r=of_property_read_u32(node,"rootfs-size",&root_size);
  if(!r && root_slot && !of_property_read_bool(node,"slot-relative-root"))r=-EINVAL;
  of_node_put(node);
  if(r || dpn_slot_root(root_start,root_size,root_slot,&root_start))return -EINVAL;
 }
 source=get_mtd_device(NULL,0);if(IS_ERR(source))return PTR_ERR(source);
 if(strcmp(source->name,"dpn-physical-nand-ro")||source->flags&MTD_WRITEABLE||source->size!=0x20000000ULL||source->writesize!=4096||source->erasesize!=262144||source->oobsize!=256){r=-EINVAL;goto fail;}
 root=(struct mtd_info){.name=install?"dpn-firmware-update":"dpn-rootfs",.type=MTD_NANDFLASH,.flags=install?MTD_CAP_NANDFLASH:MTD_NO_ERASE,.size=install?0x1200000:root_size,.erasesize=262144,.writesize=4096,.writebufsize=4096,.oobsize=256,.oobavail=source->oobavail,.owner=THIS_MODULE,._read=read_view};
 if(install){root._write=write_config;root._erase=erase_config;root._block_isbad=config_isbad;}
 root.dev.parent=&source->dev;r=mtd_device_parse_register(&root,no_parsers,NULL,NULL,0);if(r)goto fail;
 if(root.index!=2){r=-EINVAL;goto unroot;}
 config=(struct mtd_info){.name="dpn-config",.type=MTD_NANDFLASH,.flags=config_readonly?MTD_NO_ERASE:MTD_CAP_NANDFLASH,.size=cfg_size,.erasesize=262144,.writesize=4096,.writebufsize=4096,.oobsize=256,.oobavail=source->oobavail,.ecc_strength=source->ecc_strength,.ecc_step_size=source->ecc_step_size,.bitflip_threshold=source->bitflip_threshold,.owner=THIS_MODULE,._read=read_view,._write=config_readonly?NULL:write_config,._erase=config_readonly?NULL:erase_config,._block_isbad=config_isbad,._block_markbad=config_readonly?NULL:config_markbad};
 config.dev.parent=&source->dev;r=mtd_device_parse_register(&config,no_parsers,NULL,NULL,0);if(r)goto unroot;
 if(config.index!=3){mtd_device_unregister(&config);r=-EINVAL;goto unroot;}
 pr_info("dpn-storage: %s; slot %u firmware [%x,%x), config [b800000,1b800000); factory counterpart excluded\n",install?"explicit installer views":"persistent views",root_slot,firmware_start,firmware_start+0x1200000);return 0;
unroot:mtd_device_unregister(&root);
fail:put_mtd_device(source);return r;
}
static void __exit stop(void){mtd_device_unregister(&config);mtd_device_unregister(&root);put_mtd_device(source);}
module_init(start);module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("DPN bounded installation and persistent storage views");
