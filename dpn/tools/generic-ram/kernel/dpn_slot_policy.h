/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_SLOT_POLICY_H
#define DPN_SLOT_POLICY_H
/* Match complete boot tokens; never infer an active slot from a mutable file. */
static inline int dpn_token_equal(const char *p, unsigned len, const char *s)
{
 unsigned i=0;
 while(s[i]) { if(i>=len || p[i]!=s[i])return 0;i++; }
 return i==len;
}
static inline int dpn_cmdline_slot(const char *line)
{
 unsigned i=0,start,n,flags=0,roots=0;int flag=-1,root=-1;
 while(line[i]) {
  if(i>=4096)return -1;
  if(line[i]==' '||line[i]=='\t'||line[i]=='\n'){i++;continue;}
  start=i;
  while(line[i]&&line[i]!=' '&&line[i]!='\t'&&line[i]!='\n'){if(i>=4096)return -1;i++;}
  n=i-start;
  if(n>=9 && line[start]=='b'&&line[start+1]=='o'&&line[start+2]=='o'&&line[start+3]=='t'&&line[start+4]=='f'&&line[start+5]=='l'&&line[start+6]=='a'&&line[start+7]=='g'&&line[start+8]=='=') {
   flags++;
   if(dpn_token_equal(line+start,n,"bootflag=0"))flag=0;
   else if(dpn_token_equal(line+start,n,"bootflag=1"))flag=1;
   else return -1;
  }
  if(n>=5 && line[start]=='r'&&line[start+1]=='o'&&line[start+2]=='o'&&line[start+3]=='t'&&line[start+4]=='=') {
   roots++;
   if(dpn_token_equal(line+start,n,"root=/dev/mtdblock3"))root=0;
   else if(dpn_token_equal(line+start,n,"root=/dev/mtdblock6"))root=1;
   else return -1;
  }
 }
 return flags==1 && roots==1 && flag==root?flag:-1;
}
static inline unsigned dpn_firmware_base(unsigned slot) { return slot?0x3280000U:0x80000U; }
static inline int dpn_slot_write_range(unsigned long long off,unsigned long long bytes,int slot)
{
 unsigned long long base;
 if(!bytes)return 0;
 if(off>=0xb800000ULL && off<0x1b800000ULL && bytes<=0x1b800000ULL-off)return 1;
 if(slot<0||slot>1)return 0;
 base=dpn_firmware_base((unsigned)slot);
 return off>=base && off<base+0x1200000ULL && bytes<=base+0x1200000ULL-off;
}
#endif
