/* SPDX-License-Identifier: GPL-2.0-only */
/* RAM-only compact recovery+vault installation, header committed last. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <libfdt.h>
#include <mtd/mtd-user.h>
#include <sha2.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <unistd.h>
#define BASE 0x3280000U
#define LIMIT 0x4680000U
#define SIZE (LIMIT-BASE)
#define CHIP 0x20000000U
#define BLOCK 0x40000U
struct guard {char magic[8],boot[37],input[65],before[65],protected[2][65];};
static unsigned mutations;
static void need(bool b,const char *s){if(!b){fprintf(stderr,"RECOVERY_PROVISION_STOP %s errno=%d mutations=%u\n",s,errno,mutations);exit(2);}}
static void rd(int f,void *b,size_t n,uint64_t o){unsigned char *p=b;while(n){ssize_t k=pread(f,p,n,o);need(k>0,"complete read");p+=k;o+=k;n-=k;}}
static void hex(const unsigned char h[32],char out[65]){for(unsigned i=0;i<32;i++)sprintf(out+2*i,"%02x",h[i]);}
static void sha(const void *b,size_t n,unsigned char h[32]){SHA2_CTX c;SHA256Init(&c);SHA256Update(&c,b,n);SHA256Final(h,&c);}
static void digest(int f,uint64_t o,uint64_t n,char out[65]){unsigned char b[65536],h[32];SHA2_CTX c;SHA256Init(&c);while(n){size_t k=n<sizeof b?n:sizeof b;rd(f,b,k,o);SHA256Update(&c,b,k);n-=k;o+=k;}SHA256Final(h,&c);hex(h,out);}
static uint32_t le32(const unsigned char *b){return b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;}
static uint64_t le64(const unsigned char *b){return le32(b)|(uint64_t)le32(b+4)<<32;}
#ifndef DPN_PROVISION_HOST_TEST
static void text(const char *p,char *b,size_t n){int f=open(p,O_RDONLY|O_NOFOLLOW);need(f>=0,"identity open");ssize_t k=read(f,b,n-1);need(k>0&&(size_t)k<n-1,"identity size");b[k]=0;close(f);}
#endif
static void runtime(char boot[37]){
#ifdef DPN_PROVISION_HOST_TEST
 const char *b=getenv("DPN_PROVISION_TEST_BOOT");need(b&&strlen(b)==36,"test boot");memcpy(boot,b,37);
#else
 char b[128];struct statfs s;need(!statfs("/",&s)&&(s.f_type==0x01021994||s.f_type==0x858458f6),"RAM root required");
 text("/sys/module/dpn_layout4_storage/parameters/provision",b,sizeof b);need(!strcmp(b,"Y\n"),"explicit provision mode required");
 const char *names[]={"data_write","update","stock_return","flag_write","scratch_write"};for(unsigned i=0;i<5;i++){char p[160];snprintf(p,sizeof p,"/sys/module/dpn_layout4_storage/parameters/%s",names[i]);text(p,b,sizeof b);need(!strcmp(b,"N\n"),"exclusive provision mode");}
 FILE *f=fopen("/proc/mounts","r");need(f,"mount table");char line[2048];while(fgets(line,sizeof line,f))need(!strstr(line," ubifs ")&&!strstr(line," squashfs ")&&!strstr(line," overlay "),"no persistent filesystem");fclose(f);
 DIR *d=opendir("/sys/class/ubi");struct dirent *e;if(d){while((e=readdir(d)))need(strncmp(e->d_name,"ubi",3),"no attached UBI");closedir(d);}
 text("/proc/sys/kernel/random/boot_id",b,sizeof b);need(strlen(b)==37&&b[36]=='\n',"boot identity");memcpy(boot,b,36);boot[36]=0;
#endif
}
static int open_mtd(const char *path,const char *name,uint32_t size,bool writable){int f=open(path,(writable?O_RDWR|O_SYNC:O_RDONLY)|O_NOFOLLOW);need(f>=0,"MTD open");
#ifdef DPN_PROVISION_HOST_TEST
 (void)name;struct stat s;need(!fstat(f,&s)&&S_ISREG(s.st_mode)&&s.st_size==size,"test file size");
#else
 struct mtd_info_user m;need(!ioctl(f,MEMGETINFO,&m)&&m.type==MTD_NANDFLASH&&m.size==size&&m.writesize==4096&&m.erasesize==BLOCK&&m.oobsize==256&&!!(m.flags&MTD_WRITEABLE)==writable,"exact MTD geometry/flags");
 const char *base=strrchr(path,'/');need(base&&strlen(base)<32,"MTD path");char p[128],b[128];snprintf(p,sizeof p,"/sys/class/mtd/%s/name",base+1);text(p,b,sizeof b);need(strlen(b)==strlen(name)+1&&!memcmp(b,name,strlen(name))&&b[strlen(name)]=='\n',"exact MTD view");
 for(int64_t o=0;o<size;o+=BLOCK)need(ioctl(f,MEMGETBADBLOCK,&o)==0,"nonempty bad-block profile unsupported");
#endif
 return f;
}
static void validate(const unsigned char *b,int raw){
 need(le32(b)==0xaa640001&&le64(b+152)==0x2000,"FIP payload entry");uint64_t n=le64(b+160);need(n>296&&n<=0x1000000-0x2000&&le32(b+0x2000)==0x32524448&&le32(b+0x2004)==256&&le32(b+0x2008)==n,"recovery FIP limit/HDR2");
 const void *fit=b+0x2100;n-=256;need(!fdt_check_full(fit,n)&&fdt_totalsize(fit)==n,"FIT structure");uint32_t crc=~0U;for(size_t i=0;i<n;i++){crc^=b[0x2100+i];for(unsigned j=0;j<8;j++)crc=(crc>>1)^((0U-(crc&1))&0xedb88320U);}need(crc==le32(b+0x200c),"HDR2 CRC");
 int node=fdt_path_offset(fit,"/images/fdt@1"),len;const void *embedded=fdt_getprop(fit,node,"data",&len);need(embedded&&len>40,"embedded DTB data");void *dt=malloc(len);need(dt,"aligned DTB memory");memcpy(dt,embedded,len);need(!fdt_check_full(dt,len),"embedded DTB");need(!fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-layout4")&&!fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-persist"),"layout4 persistent-write compatibility");node=fdt_path_offset(dt,"/dpn-layout4");const char *role=fdt_getprop(dt,node,"write-profile",&len);need(role&&len==9&&!memcmp(role,"recovery",9),"dedicated recovery profile");const fdt32_t *version=fdt_getprop(dt,node,"format-version",&len);need(version&&len==4&&fdt32_to_cpu(*version)==4,"layout version");free(dt);
 for(uint64_t i=0x2100+n;i<0x1000000;i++)need(b[i]==255,"recovery FIP tail must be FF");
 const unsigned char *v=b+0x1000000;need(!memcmp(v,"DPNVLT1",8)&&le32(v+8)==1&&le32(v+12)==0x400000,"vault header");unsigned char h[32];sha(v,4096-32,h);need(!memcmp(h,v+4096-32,32),"vault header SHA");
 unsigned char eeprom[0x1e00],ascii[17],mac[6];rd(raw,eeprom,sizeof eeprom,0x1bc80000+0x40000);rd(raw,ascii,sizeof ascii,0x1bc80000+0x301055);need(eeprom[0]==0x92&&eeprom[1]==0x79,"factory EEPROM");
 for(unsigned i=0;i<6;i++){unsigned x;char pair[3]={(char)ascii[i*3],(char)ascii[i*3+1],0};need(sscanf(pair,"%2x",&x)==1&&(i==5||ascii[i*3+2]==':'),"factory MAC");mac[i]=x;}
 SHA2_CTX c;static const unsigned char prefix[]="DPN-BE7200GR-factory-v1";SHA256Init(&c);SHA256Update(&c,prefix,sizeof prefix);SHA256Update(&c,eeprom,sizeof eeprom);SHA256Update(&c,mac,sizeof mac);SHA256Final(h,&c);need(!memcmp(h,v+16,32),"vault belongs to this device");
}
static void protected(int f,char h[2][65]){digest(f,0,BASE,h[0]);digest(f,LIMIT,CHIP-LIMIT,h[1]);}
static void erase(int f,uint32_t o){need(o%BLOCK==0&&o<=SIZE-BLOCK,"erase bounds");
#ifdef DPN_PROVISION_HOST_TEST
 unsigned char *b=malloc(BLOCK);need(b,"test erase buffer");memset(b,255,BLOCK);need(pwrite(f,b,BLOCK,o)==BLOCK,"test erase");free(b);
#else
 struct erase_info_user e={o,BLOCK};need(!ioctl(f,MEMERASE,&e),"erase");
#endif
 mutations++;
}
static void program(int f,const unsigned char *b,uint32_t o){
#ifdef DPN_PROVISION_HOST_TEST
 const char *failure=getenv("DPN_PROVISION_FAIL_PAGE");if(failure)need(o!=strtoul(failure,NULL,0),"injected page failure");
#endif
 need(o%4096==0&&o<=SIZE-4096,"page bounds");bool ff=true;for(unsigned i=0;i<4096;i++)if(b[o+i]!=255){ff=false;break;}if(!ff)need(pwrite(f,b+o,4096,o)==4096,"ECC page program");
}
int main(int argc,char **argv){
 need(argc==7&&(!strcmp(argv[1],"--snapshot")||!strcmp(argv[1],"--write")),"usage --snapshot|--write TARGET INPUT PINNED_SHA GUARD RAW_RO");bool commit=!strcmp(argv[1],"--write");struct guard g={.magic="DPNPRV1"},old;runtime(g.boot);
 int raw=open_mtd(argv[6],"dpn-physical-nand-ro",CHIP,false),target=open_mtd(argv[2],"dpn-layout4-provision-target",SIZE,true);
 int input=open(argv[3],O_RDONLY|O_NOFOLLOW);struct stat s;need(input>=0&&!fstat(input,&s)&&S_ISREG(s.st_mode)&&s.st_size==SIZE,"exact 20 MiB candidate");digest(input,0,SIZE,g.input);need(strlen(argv[4])==64&&!strcmp(argv[4],g.input),"externally pinned candidate SHA");unsigned char *b=malloc(SIZE);need(b,"candidate memory");rd(input,b,SIZE,0);close(input);validate(b,raw);digest(target,0,SIZE,g.before);protected(raw,g.protected);
 if(!commit){int f=open(argv[5],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);need(f>=0&&write(f,&g,sizeof g)==sizeof g&&!fsync(f)&&!close(f),"exclusive same-boot snapshot");free(b);puts("RECOVERY_PROVISION_20_MIB_INPUT_AND_492_MIB_PROTECTION_SNAPSHOT_VERIFIED");return 0;}
 int f=open(argv[5],O_RDONLY|O_NOFOLLOW);need(f>=0&&!fstat(f,&s)&&s.st_size==sizeof old,"guard size");rd(f,&old,sizeof old,0);close(f);need(!memcmp(&g,&old,sizeof g),"same boot/input/target/protected data");
 erase(target,0);for(uint32_t o=BLOCK;o<SIZE;o+=BLOCK)erase(target,o);
 for(uint32_t o=BLOCK;o<SIZE;o+=4096)program(target,b,o);
 char h[65];digest(target,BLOCK,SIZE-BLOCK,h);unsigned char digest_b[32];char expected[65];sha(b+BLOCK,SIZE-BLOCK,digest_b);hex(digest_b,expected);need(!strcmp(h,expected),"body and vault readback before header");
 for(uint32_t o=0;o<BLOCK;o+=4096)program(target,b,o);
 digest(target,0,SIZE,h);need(!strcmp(h,g.input),"complete recovery+vault readback");char after[2][65];protected(raw,after);need(!memcmp(after,g.protected,sizeof after),"492 MiB outside recovery/vault unchanged");free(b);close(raw);close(target);puts("RECOVERY_AND_DEVICE_VAULT_COMMITTED_HEADER_LAST_492_MIB_UNCHANGED");return 0;
}
