// SPDX-License-Identifier: GPL-2.0-only
/* Layout4 typed views. Raw physical NAND remains RO. No BMT/table writer. */
#include <linux/module.h>
#include <linux/mtd/mtd.h>
#include <linux/mtd/concat.h>
#include <linux/of.h>
#include <linux/mutex.h>
#include <linux/namei.h>
#include <linux/statfs.h>
#include <linux/magic.h>
#include <linux/slab.h>
#include <linux/unaligned.h>
#include "dpn_install_guard.h"
enum { NORMAL,RECOVERY,VAULT,DATA_A,DATA_B,FLAG,STOCK_FIRMWARE,VENDOR_STATE,SCRATCH_A,SCRATCH_B,PROVISION_TARGET,NVIEWS };
struct view {struct mtd_info mtd;u64 base;bool writable;};
static struct view views[NVIEWS];
static struct mtd_info *source,*joined,*scratch_joined;
static unsigned long registered;
static bool data_write,update,provision,stock_return,flag_write,scratch_write;
module_param(data_write,bool,0400);module_param(update,bool,0400);
module_param(provision,bool,0400);module_param(stock_return,bool,0400);
module_param(flag_write,bool,0400);
module_param(scratch_write,bool,0400);
static DEFINE_MUTEX(io_lock);
extern bool dpn_factory_write_eligible(void);

