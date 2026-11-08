/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_INSTALL_GUARD_H
#define DPN_INSTALL_GUARD_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/of.h>
#include <linux/string.h>
#else
#include <stdint.h>
#include <stdbool.h>
typedef uint64_t u64;
#endif
#include "dpn_slot_policy.h"
#include "dpn_stock_return_policy.h"
#include "dpn_layout4_policy.h"
#define DPN_FW_START 0x80000ULL
#define DPN_FW_END 0x1280000ULL
#define DPN_DATA_START 0xb800000ULL
#define DPN_DATA_END 0x1b800000ULL
static inline bool dpn_span(u64 off,u64 n,u64 start,u64 end){return n&&off>=start&&off<end&&n<=end-off;}
static inline bool dpn_install_range(u64 off,u64 n){return dpn_span(off,n,DPN_FW_START,DPN_FW_END)||dpn_span(off,n,DPN_DATA_START,DPN_DATA_END);}
static inline bool dpn_install_row(u64 row,bool erase){u64 off;if(row>=131072)return false;off=row*4096;return (!erase||!(row%64))&&dpn_install_range(off,erase?262144:4096);}
#ifdef __KERNEL__
static inline int dpn_kernel_write_slot(void)
{
 struct device_node *layout,*chosen;const char *args;int slot;
 layout=of_find_node_by_path("/dpn-flash-layout");
 if(!layout)return 0; /* Legacy stock-to-RAM primary installer. */
 if(!of_property_read_bool(layout,"slot-relative-root")){of_node_put(layout);return 0;}
 of_node_put(layout);
 chosen=of_find_node_by_path("/chosen");if(!chosen)return -1;
 if(of_property_read_string(chosen,"bootargs",&args)){of_node_put(chosen);return -1;}
 slot=dpn_cmdline_slot(args);of_node_put(chosen);return slot;
}
static inline int dpn_kernel_layout4_permissions(void)
{
 struct device_node *node,*chosen;const char *role,*args;u32 version,normal,recovery,vault;int permission=0;
 if(of_machine_is_compatible("dlink,dpn-be7200gr-layout4")) {
  node=of_find_node_by_path("/dpn-layout4");if(!node)return -1;
  if(of_property_read_u32(node,"format-version",&version)||version!=4 ||
     of_property_read_u32(node,"normal-slot",&normal)||normal!=0 ||
     of_property_read_u32(node,"recovery-slot",&recovery)||recovery!=1 ||
     of_property_read_u32(node,"vault-size",&vault)||vault!=0x400000 ||
     of_property_read_string(node,"write-profile",&role))permission=-1;
  else if(!strcmp(role,"normal")||!strcmp(role,"recovery"))permission=7;
  else if(!strcmp(role,"provision"))permission=15;
  else permission=-1;
  of_node_put(node);return permission;
 }
 chosen=of_find_node_by_path("/chosen");if(!chosen)return 0;
 if(!of_property_read_string(chosen,"bootargs",&args))permission=dpn_layout4_trial_permissions(args);
 of_node_put(chosen);
 if(permission>0 && (!of_machine_is_compatible("dlink,dpn-be7200gr-install") ||
                    !of_machine_is_compatible("dlink,dpn-be7200gr-ram") ||
                    of_machine_is_compatible("dlink,dpn-be7200gr-stock-return")))return -1;
 return permission;
}
static inline bool dpn_write_range(u64 off,u64 n)
{
 int permission=dpn_kernel_layout4_permissions();
 if(permission)return permission>0 && dpn_layout4_range(off,n,permission);
 if(of_machine_is_compatible("dlink,dpn-be7200gr-stock-return")) {
  struct device_node *layout;u32 target;int slot=dpn_kernel_write_slot();bool valid;
  layout=of_find_node_by_path("/dpn-flash-layout");
  if(!layout)return false;
  valid=of_property_read_bool(layout,"stock-return-only") &&
        of_property_read_bool(layout,"slot-relative-root") &&
        !of_property_read_u32(layout,"stock-return-target-slot",&target);
  of_node_put(layout);
  return valid && target<=1 && slot==(int)target && dpn_stock_return_range(off,n,slot);
 }
 return of_machine_is_compatible("dlink,dpn-be7200gr-install") && dpn_slot_write_range(off,n,dpn_kernel_write_slot());
}
static inline bool dpn_write_row(u64 row,bool erase)
{
 u64 off;if(row>=131072 || (erase && row%64))return false;
 off=row*4096;
 return dpn_write_range(off,erase?262144:4096);
}
#endif
#endif
