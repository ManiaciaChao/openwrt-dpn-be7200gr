/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef DPN_LAYOUT4_NATIVE_IO_H
#define DPN_LAYOUT4_NATIVE_IO_H
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
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
#define DPN_BLOCK 0x40000U
#define DPN_PAGE 4096U
static unsigned dpn_mutations;
static inline void require(bool ok,const char *why){if(!ok){fprintf(stderr,"LAYOUT4_STOP %s errno=%d mutations=%u\n",why,errno,dpn_mutations);exit(2);}}
static inline void readat(int f,void *b,size_t n,uint64_t o){unsigned char *p=b;while(n){ssize_t k=pread(f,p,n,o);require(k>0,"complete read");p+=k;n-=k;o+=k;}}
static inline void hex(const unsigned char h[32],char out[65]){for(unsigned i=0;i<32;i++)sprintf(out+2*i,"%02x",h[i]);}
static inline void memory_sha(const void *b,size_t n,unsigned char h[32]){SHA2_CTX c;SHA256Init(&c);SHA256Update(&c,b,n);SHA256Final(h,&c);}
static inline void digest(int f,uint64_t o,uint64_t n,char out[65]){unsigned char b[65536],h[32];SHA2_CTX c;SHA256Init(&c);while(n){size_t k=n<sizeof b?n:sizeof b;readat(f,b,k,o);SHA256Update(&c,b,k);o+=k;n-=k;}SHA256Final(h,&c);hex(h,out);}
static inline bool digest_valid(const char *s){if(strlen(s)!=64)return false;for(unsigned i=0;i<64;i++)if(!strchr("0123456789abcdef",s[i]))return false;return true;}
static inline uint32_t little32(const unsigned char *p){return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static inline uint64_t little64(const unsigned char *p){return little32(p)|(uint64_t)little32(p+4)<<32;}
static inline void read_text(const char *path,char *b,size_t n){int f=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);require(f>=0,"identity file open");ssize_t k=read(f,b,n-1);require(k>0&&(size_t)k<n-1,"identity file size");b[k]=0;close(f);}
static inline int open_input(const char *path,uint64_t bytes){int f=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat s;require(f>=0&&!fstat(f,&s)&&S_ISREG(s.st_mode)&&s.st_size==(off_t)bytes,"exact regular input size");return f;}
static inline int open_mtd(unsigned index,const char *name,uint32_t bytes,bool writable){char path[512];
#ifdef DPN_LAYOUT4_HOST_TEST
 const char *dir=getenv("DPN_TEST_NAND_DIR");require(dir,"explicit synthetic NAND directory");require(snprintf(path,sizeof path,"%s/mtd%u",dir,index)<(int)sizeof path,"simulation path");
#else
 snprintf(path,sizeof path,"/dev/mtd%u",index);
#endif
 int f=open(path,(writable?O_RDWR|O_SYNC:O_RDONLY)|O_CLOEXEC|O_NOFOLLOW);require(f>=0,"MTD open");
#ifdef DPN_LAYOUT4_HOST_TEST
 (void)name;struct stat s;require(!fstat(f,&s)&&S_ISREG(s.st_mode)&&s.st_size==bytes,"synthetic exact MTD size");
#else
 struct mtd_info_user m;require(!ioctl(f,MEMGETINFO,&m)&&m.type==MTD_NANDFLASH&&m.size==bytes&&m.erasesize==DPN_BLOCK&&m.writesize==DPN_PAGE&&m.oobsize==256&&!!(m.flags&MTD_WRITEABLE)==writable,"MTD geometry and flags");
 char b[128];snprintf(path,sizeof path,"/sys/class/mtd/mtd%u/name",index);read_text(path,b,sizeof b);require(strlen(b)==strlen(name)+1&&!memcmp(b,name,strlen(name))&&b[strlen(name)]=='\n',"exact typed MTD name");
 if(writable)for(int64_t off=0;off<bytes;off+=DPN_BLOCK)require(ioctl(f,MEMGETBADBLOCK,&off)==0,"bad block in raw fixed target unsupported");
#endif
 return f;}
static inline void ram_detached_mode(const char *parameter,char boot[37]){
#ifdef DPN_LAYOUT4_HOST_TEST
 (void)parameter;const char *b=getenv("DPN_TEST_BOOT_ID");require(b&&strlen(b)==36,"synthetic boot ID");memcpy(boot,b,37);
#else
 struct statfs s;require(!statfs("/",&s)&&(s.f_type==0x01021994||s.f_type==0x858458f6),"RAM root required");
 char path[160],b[128];const char *params[]={"data_write","update","provision","stock_return","flag_write","scratch_write"};
 for(unsigned i=0;i<6;i++){snprintf(path,sizeof path,"/sys/module/dpn_layout4_storage/parameters/%s",params[i]);read_text(path,b,sizeof b);require(!strcmp(b,strcmp(params[i],parameter)?"N\n":"Y\n"),"exclusive typed storage mode");}
 FILE *f=fopen("/proc/mounts","r");require(f,"mount table");char line[2048];while(fgets(line,sizeof line,f))require(!strstr(line," squashfs ")&&!strstr(line," ubifs ")&&!strstr(line," overlay "),"persistent filesystem mounted");fclose(f);
 DIR *d=opendir("/sys/class/ubi");struct dirent *e;if(d){while((e=readdir(d)))require(strncmp(e->d_name,"ubi",3),"UBI still attached");closedir(d);}
 read_text("/proc/sys/kernel/random/boot_id",b,sizeof b);require(strlen(b)==37&&b[36]=='\n',"boot identity");memcpy(boot,b,36);boot[36]=0;
#endif
}
static inline void erase_block(int f,uint32_t off,uint32_t size){require(off%DPN_BLOCK==0&&off<=size-DPN_BLOCK,"erase bounds");
#ifdef DPN_LAYOUT4_HOST_TEST
 unsigned char *b=malloc(DPN_BLOCK);require(b,"test erase memory");memset(b,255,DPN_BLOCK);require(pwrite(f,b,DPN_BLOCK,off)==DPN_BLOCK,"test erase");free(b);
#else
 struct erase_info_user e={off,DPN_BLOCK};require(!ioctl(f,MEMERASE,&e),"bounded MTD erase");
#endif
 dpn_mutations++;}
static inline void program_page(int f,const unsigned char *b,uint32_t off,uint32_t size,const char *phase){require(off%DPN_PAGE==0&&off<=size-DPN_PAGE,"page bounds");
#ifdef DPN_LAYOUT4_HOST_TEST
 const char *failure=getenv("DPN_TEST_FAIL_PHASE"),*at=getenv("DPN_TEST_FAIL_PAGE");if(failure&&at&&strcmp(failure,phase)==0)require(off!=strtoul(at,NULL,0),"injected program failure");
#else
 (void)phase;
#endif
 bool ff=true;for(unsigned i=0;i<DPN_PAGE;i++)if(b[i]!=255){ff=false;break;}if(!ff)require(pwrite(f,b,DPN_PAGE,off)==DPN_PAGE,"complete ECC page program");}
#endif
