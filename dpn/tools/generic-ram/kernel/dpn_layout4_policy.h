/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_LAYOUT4_POLICY_H
#define DPN_LAYOUT4_POLICY_H
#include "dpn_slot_policy.h"
/* Candidate geometry. Not activated by the layout-3 kernel or installer. */
#define DPN_L4_CHIP_END 0x20000000ULL
#define DPN_L4_NORMAL_START 0x80000ULL
#define DPN_L4_NORMAL_END 0x1080000ULL
#define DPN_L4_DATA_A_START 0x1080000ULL
#define DPN_L4_DATA_A_END 0x3280000ULL
#define DPN_L4_RECOVERY_START 0x3280000ULL
#define DPN_L4_RECOVERY_END 0x4280000ULL
#define DPN_L4_VAULT_START 0x4280000ULL
#define DPN_L4_VAULT_END 0x4680000ULL
#define DPN_L4_DATA_B_START 0x4680000ULL
#define DPN_L4_DATA_B_END 0x1bc80000ULL
#define DPN_L4_DATA_BYTES 0x19800000ULL
#define DPN_L4_FLAG_START 0x1bfc0000ULL
#define DPN_L4_FLAG_END 0x1c000000ULL
#define DPN_L4_ALLOW_DATA 1U
#define DPN_L4_ALLOW_NORMAL 2U
#define DPN_L4_ALLOW_FLAG 4U
#define DPN_L4_ALLOW_PROVISION 8U
static inline int dpn_layout4_range(unsigned long long off,unsigned long long bytes,unsigned permissions)
{
 static const struct {unsigned long long start,end;unsigned permission;} windows[]={
  {DPN_L4_NORMAL_START,DPN_L4_NORMAL_END,DPN_L4_ALLOW_NORMAL},
  {DPN_L4_DATA_A_START,DPN_L4_DATA_A_END,DPN_L4_ALLOW_DATA},
  {DPN_L4_RECOVERY_START,DPN_L4_RECOVERY_END,DPN_L4_ALLOW_PROVISION},
  {DPN_L4_VAULT_START,DPN_L4_VAULT_END,DPN_L4_ALLOW_PROVISION},
  {DPN_L4_DATA_B_START,DPN_L4_DATA_B_END,DPN_L4_ALLOW_DATA},
  {DPN_L4_FLAG_START,DPN_L4_FLAG_END,DPN_L4_ALLOW_FLAG},
 };
 unsigned i;
 if(!bytes || permissions&~15U || off>=DPN_L4_CHIP_END || bytes>DPN_L4_CHIP_END-off)return 0;
 for(i=0;i<sizeof(windows)/sizeof(windows[0]);i++) {
  unsigned long long take;
  if(off>=windows[i].end)continue;
  if(off<windows[i].start || !(permissions&windows[i].permission))return 0;
  take=windows[i].end-off;if(take>bytes)take=bytes;
  off+=take;bytes-=take;if(!bytes)return 1;
 }
 return 0;
}
static inline int dpn_layout4_row(unsigned long long row,int erase,unsigned permissions)
{
 if(row>=131072 || (erase&&row%64))return 0;
 return dpn_layout4_range(row*4096,erase?262144:4096,permissions);
}
/* Explicit laboratory kernel command line only. Absence preserves layout 3;
 * malformed/duplicate requests fail closed and never select a legacy window. */
static inline int dpn_layout4_trial_permissions(const char *line)
{
 unsigned i=0,start,n,trials=0,selftests=0;int permission=-1,selftest=0;
 static const char key[]="dpn_layout4_trial=";
 static const char testkey[]="dpn_vault_selftest=";
 while(line[i]) {
  unsigned k;
  if(i>=4096)return -1;
  if(line[i]==' '||line[i]=='\t'||line[i]=='\n'){i++;continue;}
  start=i;
  while(line[i]&&line[i]!=' '&&line[i]!='\t'&&line[i]!='\n'){if(i>=4096)return -1;i++;}
  n=i-start;
  for(k=0;k<sizeof(key)-1&&k<n&&line[start+k]==key[k];k++);
  if(k==sizeof(key)-1){
   trials++;
   if(dpn_token_equal(line+start,n,"dpn_layout4_trial=provision"))permission=15;
   else if(dpn_token_equal(line+start,n,"dpn_layout4_trial=normal") ||
           dpn_token_equal(line+start,n,"dpn_layout4_trial=recovery"))permission=7;
   else permission=-1;
  }
  for(k=0;k<sizeof(testkey)-1&&k<n&&line[start+k]==testkey[k];k++);
  if(k==sizeof(testkey)-1){selftests++;selftest=dpn_token_equal(line+start,n,"dpn_vault_selftest=1");}
 }
 if(!trials)return 0;
 return trials==1&&selftests==1&&selftest&&dpn_cmdline_slot(line)>=0?permission:-1;
}
#endif