static int read_view(struct mtd_info *mtd,loff_t off,size_t len,size_t *done,u_char *buf)
{
 struct view *v=container_of(mtd,struct view,mtd);struct mtd_ecc_stats before;int r;
 *done=0;if(off<0||off>mtd->size||len>mtd->size-off)return -EINVAL;
 mutex_lock(&io_lock);before=source->ecc_stats;r=mtd_read(source,v->base+off,len,done,buf);
 mtd->ecc_stats.corrected+=source->ecc_stats.corrected-before.corrected;
 mtd->ecc_stats.failed+=source->ecc_stats.failed-before.failed;
 mutex_unlock(&io_lock);return r;
}
static int flag_block_clean(void)
{
 u8 *b;size_t done;int r;unsigned i;
 b=kvmalloc(262144,GFP_KERNEL);if(!b)return -ENOMEM;
 r=mtd_read(source,DPN_L4_FLAG_START,262144,&done,b);
 if(r&&!mtd_is_bitflip(r))goto out;
 if(done!=262144){r=-EIO;goto out;}
 if(b[0]!='0'&&b[0]!='1'&&b[0]!=255){r=-EINVAL;goto out;}
 for(i=1;i<262144;i++)if(b[i]!=255){r=-EINVAL;goto out;}
 r=0;
out:kvfree(b);return r;
}
static int write_view(struct mtd_info *mtd,loff_t off,size_t len,size_t *done,const u_char *buf)
{
 struct view *v=container_of(mtd,struct view,mtd);
 struct mtd_oob_ops ops={.mode=MTD_OPS_PLACE_OOB,.len=len,.datbuf=(u_char *)buf};int r;
 *done=0;
 if(!v->writable||off<0||!len||off>=mtd->size||len>mtd->size-off||off%4096||len%4096||!dpn_write_range(v->base+off,len))return -EINVAL;
 if(v==&views[FLAG]){
  if(off||len!=4096||(buf[0]!='0'&&buf[0]!='1'))return -EINVAL;
  for(unsigned i=1;i<len;i++)if(buf[i]!=255)return -EINVAL;
 }
 mutex_lock(&io_lock);
 if(v==&views[FLAG]){r=flag_block_clean();if(r)goto out;}
 r=source->_write_oob(source,v->base+off,&ops);*done=ops.retlen;
out:mutex_unlock(&io_lock);return r;
}
static int erase_view(struct mtd_info *mtd,struct erase_info *e)
{
 struct view *v=container_of(mtd,struct view,mtd);struct erase_info physical=*e;int r;
 if(!v->writable||!e->len||e->addr>=mtd->size||e->len>mtd->size-e->addr||
    e->addr%262144||e->len%262144||!dpn_write_range(v->base+e->addr,e->len))return -EINVAL;
 if(v==&views[FLAG]&&(e->addr||e->len!=262144))return -EINVAL;
 physical.addr+=v->base;mutex_lock(&io_lock);
 if(v==&views[FLAG]){r=flag_block_clean();if(r)goto out;}
 r=source->_erase(source,&physical);
 if(r&&physical.fail_addr!=MTD_FAIL_ADDR_UNKNOWN)e->fail_addr=physical.fail_addr-v->base;
out:mutex_unlock(&io_lock);return r;
}
static int isbad_view(struct mtd_info *mtd,loff_t off)
{
 struct view *v=container_of(mtd,struct view,mtd);
 if(off<0||off>=mtd->size)return -EINVAL;
 return mtd_block_isbad(source,v->base+off);
}
static int markbad_view(struct mtd_info *mtd,loff_t off)
{
 struct view *v=container_of(mtd,struct view,mtd);int r;
 if(!v->writable||(v!=&views[DATA_A]&&v!=&views[DATA_B])||off<0||off>=mtd->size||off%262144||!dpn_write_range(v->base+off,4096))return -EINVAL;
 mutex_lock(&io_lock);r=source->_block_markbad(source,v->base+off);mutex_unlock(&io_lock);return r;
}
static bool ram_root(void)
{
 struct path path;struct kstatfs st;int r=kern_path("/",LOOKUP_FOLLOW,&path);
 if(r)return false;
 r=vfs_statfs(&path,&st);path_put(&path);
 return !r&&(st.f_type==TMPFS_MAGIC||st.f_type==RAMFS_MAGIC);
}
static void unregister_views(void)
{
 if(scratch_joined){mtd_device_unregister(scratch_joined);mtd_concat_destroy(scratch_joined);scratch_joined=NULL;}
 if(joined){mtd_device_unregister(joined);mtd_concat_destroy(joined);joined=NULL;}
 for(int i=NVIEWS-1;i>=0;i--)if(registered&BIT(i)){mtd_device_unregister(&views[i].mtd);registered&=~BIT(i);}
}
static bool legacy_scratch_eligible(void)
{
 struct device_node *node;u32 layout;u8 header[216],hdr2[16];size_t done;u64 payload;int r;
 node=of_find_node_by_path("/dpn-layout4");if(node){of_node_put(node);return false;}
 node=of_find_node_by_path("/dpn-flash-layout");if(!node)return false;
 r=of_property_read_u32(node,"upgrade-layout",&layout);of_node_put(node);
 if(r||layout!=3||dpn_kernel_write_slot()!=0)return false;
 r=mtd_read(source,0x80000,sizeof header,&done,header);
 if((r&&!mtd_is_bitflip(r))||done!=sizeof header)return false;
 payload=get_unaligned_le64(header+160);
 r=mtd_read(source,0x82000,sizeof hdr2,&done,hdr2);
 if((r&&!mtd_is_bitflip(r))||done!=sizeof hdr2)return false;
 return get_unaligned_le32(header)==0xaa640001 && get_unaligned_le32(hdr2)==0x32524448 &&
        get_unaligned_le32(hdr2+4)==256 && get_unaligned_le32(hdr2+8)==payload &&
        payload>256 && payload<=0x1200000-0x2000;
}
static int register_view(unsigned which,const char *name,u64 base,u64 bytes,bool writable)
{
 struct view *v=&views[which];struct mtd_info *m=&v->mtd;int r;
 if(writable&&!dpn_write_range(base,bytes))return -EPERM;
 v->base=base;v->writable=writable;
 *m=(struct mtd_info){.name=name,.type=MTD_NANDFLASH,.flags=writable?MTD_CAP_NANDFLASH:MTD_NO_ERASE,
  .size=bytes,.writesize=4096,.writebufsize=4096,.erasesize=262144,.oobsize=256,
  .oobavail=source->oobavail,.ecc_strength=source->ecc_strength,.ecc_step_size=source->ecc_step_size,
  .bitflip_threshold=source->bitflip_threshold,.owner=THIS_MODULE,._read=read_view,._block_isbad=isbad_view};
 m->dev.parent=&source->dev;
 if(writable){m->_write=write_view;m->_erase=erase_view;if(which==DATA_A||which==DATA_B)m->_block_markbad=markbad_view;}
 r=mtd_device_register(m,NULL,0);if(r)return r;registered|=BIT(which);return 0;
}
static int __init start(void)
{
 int r,permissions=dpn_kernel_layout4_permissions();struct mtd_info *existing,*parts[2];
 bool writes=data_write||update||provision||stock_return||flag_write||scratch_write;
 if(!of_machine_is_compatible("dlink,dpn-be7200gr"))return -ENODEV;
 if(writes&&permissions<=0)return -EPERM;
 if((update||provision||stock_return||scratch_write)&&!ram_root())return -EPERM;
 if(scratch_write&&(data_write||update||provision||stock_return||flag_write))return -EINVAL;
 if(stock_return&&(data_write||update||provision))return -EINVAL;
 if(provision&&!(permissions&DPN_L4_ALLOW_PROVISION))return -EPERM;
 existing=get_mtd_device(NULL,2);if(!IS_ERR(existing)){put_mtd_device(existing);return -EBUSY;}
 source=get_mtd_device(NULL,0);if(IS_ERR(source))return PTR_ERR(source);
 if(strcmp(source->name,"dpn-physical-nand-ro")||source->flags&MTD_WRITEABLE||source->type!=MTD_NANDFLASH||
    source->size!=DPN_L4_CHIP_END||source->writesize!=4096||source->erasesize!=262144||source->oobsize!=256||
    !source->_write_oob||!source->_erase||!source->_block_markbad){r=-EINVAL;goto fail;}
 if(writes&&!dpn_factory_write_eligible()){r=-EOPNOTSUPP;goto fail;}
 if(scratch_write&&!legacy_scratch_eligible()){r=-EPERM;goto fail;}
 if(flag_write){r=flag_block_clean();if(r)goto fail;}
 r=register_view(RECOVERY,"dpn-layout4-recovery",DPN_L4_RECOVERY_START,0x1000000,provision);if(r)goto fail;
 r=register_view(VAULT,"dpn-layout4-vault",DPN_L4_VAULT_START,0x400000,provision);if(r)goto fail;
 r=register_view(FLAG,"dpn-layout4-bootflag",DPN_L4_FLAG_START,0x40000,flag_write);if(r)goto fail;
 if(stock_return){
  r=register_view(STOCK_FIRMWARE,"dpn-layout4-stock-target",0x80000,0x3200000,true);if(r)goto fail;
  r=register_view(VENDOR_STATE,"dpn-layout4-vendor-target",0x6480000,0x5380000,true);if(r)goto fail;
 }else{
  r=register_view(NORMAL,"dpn-layout4-normal",DPN_L4_NORMAL_START,0x1000000,update);if(r)goto fail;
  r=register_view(DATA_A,"dpn-layout4-data-a",DPN_L4_DATA_A_START,0x2200000,data_write);if(r)goto fail;
  r=register_view(DATA_B,"dpn-layout4-data-b",DPN_L4_DATA_B_START,0x17600000,data_write);if(r)goto fail;
  parts[0]=&views[DATA_A].mtd;parts[1]=&views[DATA_B].mtd;joined=mtd_concat_create(parts,2,"dpn-layout4-data");
  if(!joined){r=-ENOMEM;goto fail;}
  if(joined->size!=DPN_L4_DATA_BYTES||!!(joined->flags&MTD_WRITEABLE)!=data_write){mtd_concat_destroy(joined);joined=NULL;r=-EINVAL;goto fail;}
  joined->owner=THIS_MODULE;r=mtd_device_register(joined,NULL,0);
  if(r){mtd_concat_destroy(joined);joined=NULL;goto fail;}
  if(provision){
   r=register_view(PROVISION_TARGET,"dpn-layout4-provision-target",DPN_L4_RECOVERY_START,0x1400000,true);if(r)goto fail;
  }
  if(scratch_write){
   r=register_view(SCRATCH_A,"dpn-layout4-scratch-a",0x1480000,0x800000,true);if(r)goto fail;
   r=register_view(SCRATCH_B,"dpn-layout4-scratch-b",0x2480000,0x800000,true);if(r)goto fail;
   parts[0]=&views[SCRATCH_A].mtd;parts[1]=&views[SCRATCH_B].mtd;
   scratch_joined=mtd_concat_create(parts,2,"dpn-layout4-scratch");
   if(!scratch_joined){r=-ENOMEM;goto fail;}
   scratch_joined->owner=THIS_MODULE;
   r=mtd_device_register(scratch_joined,NULL,0);
   if(r){mtd_concat_destroy(scratch_joined);scratch_joined=NULL;goto fail;}
  }
 }
 pr_info("dpn-layout4: typed views, data_write=%u update=%u provision=%u stock_return=%u flag_write=%u; bootloader/ART outside flag/BMT excluded\n",data_write,update,provision,stock_return,flag_write);return 0;
fail:unregister_views();put_mtd_device(source);return r;
}
static void __exit stop(void){unregister_views();put_mtd_device(source);}
module_init(start);module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Typed layout4 data, firmware, per-device vault and stock-return views");
