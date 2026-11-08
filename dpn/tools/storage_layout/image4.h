/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_IMAGE4_H
#define DPN_IMAGE4_H
#include "native_io.h"
#include <libfdt.h>
#include <sha1.h>
static inline void prop_string(const void *dt,int node,const char *name,const char *value){int len;const char *p=fdt_getprop(dt,node,name,&len);require(p&&len==(int)strlen(value)+1&&!memcmp(p,value,len),"exact image string property");}
static inline void prop_number(const void *dt,int node,const char *name,uint32_t value){int len;const fdt32_t *p=fdt_getprop(dt,node,name,&len);require(p&&len==4&&fdt32_to_cpu(*p)==value,"exact layout/image integer property");}
/* Caller pins complete bytes independently; this verifies their semantics. */
static inline void validate_image4(const unsigned char *b,size_t size,const char *role,const unsigned char rootsha[32]){
 require(size>0x2100&&size<=0x1000000,"normal/recovery image bounded by 16 MiB");
 require(little32(b)==0xaa640001&&little64(b+152)==0x2000,"FIP header and payload offset");
 static const unsigned char uuid[4][16]={
  {0x82,0x7e,0xe8,0x90,0xf8,0x60,0xe4,0x11,0xa1,0xb4,0x77,0x7a,0x21,0xb4,0xf9,0x4c},
  {0x8a,0xd5,0x83,0x2a,0xfb,0x60,0xe4,0x11,0x8a,0xaf,0xdf,0x30,0xbb,0xc4,0x98,0x59},
  {0x8e,0xc4,0xc1,0xf3,0x5d,0x63,0xe4,0x11,0xa7,0xa9,0x87,0xee,0x40,0xb2,0x3f,0xa7},
  {0xd6,0xd0,0xee,0xa7,0xfc,0xea,0xd5,0x4b,0x97,0x82,0x99,0x34,0xf2,0x34,0xb6,0xe4}};
 static const uint32_t offsets[]={0x400,0x1000,0x1800,0x2000};
 for(unsigned i=0;i<4;i++){const unsigned char *entry=b+16+i*40;require(!memcmp(entry,uuid[i],16)&&little64(entry+16)==offsets[i]&&little64(entry+32)==0,"canonical public FIP entries");if(i<3)require(little64(entry+24)==2&&b[offsets[i]]==0x30&&b[offsets[i]+1]==0,"public empty DER wrapper");}
 for(unsigned i=176;i<216;i++)require(b[i]==0,"FIP table terminator");
 uint64_t payload=little64(b+160);require(payload>296&&payload<=size-0x2000&&little32(b+0x2000)==0x32524448&&little32(b+0x2004)==256&&little32(b+0x2008)==payload,"FIP/HDR2 payload bounds");
 size_t n=payload-256;const void *fit=b+0x2100;require(!fdt_check_full(fit,n)&&fdt_totalsize(fit)==n,"complete FIT");
 uint32_t crc=~0U;for(size_t i=0;i<n;i++){crc^=b[0x2100+i];for(unsigned j=0;j<8;j++)crc=(crc>>1)^((0U-(crc&1))&0xedb88320U);}require(crc==little32(b+0x200c),"HDR2 CRC");
 for(size_t i=0x2100+n;i<size;i++)require(b[i]==255,"only FF after complete FIP");
 const char *names[]={"kernel@1","fdt@1","filesystem@1"};const char *types[]={"kernel","flat_dt","filesystem"};
 int images=fdt_path_offset(fit,"/images"),count=0,node;require(images>=0,"FIT images");fdt_for_each_subnode(node,fit,images)count++;require(count==3,"exact three image components");
 void *dt=NULL;int dtlen=0;
 for(unsigned i=0;i<3;i++){
  char path[64];snprintf(path,sizeof path,"/images/%s",names[i]);node=fdt_path_offset(fit,path);require(node>=0,"required image");prop_string(fit,node,"type",types[i]);prop_string(fit,node,"arch","arm64");prop_string(fit,node,"compression",i==0?"lzma":"none");
  int len;const unsigned char *data=fdt_getprop(fit,node,"data",&len);require(data&&len>0,"inline bounded image data");
  int hash=fdt_subnode_offset(fit,node,"hash@1");require(hash>=0,"FIT SHA1 node");prop_string(fit,hash,"algo","sha1");int hlen;const void *expected=fdt_getprop(fit,hash,"value",&hlen);unsigned char h[20];SHA1_CTX c;SHA1Init(&c);SHA1Update(&c,data,len);SHA1Final(h,&c);require(expected&&hlen==20&&!memcmp(expected,h,20),"FIT component SHA1");
  if(i==0){prop_string(fit,node,"os","linux");prop_number(fit,node,"load",0x8b000000);prop_number(fit,node,"entry",0x8b000000);}
  if(i==1){prop_number(fit,node,"load",0x8d000000);dtlen=len;dt=malloc(len);require(dt,"aligned DTB memory");memcpy(dt,data,len);}
  if(i==2)require(len>=96&&little32(data)==0x73717368,"container SquashFS marker");
 }
 int config=fdt_path_offset(fit,"/configurations");prop_string(fit,config,"default","conf@1");config=fdt_path_offset(fit,"/configurations/conf@1");prop_string(fit,config,"kernel","kernel@1");prop_string(fit,config,"fdt","fdt@1");
 require(dt&&!fdt_check_full(dt,dtlen),"embedded DTB structure");
 require(!fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr")&&!fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-layout4")&&!fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-persist"),"board and layout write gates");
 if(!strcmp(role,"normal")){int len;const char *first=fdt_getprop(dt,0,"compatible",&len);require(first&&len>0&&!strcmp(first,"dlink,dpn-be7200gr"),"normal board_name compatibility");}
 node=fdt_path_offset(dt,"/dpn-layout4");require(node>=0,"layout4 metadata");prop_string(dt,node,"write-profile",role);prop_number(dt,node,"format-version",4);prop_number(dt,node,"normal-slot",0);prop_number(dt,node,"recovery-slot",1);prop_number(dt,node,"vault-size",0x400000);
 int len;const void *root=fdt_getprop(dt,node,"rootfs-sha256",&len);require(root&&len==32&&(!rootsha||!memcmp(root,rootsha,32)),"actual UBI rootfs hash binding");
 int depth=0;for(node=fdt_next_node(dt,-1,&depth);node>=0;node=fdt_next_node(dt,node,&depth)){
  require(!fdt_getprop(dt,node,"local-mac-address",NULL)&&!fdt_getprop(dt,node,"mac-address",NULL)&&!fdt_getprop(dt,node,"mediatek,eeprom-data",NULL),"no embedded per-device MAC/calibration");
 }
 free(dt);
}
#endif
