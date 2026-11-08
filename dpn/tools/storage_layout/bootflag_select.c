/* SPDX-License-Identifier: GPL-2.0-only */
/* Only the original selector eraseblock; no U-Boot environment writer. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <mtd/mtd-user.h>
#include <sha2.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#define ART 0x1bc80000ULL
#define ART_SIZE 0x380000U
#define FLAG 0x340000U
#define BLOCK 0x40000U
static unsigned mutations;
static void need(bool b,const char *s){if(!b){fprintf(stderr,"BOOTFLAG_STOP %s errno=%d mutations=%u\n",s,errno,mutations);exit(2);}}
static void rd(int f,void *b,size_t n,unsigned long long o){unsigned char *p=b;while(n){ssize_t k=pread(f,p,n,o);need(k>0,"complete read");p+=k;n-=k;o+=k;}}
static void normalized_sha(unsigned char *b,char out[65]){unsigned char h[32],saved=b[FLAG];b[FLAG]='0';SHA2_CTX c;SHA256Init(&c);SHA256Update(&c,b,ART_SIZE);SHA256Final(h,&c);b[FLAG]=saved;for(unsigned i=0;i<32;i++)sprintf(out+2*i,"%02x",h[i]);}
#ifndef DPN_FLAG_HOST_TEST
static void text(const char *path,char *b,size_t n){int f=open(path,O_RDONLY|O_NOFOLLOW);need(f>=0,"identity file");ssize_t k=read(f,b,n-1);need(k>0&&(size_t)k<n-1,"identity size");b[k]=0;close(f);}
static void mode(void){char b[128],p[160];text("/sys/module/dpn_layout4_storage/parameters/flag_write",b,sizeof b);need(!strcmp(b,"Y\n"),"explicit flag view required");const char *names[]={"data_write","update","provision","stock_return","scratch_write"};for(unsigned i=0;i<5;i++){snprintf(p,sizeof p,"/sys/module/dpn_layout4_storage/parameters/%s",names[i]);text(p,b,sizeof b);need(!strcmp(b,"N\n"),"exclusive flag mode");}}
static void mtd(int f,const char *path,const char *name,unsigned size,bool writable){struct mtd_info_user m;need(!ioctl(f,MEMGETINFO,&m)&&m.type==MTD_NANDFLASH&&m.size==size&&m.erasesize==BLOCK&&m.writesize==4096&&m.oobsize==256&&!!(m.flags&MTD_WRITEABLE)==writable,"exact MTD geometry/flags");const char *base=strrchr(path,'/');need(base&&strlen(base)<32,"MTD path");char p[128],b[128];snprintf(p,sizeof p,"/sys/class/mtd/%s/name",base+1);text(p,b,sizeof b);need(strlen(b)==strlen(name)+1&&!memcmp(b,name,strlen(name))&&b[strlen(name)]=='\n',"MTD identity");}
#endif
int main(int argc,char **argv){
 need(argc==5&&strlen(argv[1])==1&&(argv[1][0]=='0'||argv[1][0]=='1')&&strlen(argv[4])==64,"usage 0|1 FLAG_MTD RAW_RO PINNED_ART_SHA_NORMALIZED_TO_ASCII_0");
 int raw=open(argv[3],O_RDONLY|O_NOFOLLOW),target=open(argv[2],O_RDWR|O_SYNC|O_NOFOLLOW);need(raw>=0&&target>=0,"MTD opens");
#ifndef DPN_FLAG_HOST_TEST
 mode();mtd(raw,argv[3],"dpn-physical-nand-ro",0x20000000,false);mtd(target,argv[2],"dpn-layout4-bootflag",BLOCK,true);
 int64_t off=0;need(ioctl(target,MEMGETBADBLOCK,&off)==0,"selector block healthy");
#endif
 unsigned char *before=malloc(ART_SIZE),*after=malloc(ART_SIZE),page[4096];need(before&&after,"ART read buffers");rd(raw,before,ART_SIZE,ART);need(before[FLAG]=='0'||before[FLAG]=='1'||before[FLAG]==255,"known or interrupted-erased selector");for(unsigned i=FLAG+1;i<ART_SIZE;i++)need(before[i]==255,"selector block contains other data");char h[65];normalized_sha(before,h);need(!strcmp(h,argv[4]),"pinned factory ART unchanged");
 if(before[FLAG]==argv[1][0]){free(before);free(after);close(raw);close(target);puts("BOOTFLAG_ALREADY_SELECTED_NO_ERASE");return 0;}
 memset(page,255,sizeof page);page[0]=argv[1][0];
#ifdef DPN_FLAG_HOST_TEST
 unsigned char *erased=malloc(BLOCK);need(erased,"test erase buffer");memset(erased,255,BLOCK);need(pwrite(target,erased,BLOCK,ART+FLAG)==BLOCK,"simulated selector erase");free(erased);mutations++;need(pwrite(target,page,sizeof page,ART+FLAG)==sizeof page,"simulated selector page");
#else
 struct erase_info_user erase={0,BLOCK};need(!ioctl(target,MEMERASE,&erase),"selector erase");mutations++;need(pwrite(target,page,sizeof page,0)==sizeof page,"selector ECC page");
#endif
 rd(raw,after,ART_SIZE,ART);need(after[FLAG]==argv[1][0],"new selector readback");after[FLAG]=before[FLAG];need(!memcmp(before,after,ART_SIZE),"all other ART bytes unchanged");free(before);free(after);close(raw);close(target);puts("BOOTFLAG_SELECTED_ORIGINAL_ART_UNCHANGED_EXCEPT_ONE_BYTE");return 0;
}
