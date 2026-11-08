/* SPDX-License-Identifier: GPL-2.0-only */
/* Extract only the verified installer filesystem from a read-only factory slot.
 * No writable device is opened; slot is supplied by the strict bootarg parser.
 */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <libfdt.h>
#include <mtd/mtd-user.h>
#include <sha1.h>
#include <sha2.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
static void need(bool b,const char *s){if(!b){fprintf(stderr,"FACTORY_READ_STOP %s errno=%d\n",s,errno);exit(2);}}
static uint32_t le32(const unsigned char *p){return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void rd(int f,void *b,size_t n,uint64_t o){while(n){ssize_t k=pread(f,b,n,o);need(k>0,"complete ECC read");b=(char*)b+k;n-=k;o+=k;}}
int main(int argc,char **argv){
 need(argc==5&&(!strcmp(argv[2],"0")||!strcmp(argv[2],"1"))&&strlen(argv[3])==64,"usage RAW_RO SLOT EXPECTED_FS_SHA256 NEW_OUTPUT");
 int raw=open(argv[1],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);need(raw>=0,"read-only NAND open");
#ifndef DPN_FACTORY_READ_HOST_TEST
 struct mtd_info_user m;need(!ioctl(raw,MEMGETINFO,&m)&&m.type==MTD_NANDFLASH&&m.size==0x20000000&&m.erasesize==0x40000&&m.writesize==4096&&!(m.flags&MTD_WRITEABLE),"physical read-only geometry");
#endif
 uint64_t base=!strcmp(argv[2],"0")?0x80000:0x3280000;unsigned char header[0x2100];rd(raw,header,sizeof header,base);
 need(le32(header)==0xaa640001&&le32(header+152)==0x2000&&!le32(header+156)&&le32(header+0x2000)==0x32524448&&le32(header+0x2004)==256,"FIP/HDR2 header");
 uint32_t payload=le32(header+0x2008);need(payload>296&&payload<=0x3200000-0x2000&&le32(header+160)==payload&&!le32(header+164),"50 MiB slot bounds");
 size_t n=payload-256;unsigned char *fit=malloc(n);need(fit,"FIT memory");rd(raw,fit,n,base+0x2100);close(raw);
 need(!fdt_check_full(fit,n)&&fdt_totalsize(fit)==n,"complete FIT");
 uint32_t crc=~0U;for(size_t i=0;i<n;i++){crc^=fit[i];for(unsigned j=0;j<8;j++)crc=(crc>>1)^((0U-(crc&1))&0xedb88320U);}need(crc==le32(header+0x200c),"FIT CRC");
 int node=fdt_path_offset(fit,"/images/filesystem@1"),size;const unsigned char *fs=fdt_getprop(fit,node,"data",&size);need(fs&&size>=96&&le32(fs)==0x73717368,"installer SquashFS");
 int h=fdt_subnode_offset(fit,node,"hash@1"),alen,hlen;const char *algo=fdt_getprop(fit,h,"algo",&alen);const void *digest=fdt_getprop(fit,h,"value",&hlen);unsigned char actual[32];
 need(algo&&alen==5&&!memcmp(algo,"sha1",5)&&digest&&hlen==20,"FIT filesystem SHA1 descriptor");SHA1_CTX c1;SHA1Init(&c1);SHA1Update(&c1,fs,size);SHA1Final(actual,&c1);need(!memcmp(actual,digest,20),"FIT filesystem SHA1");
 SHA2_CTX c2;SHA256Init(&c2);SHA256Update(&c2,fs,size);SHA256Final(actual,&c2);char hex[65];for(unsigned i=0;i<32;i++)sprintf(hex+2*i,"%02x",actual[i]);need(!strcmp(hex,argv[3]),"DTB-bound installer filesystem SHA256");
 int out=open(argv[4],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);need(out>=0,"exclusive new RAM file");
 size_t at=0;while(at<(size_t)size){ssize_t k=write(out,fs+at,size-at);need(k>0,"filesystem output");at+=k;}need(!fsync(out)&&!close(out),"output sync");free(fit);puts("FACTORY_FILESYSTEM_EXTRACTED_READONLY_AND_HASH_VERIFIED");return 0;
}
