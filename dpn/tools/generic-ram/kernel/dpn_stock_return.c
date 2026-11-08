// SPDX-License-Identifier: GPL-2.0-only
/* Explicit RAM-only view for stock restoration; no config or OOB writer. */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/mtd/mtd.h>
#include <linux/magic.h>
#include <linux/namei.h>
#include <linux/statfs.h>
#include <linux/mutex.h>
#include "dpn_install_guard.h"

static struct mtd_info *source;
static struct mtd_info view;
static u64 base;
static unsigned int target_slot;
module_param(target_slot,uint,0400);
static DEFINE_MUTEX(io_lock);
extern bool dpn_factory_write_eligible(void);

static int read_view(struct mtd_info *mtd,loff_t off,size_t len,size_t *ret,u_char *buf)
{
 struct mtd_ecc_stats before;int r;
 *ret=0;
 if(off<0 || off>mtd->size || len>mtd->size-off)return -EINVAL;
 mutex_lock(&io_lock);before=source->ecc_stats;
 r=mtd_read(source,base+off,len,ret,buf);
 mtd->ecc_stats.corrected+=source->ecc_stats.corrected-before.corrected;
 mtd->ecc_stats.failed+=source->ecc_stats.failed-before.failed;
 mutex_unlock(&io_lock);return r;
}
static int write_view(struct mtd_info *mtd,loff_t off,size_t len,size_t *ret,const u_char *buf)
{
 struct mtd_oob_ops ops={.mode=MTD_OPS_PLACE_OOB,.len=len,.datbuf=(u_char *)buf};int r;
 *ret=0;
 if(off<0 || !len || off>=mtd->size || len>mtd->size-off || off%4096 || len%4096 ||
    !dpn_write_range(base+off,len))return -EINVAL;
 mutex_lock(&io_lock);r=source->_write_oob(source,base+off,&ops);mutex_unlock(&io_lock);
 *ret=ops.retlen;return r;
}
static int erase_view(struct mtd_info *mtd,struct erase_info *e)
{
 struct erase_info physical=*e;int r;
 if(!e->len || e->addr>=mtd->size || e->len>mtd->size-e->addr ||
    e->addr%262144 || e->len%262144 || !dpn_write_range(base+e->addr,e->len))return -EINVAL;
 physical.addr+=base;
 mutex_lock(&io_lock);r=source->_erase(source,&physical);mutex_unlock(&io_lock);
 if(r && physical.fail_addr!=MTD_FAIL_ADDR_UNKNOWN)e->fail_addr=physical.fail_addr-base;
 return r;
}
static int isbad_view(struct mtd_info *mtd,loff_t off)
{
 int r,p;u8 mark[2];u64 block;
 if(off<0 || off>=mtd->size)return -EINVAL;
 block=base+(off&~(262144ULL-1));
 for(p=0;p<2;p++) {
  struct mtd_oob_ops ops={.mode=MTD_OPS_PLACE_OOB,.ooblen=2,.oobbuf=mark};
  r=mtd_read_oob(source,block+p*4096,&ops);
  if(r && !mtd_is_bitflip(r))return r;
  if(ops.oobretlen!=2)return -EIO;
  if(mark[0]!=255 || mark[1]!=255)return 1;
 }
 return 0;
}
static int __init start(void)
{
 struct path path;struct kstatfs st;u64 off;int r;
 if(!of_machine_is_compatible("dlink,dpn-be7200gr-stock-return") || target_slot>1 ||
    dpn_kernel_write_slot()!=(int)target_slot)return -EPERM;
 base=dpn_firmware_base(target_slot);
 if(!dpn_write_range(base,DPN_STOCK_SLOT_BYTES) || dpn_write_range(0xb800000,4096))return -EPERM;
 r=kern_path("/",LOOKUP_FOLLOW,&path);if(r)return r;
 r=vfs_statfs(&path,&st);path_put(&path);if(r)return r;
 if(st.f_type!=TMPFS_MAGIC && st.f_type!=RAMFS_MAGIC)return -EPERM;
 /* The loader must unload persistent storage before exposing this view. */
 for(r=2;r<4;r++) {
  struct mtd_info *existing=get_mtd_device(NULL,r);
  if(!IS_ERR(existing)){put_mtd_device(existing);return -EBUSY;}
 }
 if(!dpn_factory_write_eligible())return -EOPNOTSUPP;
 source=get_mtd_device(NULL,0);if(IS_ERR(source))return PTR_ERR(source);
 if(source->size!=0x20000000ULL || source->writesize!=4096 ||
    source->erasesize!=262144 || source->oobsize!=256 || source->type!=MTD_NANDFLASH ||
    source->flags&MTD_WRITEABLE || !source->_write_oob || !source->_erase){r=-EINVAL;goto fail;}
 view.name="dpn-stock-return-target";view.type=source->type;
 view.flags=MTD_CAP_NANDFLASH;view.size=DPN_STOCK_SLOT_BYTES;
 view.writesize=source->writesize;view.writebufsize=source->writebufsize;
 view.erasesize=source->erasesize;view.oobsize=source->oobsize;
 view.ecc_strength=source->ecc_strength;view.ecc_step_size=source->ecc_step_size;
 view.owner=THIS_MODULE;view._read=read_view;view._write=write_view;
 view._erase=erase_view;view._block_isbad=isbad_view;
 for(off=0;off<view.size;off+=view.erasesize){r=isbad_view(&view,off);if(r){r=r<0?r:-EIO;goto fail;}}
 r=mtd_device_register(&view,NULL,0);if(r)goto fail;
 if(view.index!=2){mtd_device_unregister(&view);r=-EINVAL;goto fail;}
 pr_info("dpn-stock-return: explicit RAM target slot %u [%llx,%llx); CFG and other slot excluded\n",
         target_slot,base,base+DPN_STOCK_SLOT_BYTES);return 0;
fail:put_mtd_device(source);return r;
}
static void __exit stop(void){mtd_device_unregister(&view);put_mtd_device(source);}
module_init(start);module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("DPN RAM-only bounded full-slot stock-return view");
