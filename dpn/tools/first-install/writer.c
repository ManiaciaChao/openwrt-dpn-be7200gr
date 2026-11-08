/* SPDX-License-Identifier: GPL-2.0-only */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <dirent.h>
#include <ctype.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <mtd/mtd-user.h>
#include <sha1.h>
#include <sha2.h>
#include <libfdt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <unistd.h>
#include "../generic-ram/kernel/dpn_slot_policy.h"
/* Guard digests are read from this target, never compiled into public code. */
struct guard { unsigned char magic[8],slot[4]; char region[3][65]; char header[65]; char previous_prefix[65]; };
static unsigned active_slot;
static size_t firmware_start=0x80000,factory_start=0x3280000;
static struct guard guard;
static struct {size_t off,len;} protected_ranges[]={
 {0,0x80000},{0x1280000,0xb800000-0x1280000},{0x1b800000,0x20000000-0x1b800000}
};
#define BLOCK 262144U
#define PAGE 4096U
#define PREFIX 18874368U
static int mutations,writes;
static unsigned image_layout;
static bool legacy_probe;
static char temporary[128];
static int active_lock=-1;
static void cleanup(void){if(temporary[0])unlink(temporary);if(active_lock>=0)close(active_lock);}
static const char *sim;
static void stop(const char *s){fprintf(stderr,"DPN_UPGRADE_STOP %s errno=%d mutations=%d\n",s,errno,mutations);exit(2);}
static void select_slot(unsigned slot){
 if(slot>1)stop("invalid update slot");active_slot=slot;
 firmware_start=dpn_firmware_base(slot);factory_start=dpn_firmware_base(1-slot);
 protected_ranges[0].len=firmware_start;
 protected_ranges[1].off=firmware_start+PREFIX;
 protected_ranges[1].len=0xb800000-protected_ranges[1].off;
}
static unsigned runtime_slot(void){
#ifdef DPN_UPGRADE_HOST_TEST
 const char *s=getenv("DPN_TEST_SLOT");if(!s)return 0;
 if(!strcmp(s,"0"))return 0;if(!strcmp(s,"1"))return 1;stop("invalid simulated slot");
#else
 char line[4098];FILE *f=fopen("/sys/module/dpn_storage/parameters/root_slot","r");
 if(!f||!fgets(line,sizeof line,f))stop("runtime slot unavailable");fclose(f);
 unsigned slot;if(!strcmp(line,"0\n"))slot=0;else if(!strcmp(line,"1\n"))slot=1;else stop("runtime slot invalid");
 struct stat st;
 if(!stat("/sys/firmware/devicetree/base/dpn-flash-layout/slot-relative-root",&st)){
  f=fopen("/proc/cmdline","r");if(!f||!fgets(line,sizeof line,f))stop("boot handoff unavailable");fclose(f);
  if(dpn_cmdline_slot(line)!=(int)slot)stop("runtime slot contradicts boot handoff");
 }else if(slot)stop("secondary updates require slot-aware profile");
 return slot;
#endif
 return 0;
}
static void bind_runtime(void){if(runtime_slot()!=active_slot)stop("guard belongs to another running slot");}
static void lock_prefix(bool write){
 char path[512];
#ifdef DPN_UPGRADE_HOST_TEST
 if(snprintf(path,sizeof path,"%s/firmware.lock",sim)>=(int)sizeof path)stop("lock path");
#else
 strcpy(path,"/tmp/dpn-firmware-program.lock");
#endif
 active_lock=open(path,O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);struct stat st;
 if(active_lock<0||fstat(active_lock,&st)||!S_ISREG(st.st_mode)||st.st_uid!=geteuid()||flock(active_lock,(write?LOCK_EX:LOCK_SH)|LOCK_NB))stop("another programmer is active or lock is invalid");
}
static void readat(int fd,void *v,size_t n,off_t off){char *p=v;while(n){ssize_t k=pread(fd,p,n,off);if(k<=0)stop("short read");p+=k;off+=k;n-=k;}}
static void hex(const unsigned char *b,size_t n,char *out){for(size_t i=0;i<n;i++)sprintf(out+2*i,"%02x",b[i]);}
static void digest256(const void *p,size_t n,unsigned char b[32]){SHA2_CTX c;SHA256Init(&c);SHA256Update(&c,p,n);SHA256Final(b,&c);}
static void digest1(const void *p,size_t n,unsigned char b[20]){SHA1_CTX c;SHA1Init(&c);SHA1Update(&c,p,n);SHA1Final(b,&c);}
static void sha(const void *p,size_t n,char h[65]){unsigned char b[32];digest256(p,n,b);hex(b,32,h);}
static void hashfd(int fd,off_t off,size_t n,char h[65]){SHA2_CTX c;unsigned char b[65536],d[32];SHA256Init(&c);while(n){size_t k=n<sizeof b?n:sizeof b;readat(fd,b,k,off);SHA256Update(&c,b,k);off+=k;n-=k;}SHA256Final(d,&c);hex(d,32,h);}
static uint32_t le32(const unsigned char *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint64_t le64(const unsigned char *p){return le32(p)|((uint64_t)le32(p+4)<<32);}
static uint32_t jamcrc(const unsigned char *p,size_t n){uint32_t c=~0U;while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^((0U-(c&1))&0xedb88320U);}return c;}
static const void *prop(const void *f,int node,const char *name,int *len){const void *p=fdt_getprop(f,node,name,len);if(!p)stop("missing FIT property");return p;}
static void strprop(const void *f,int node,const char *name,const char *want){int n;const char *p=prop(f,node,name,&n);if(n!=(int)strlen(want)+1||memcmp(p,want,n))stop("FIT string mismatch");}
static uint32_t u32prop(const void *f,int node,const char *name){int n;const fdt32_t *p=prop(f,node,name,&n);if(n!=4)stop("FIT integer size");return fdt32_to_cpu(*p);}
static void factory_policy(const void *dt){
 int provider=fdt_path_offset(dt,"/dpn-art"),depth=0,node=0,n;
 if(provider<0||fdt_node_check_compatible(dt,provider,"dlink,dpn-be7200gr-art"))stop("runtime factory-data provider missing");
 for(;node>=0&&depth>=0;node=fdt_next_node(dt,node,&depth))
  if(fdt_getprop(dt,node,"mediatek,eeprom-data",&n)||fdt_getprop(dt,node,"local-mac-address",&n)||fdt_getprop(dt,node,"mac-address",&n))stop("inline calibration or fixed MAC forbidden in generic image");
}
static unsigned char *image(const char *path,size_t *bytes){
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<=0x2100||st.st_size>PREFIX)stop("FIP size/type");
 *bytes=st.st_size;unsigned char *b=malloc(PREFIX);if(!b)stop("memory");memset(b,255,PREFIX);readat(fd,b,*bytes,0);close(fd);
 unsigned char hdr[0x2100];memcpy(hdr,b,sizeof hdr);memset(hdr+160,0,8);memset(hdr+0x2008,0,8);char h[65];sha(hdr,sizeof hdr,h);if(strcmp(h,guard.header))stop("device factory header mismatch");
 const void *fit=b+0x2100;size_t len=*bytes-0x2100;
 if(fdt_check_full(fit,len)||fdt_totalsize(fit)!=len||le64(b+160)!=len+256||le32(b+0x2008)!=len+256||le32(b+0x200c)!=jamcrc(fit,len))stop("FIP/FIT length or CRC");
 int images=fdt_path_offset(fit,"/images"),configs=fdt_path_offset(fit,"/configurations"),conf=fdt_path_offset(fit,"/configurations/conf@1");
 if(images<0||configs<0||conf<0)stop("FIT structure");strprop(fit,configs,"default","conf@1");strprop(fit,conf,"kernel","kernel@1");strprop(fit,conf,"fdt","fdt@1");
 int q;if(fdt_getprop(fit,conf,"ramdisk",&q))stop("RAM test image forbidden");
 const unsigned char *dt=NULL,*fs=NULL;int dlen=0,flen=0,count=0,node;
 fdt_for_each_subnode(node,fit,images) count++;
 if(count!=3)stop("FIT must contain three images");
 const char *names[]={"fdt@1","kernel@1","filesystem@1"};const char *types[]={"flat_dt","kernel","filesystem"};
 for(int i=0;i<3;i++){
  node=fdt_subnode_offset(fit,images,names[i]);if(node<0)stop("FIT image name");int n;const unsigned char *data=prop(fit,node,"data",&n);if(n<=0)stop("empty FIT image");
  strprop(fit,node,"type",types[i]);strprop(fit,node,"arch","arm64");strprop(fit,node,"compression",i==1?"lzma":"none");
  int hn=fdt_subnode_offset(fit,node,"hash@1");if(hn<0)stop("missing SHA1 node");strprop(fit,hn,"algo","sha1");int sz;const void *v=prop(fit,hn,"value",&sz);unsigned char digest[20];digest1(data,n,digest);if(sz!=20||memcmp(v,digest,20))stop("FIT SHA1 mismatch");
  if(i==0){dt=data;dlen=n;if(u32prop(fit,node,"load")!=0x8d000000)stop("FDT load");}
  if(i==1&&(u32prop(fit,node,"load")!=0x8b000000||u32prop(fit,node,"entry")!=0x8b000000))stop("kernel load/entry");
  if(i==1||i==2)strprop(fit,node,"os","linux");
  if(i==2){fs=data;flen=n;}
 }
 /* FIT inline data is only four-byte aligned; libfdt requires eight. */
 void *aligned_dt=malloc(dlen);if(!aligned_dt)stop("FDT memory");memcpy(aligned_dt,dt,dlen);dt=aligned_dt;
 if(fdt_check_full(dt,dlen)||(!legacy_probe&&fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr"))||fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-persist")||fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-upgrade"))stop("candidate lacks persistent upgrade support");
 if(!legacy_probe)factory_policy(dt);
 int layout=fdt_path_offset(dt,"/dpn-flash-layout");if(layout<0)stop("missing layout");image_layout=u32prop(dt,layout,"upgrade-layout");
 if(image_layout!=3&&!(legacy_probe&&image_layout==2))stop("requires generic layout 3");
 if(!legacy_probe&&(fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-install")||!fdt_getprop(dt,layout,"persistent-root",&q)||u32prop(dt,layout,"format-version")!=1))stop("generic persistent boot policy missing");
 if(fdt_node_check_compatible(dt,0,"dlink,dpn-be7200gr-expand")||u32prop(dt,layout,"config-bank")!=2||u32prop(dt,layout,"config-start")!=0xb800000||u32prop(dt,layout,"config-size")!=0x10000000)stop("expanded config layout mismatch");
#ifndef DPN_UPGRADE_HOST_TEST
 {FILE *cf=fopen("/sys/firmware/devicetree/base/dpn-flash-layout/config-bank","rb");unsigned char a[4]={0};if(cf){size_t n=fread(a,1,4,cf);fclose(cf);if(!legacy_probe&&n==4&&a[3]==2&&image_layout!=3)stop("downgrade would lose expanded overlay");}}
#else
 if(!legacy_probe&&getenv("DPN_CURRENT_BANK")&&atoi(getenv("DPN_CURRENT_BANK"))==2&&image_layout!=3)stop("downgrade would lose expanded overlay");
#endif
 if(fdt_getprop(dt,layout,"ram-stage",&q)||fdt_getprop(dt,layout,"ram-root",&q)||fdt_getprop(dt,layout,"ram-install",&q))stop("RAM profile forbidden");
 if(active_slot && !fdt_getprop(dt,layout,"slot-relative-root",&q))stop("secondary updates require slot-relative root");
 if(u32prop(dt,layout,"rootfs-offset")!=0x80000+(size_t)(fs-b)||u32prop(dt,layout,"rootfs-size")!=(uint32_t)flen)stop("rootfs layout mismatch");
 int sz;const void *want=prop(dt,layout,"rootfs-sha256",&sz);unsigned char digest[32];digest256(fs,flen,digest);if(sz!=32||memcmp(want,digest,32)||le32(fs)!=0x73717368)stop("rootfs SHA256/magic");
 int reserved=0;for(int i=0;i<fdt_num_mem_rsv(dt);i++){uint64_t a,n;if(fdt_get_mem_rsv(dt,i,&a,&n))stop("FDT reservation");if(a==0x98000000&&n==0x8000000)reserved=1;}if(!reserved)stop("FDT high RAM reservation missing");
 free(aligned_dt);printf("DPN_IMAGE_LAYOUT=%u\n",image_layout);sha(b,*bytes,h);printf("DPN_IMAGE_OK bytes=%zu SHA256=%s\n",*bytes,h);return b;
}
static int part(int idx,int mode){char path[512];
#ifdef DPN_UPGRADE_HOST_TEST
 snprintf(path,sizeof path,"%s/mtd%d",sim,idx);
#else
 snprintf(path,sizeof path,"/dev/mtd%d",idx);
#endif
 int fd=open(path,mode|O_NOFOLLOW|O_CLOEXEC);if(fd<0)stop("MTD open");
#ifndef DPN_UPGRADE_HOST_TEST
 struct mtd_info_user info;if(ioctl(fd,MEMGETINFO,&info)||info.type!=MTD_NANDFLASH||info.size!=(idx==0?0x20000000U:PREFIX)||info.writesize!=PAGE||info.erasesize!=BLOCK||info.oobsize!=256)stop("MTD geometry");
 FILE *f;snprintf(path,sizeof path,"/sys/class/mtd/mtd%d/name",idx);f=fopen(path,"r");if(!f||!fgets(path,sizeof path,f))stop("MTD name read");fclose(f);if(strcmp(path,idx==0?"dpn-physical-nand-ro\n":"dpn-firmware-update\n"))stop("MTD identity");
 if((idx==0&&(info.flags&MTD_WRITEABLE))||(idx==2&&!(info.flags&MTD_WRITEABLE)))stop("MTD flags");
#endif
 return fd;
}
static void protected(int fd){
 char h[65];for(size_t i=0;i<3;i++){
  hashfd(fd,protected_ranges[i].off,protected_ranges[i].len,h);
  if(strcmp(h,guard.region[i]))stop("protected region changed since snapshot");
 }puts("PROTECTED_REGIONS_OK");
}
static void header_digest(int fd,char h[65],unsigned char header[0x2100]){
 readat(fd,header,0x2100,factory_start);unsigned char normalized[0x2100];
 memcpy(normalized,header,sizeof normalized);memset(normalized+160,0,8);memset(normalized+0x2008,0,8);
 sha(normalized,sizeof normalized,h);
}
static void guard_load(const char *path){
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;unsigned char raw[337];
 if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode)||(st.st_size!=333&&st.st_size!=337))stop("guard file type/size");
 readat(fd,raw,st.st_size,0);close(fd);
 if(st.st_size==333){
  if(memcmp(raw,"DPNGRD3",8))stop("legacy guard version");
  memcpy(guard.magic,"DPNGRD4",8);memset(guard.slot,0,4);memcpy(guard.region,raw+8,325);
 }else{
  memcpy(&guard,raw,sizeof guard);
  if(memcmp(guard.magic,"DPNGRD4",8))stop("guard version");
 }
 if(guard.slot[0]>1||guard.slot[1]||guard.slot[2]||guard.slot[3])stop("guard slot encoding");
 select_slot(guard.slot[0]);
 const char *hashes[]={guard.region[0],guard.region[1],guard.region[2],guard.header,guard.previous_prefix};
 for(size_t i=0;i<5;i++){if(hashes[i][64])stop("guard digest length");for(int j=0;j<64;j++)if(!((hashes[i][j]>='0'&&hashes[i][j]<='9')||(hashes[i][j]>='a'&&hashes[i][j]<='f')))stop("guard digest encoding");}
}
static void snapshot(const char *path){
 select_slot(runtime_slot());int fd=part(0,O_RDONLY);memcpy(guard.magic,"DPNGRD4",8);memset(guard.slot,0,4);guard.slot[0]=active_slot;
 unsigned char flag;readat(fd,&flag,1,0x1bfc0000);if(flag!='0'+active_slot)stop("physical bootflag contradicts running slot; flag will not be changed");
 for(size_t i=0;i<3;i++)hashfd(fd,protected_ranges[i].off,protected_ranges[i].len,guard.region[i]);
 unsigned char hdr[0x2100];header_digest(fd,guard.header,hdr);
 hashfd(fd,firmware_start,PREFIX,guard.previous_prefix);close(fd);
 int out=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(out<0||write(out,&guard,sizeof guard)!=sizeof guard||fsync(out))stop("guard snapshot output");
 close(out);puts("PER_TARGET_GUARD_SAVED_NO_FLASH_WRITES");
}
static void assemble(const char *fitpath,const char *output){
 int source=part(0,O_RDONLY);protected(source);unsigned char hdr[0x2100];char h[65];header_digest(source,h,hdr);close(source);
 if(strcmp(h,guard.header))stop("factory header guard mismatch");
 int f=open(fitpath,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 if(f<0||fstat(f,&st)||!S_ISREG(st.st_mode)||st.st_size<40||st.st_size>PREFIX-0x2100)stop("FIT input size/type");
 size_t len=st.st_size;unsigned char *fit=malloc(len);if(!fit)stop("memory");readat(f,fit,len,0);close(f);
 if(fdt_check_full(fit,len)||fdt_totalsize(fit)!=len)stop("FIT structure/size");
 uint64_t size=len+256;for(int i=0;i<8;i++)hdr[160+i]=size>>(8*i);
 uint32_t crc=jamcrc(fit,len);for(int i=0;i<4;i++){hdr[0x2008+i]=size>>(8*i);hdr[0x200c+i]=crc>>(8*i);}
 int out=open(output,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(out<0||write(out,hdr,sizeof hdr)!=sizeof hdr||write(out,fit,len)!=(ssize_t)len||fsync(out))stop("assembled FIP output");
 close(out);free(fit);size_t bytes;unsigned char *checked=image(output,&bytes);free(checked);
 puts("TARGET_FIP_ASSEMBLED_NO_FLASH_WRITES");
}
static void check_fit(const char *path){
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<40||st.st_size>PREFIX-0x2100)stop("FIT input size/type");
 size_t n=st.st_size;unsigned char *fit=malloc(n);if(!fit)stop("memory");readat(fd,fit,n,0);close(fd);
 unsigned char header[0x2100]={0};sha(header,sizeof header,guard.header);
 uint64_t size=n+256;uint32_t crc=jamcrc(fit,n);
 for(int i=0;i<8;i++)header[160+i]=size>>(8*i);
 for(int i=0;i<4;i++){header[0x2008+i]=size>>(8*i);header[0x200c+i]=crc>>(8*i);}
 char name[]="/tmp/dpn-fit-check-XXXXXX";int out=mkstemp(name);
 if(out>=0)strcpy(temporary,name);
 if(out<0||write(out,header,sizeof header)!=sizeof header||write(out,fit,n)!=(ssize_t)n)stop("temporary FIT check");
 close(out);free(fit);size_t bytes;unsigned char *b=image(name,&bytes);free(b);
 if(unlink(name))stop("temporary check cleanup");temporary[0]=0;puts("GENERIC_FIT_VALIDATED_NO_MTD_ACCESS");
}
static void config_blank(void){
 int source=part(0,O_RDONLY);unsigned char b[65536];
 for(size_t off=0xb800000;off<0x1b800000;off+=sizeof b){
  readat(source,b,sizeof b,off);for(size_t i=0;i<sizeof b;i++)if(b[i]!=255)stop("new config bank is not completely blank");
 }
 close(source);puts("NEW_CONFIG_BANK_ALL_FF");
}
static void probe_current(void){
 int source=part(0,O_RDONLY);protected(source);unsigned char hdr[0x2100];
 readat(source,hdr,sizeof hdr,firmware_start);uint64_t encoded=le64(hdr+160);
 if(encoded<=256||encoded-256>PREFIX-sizeof hdr)stop("existing prefix is not a supported bounded installation");
 size_t len=encoded-256;unsigned char *fit=malloc(len);if(!fit)stop("memory");readat(source,fit,len,firmware_start+0x2100);close(source);
 char name[]="/tmp/dpn-probe-current-XXXXXX";int out=mkstemp(name);
 if(out>=0)strcpy(temporary,name);
 if(out<0||write(out,hdr,sizeof hdr)!=sizeof hdr||write(out,fit,len)!=(ssize_t)len)stop("current prefix probe temporary output");
 close(out);free(fit);legacy_probe=true;size_t bytes;unsigned char *b=image(name,&bytes);free(b);legacy_probe=false;
 if(unlink(name))stop("current probe cleanup");temporary[0]=0;puts("EXISTING_EXPANDED_CONFIG_PROFILE_VERIFIED");
}
static void ram_guard(void){
#ifndef DPN_UPGRADE_HOST_TEST
 struct statfs st;if(statfs("/",&st)||(st.f_type!=0x01021994&&st.f_type!=0x858458f6))stop("requires RAM root");
 FILE *f=fopen("/proc/mounts","r");char line[1024];if(!f)stop("mounts read");while(fgets(line,sizeof line,f))if(strstr(line," squashfs ")||strstr(line," ubifs ")||strstr(line," overlay "))stop("Flash filesystem still mounted");fclose(f);
 DIR *dir=opendir("/sys/class/ubi");if(dir){struct dirent *de;while((de=readdir(dir))){
  if(strncmp(de->d_name,"ubi",3))continue;const char *n=de->d_name+3;if(!*n)continue;
  while(isdigit((unsigned char)*n))n++;if(!*n)stop("all UBI devices must be detached");
 }closedir(dir);}
#endif
}
static void erase(int fd,size_t off){if(off%BLOCK||off>PREFIX-BLOCK)stop("erase bounds");
#ifdef DPN_UPGRADE_HOST_TEST
 unsigned char b[PAGE];memset(b,255,PAGE);for(size_t p=0;p<BLOCK;p+=PAGE)if(pwrite(fd,b,PAGE,off+p)!=PAGE)stop("sim erase");
#else
 struct erase_info_user64 e={.start=off,.length=BLOCK};if(ioctl(fd,MEMERASE64,&e))stop("erase failed");
#endif
 mutations++;
}
static void program(int fd,size_t off,const unsigned char *b){if(off%PAGE||off>PREFIX-PAGE)stop("program bounds");
#ifdef DPN_UPGRADE_HOST_TEST
 const char *v=getenv("DPN_TEST_FAIL_WRITE_AT");if(v&&writes++==atoi(v)){errno=EIO;stop("injected program failure");}
 unsigned char old[PAGE];readat(fd,old,PAGE,off);for(size_t i=0;i<PAGE;i++)if((old[i]&b[i])!=b[i])stop("zero-to-one");
#endif
 if(pwrite(fd,b,PAGE,off)!=PAGE)stop("program failed");mutations++;
}
static void compare(int fd,const unsigned char *b,size_t start,size_t end){unsigned char p[PAGE];for(size_t n=start;n<end;n+=PAGE){readat(fd,p,PAGE,n);if(memcmp(p,b+n,PAGE))stop("ECC readback mismatch");}}
static unsigned char *previous(const char *path){
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size!=PREFIX)stop("previous prefix size/type");
 unsigned char *b=malloc(PREFIX);if(!b)stop("memory");readat(fd,b,PREFIX,0);close(fd);
 char h[65];sha(b,PREFIX,h);if(strcmp(h,guard.previous_prefix))stop("previous prefix does not match this target snapshot");
 return b;
}
int main(int argc,char **argv){setvbuf(stdout,NULL,_IOLBF,0);atexit(cleanup);
#ifdef DPN_UPGRADE_HOST_TEST
 if(argc<3)return 64;sim=argv[--argc];
#else
 (void)sim;(void)writes;
#endif
 if(argc==3&&!strcmp(argv[1],"--snapshot")){ram_guard();lock_prefix(false);snapshot(argv[2]);return 0;}
 if(argc==3&&!strcmp(argv[1],"--check-fit")){check_fit(argv[2]);return 0;}
 if(argc==2&&!strcmp(argv[1],"--check-config-blank")){ram_guard();config_blank();return 0;}
 if(argc==3&&!strcmp(argv[1],"--probe-current")){lock_prefix(false);guard_load(argv[2]);probe_current();return 0;}
 if(argc==5&&!strcmp(argv[1],"--assemble-fit")){guard_load(argv[3]);assemble(argv[2],argv[4]);return 0;}
 if(argc!=4)return 64;
 bool restore=!strcmp(argv[1],"--restore-prefix")||!strcmp(argv[1],"--check-restore")||!strcmp(argv[1],"--verify-restored");
 if(!restore&&strcmp(argv[1],"--check-image")&&strcmp(argv[1],"--write")&&strcmp(argv[1],"--verify-written"))return 64;
 guard_load(argv[3]);size_t bytes;unsigned char *b=restore?previous(argv[2]):image(argv[2],&bytes);
 if(!strcmp(argv[1],"--check-image")||!strcmp(argv[1],"--check-restore")){free(b);return 0;}
 if(!strcmp(argv[1],"--verify-written")||!strcmp(argv[1],"--verify-restored")){
  bind_runtime();lock_prefix(false);
  int source=part(0,O_RDONLY),view=part(2,O_RDONLY);protected(source);compare(view,b,0,PREFIX);close(view);close(source);free(b);puts("DPN_INSTALLED_PREFIX_ECC_AND_PROTECTION_VERIFIED");return 0;
 }
 bind_runtime();ram_guard();lock_prefix(true);int source=part(0,O_RDONLY),fd=part(2,O_RDWR);protected(source);
 if(!restore){char prior[65];hashfd(source,firmware_start,PREFIX,prior);if(strcmp(prior,guard.previous_prefix))stop("firmware changed since guard snapshot");}
#ifndef DPN_UPGRADE_HOST_TEST
 for(int64_t off=0;off<PREFIX;off+=BLOCK)if(ioctl(fd,MEMGETBADBLOCK,&off)!=0)stop("firmware bad-block guard");
#endif
 puts("PREFIX_ERASE_BEGIN");for(size_t off=0;off<PREFIX;off+=BLOCK)erase(fd,off);
 for(size_t off=BLOCK;off<PREFIX;off+=PAGE)program(fd,off,b+off);compare(fd,b,BLOCK,PREFIX);puts("BODY_READBACK_OK_HEADER_STILL_ERASED");
 for(size_t off=0;off<BLOCK;off+=PAGE)program(fd,off,b+off);compare(fd,b,0,PREFIX);puts("PREFIX_READBACK_OK");
 protected(source);puts(restore?"DPN_PREVIOUS_PREFIX_RESTORED_AND_PROTECTED":"DPN_INSTALL_WRITE_COMPLETE_PROTECTED_REGIONS_UNCHANGED");close(fd);close(source);free(b);return 0;
}
