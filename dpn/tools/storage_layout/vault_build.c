/* SPDX-License-Identifier: GPL-2.0-only */
/* Per-device vault generation in RAM. Never opens a Flash device for writing. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
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
#include <zlib.h>
#define SIZE 0x400000U
#define HEADER 4096U
#define ESSENTIAL 0x1980000U
#define ART 0x1bc80000U
static void need(bool b,const char *s){if(!b){fprintf(stderr,"DPN_VAULT_BUILD_STOP %s errno=%d\n",s,errno);exit(2);}}
static void rd(int f,void *b,size_t n,uint64_t o){unsigned char *p=b;while(n){ssize_t k=pread(f,p,n,o);need(k>0,"complete read");p+=k;o+=k;n-=k;}}
static void sha(const void *b,size_t n,unsigned char h[32]){SHA2_CTX c;SHA256Init(&c);SHA256Update(&c,b,n);SHA256Final(h,&c);}
static void digest(int f,uint64_t o,size_t n,unsigned char h[32]){unsigned char b[65536];SHA2_CTX c;SHA256Init(&c);while(n){size_t k=n<sizeof b?n:sizeof b;rd(f,b,k,o);SHA256Update(&c,b,k);o+=k;n-=k;}SHA256Final(h,&c);}
static void put32(unsigned char *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(n>>(i*8));}
static unsigned char *small(const char *path,size_t limit,size_t *size){
 int f=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 need(f>=0&&!fstat(f,&st)&&S_ISREG(st.st_mode)&&st.st_size>0&&(uint64_t)st.st_size<=limit,"bounded identity file");
 *size=st.st_size;unsigned char *b=malloc(*size);need(b,"identity memory");rd(f,b,*size,0);close(f);return b;
}
static int nibble(unsigned char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
int main(int argc,char **argv){
 need(argc==7&&!strcmp(argv[1],"--build"),"usage --build RAW_RO FACTORY_BOOT_SLOT AUTHORIZED_KEYS HOST_KEY OUTPUT");
 need(!strcmp(argv[3],"0")||!strcmp(argv[3],"1"),"unambiguous factory slot");
 int raw=open(argv[2],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 need(raw>=0&&!fstat(raw,&st),"read-only source");
#ifdef DPN_VAULT_BUILD_HOST_TEST
 need(S_ISREG(st.st_mode)&&st.st_size==0x20000000,"exact synthetic NAND size");
#else
 struct mtd_info_user m;need(S_ISCHR(st.st_mode)&&!ioctl(raw,MEMGETINFO,&m)&&m.type==MTD_NANDFLASH&&m.size==0x20000000&&m.writesize==4096&&m.oobsize==256&&m.erasesize==262144&&!(m.flags&MTD_WRITEABLE),"qualified read-only physical NAND");
 struct statfs fs;need(!statfs("/",&fs)&&(fs.f_type==0x01021994||fs.f_type==0x858458f6),"RAM installer root");
#endif
 unsigned char *b=malloc(SIZE),*plain=malloc(ESSENTIAL),*check=malloc(ESSENTIAL);need(b&&plain&&check,"vault memory");memset(b,255,SIZE);
 memcpy(b,"DPNVLT1",8);put32(b+8,1);put32(b+12,SIZE);
 unsigned char eeprom[0x1e00],ascii[17],mac[6];rd(raw,eeprom,sizeof eeprom,ART+0x40000);rd(raw,ascii,sizeof ascii,ART+0x301055);
 need(eeprom[0]==0x92&&eeprom[1]==0x79,"factory EEPROM marker");
 for(unsigned i=0;i<6;i++){int x=nibble(ascii[3*i]),y=nibble(ascii[3*i+1]);need(x>=0&&y>=0&&(i==5||ascii[3*i+2]==':'),"factory MAC shape");mac[i]=(unsigned char)(x*16+y);}
 need(!(mac[0]&1)&&(mac[0]|mac[1]|mac[2]|mac[3]|mac[4]|mac[5]),"factory MAC identity");
 SHA2_CTX c;static const unsigned char prefix[]="DPN-BE7200GR-factory-v1";
 SHA256Init(&c);SHA256Update(&c,prefix,sizeof prefix);SHA256Update(&c,eeprom,sizeof eeprom);SHA256Update(&c,mac,sizeof mac);SHA256Final(b+16,&c);
 uint64_t stock=!strcmp(argv[3],"1")?0x80000:0x3280000;
 unsigned char magic[4];rd(raw,magic,4,stock);need(!memcmp(magic,"\x01\x00\x64\xaa",4),"opposite stock slot FIP");
 rd(raw,magic,4,0x4280000);need(memcmp(magic,"DPNV",4),"existing vault: refuse automatic reinstall");
 digest(raw,stock,0x3200000,b+48);digest(raw,0x6480000,0x5380000,b+80);
 rd(raw,plain,0x1900000,0x6480000);rd(raw,plain+0x1900000,0x80000,0xb780000);sha(plain,ESSENTIAL,b+112);
 put32(b+144,0x5380000);put32(b+148,ESSENTIAL);put32(b+152,3);put32(b+156,0);
 put32(b+280,0x6480000);put32(b+284,0x1900000);put32(b+288,0xb780000);put32(b+292,0x80000);
 unsigned char *packed=malloc(SIZE);need(packed,"gzip memory");
 z_stream z={0};need(deflateInit2(&z,9,Z_DEFLATED,31,8,Z_DEFAULT_STRATEGY)==Z_OK,"gzip init");
 z.next_in=plain;z.avail_in=ESSENTIAL;z.next_out=packed;z.avail_out=SIZE;
 need(deflate(&z,Z_FINISH)==Z_STREAM_END,"essential state exceeds vault capacity");size_t packed_size=z.total_out;need(deflateEnd(&z)==Z_OK,"gzip finish");
 z_stream u={0};need(inflateInit2(&u,31)==Z_OK,"verify gzip init");u.next_in=packed;u.avail_in=packed_size;u.next_out=check;u.avail_out=ESSENTIAL;
 need(inflate(&u,Z_FINISH)==Z_STREAM_END&&u.total_out==ESSENTIAL&&u.total_in==packed_size&&!memcmp(plain,check,ESSENTIAL),"gzip byte comparison");need(inflateEnd(&u)==Z_OK,"verify gzip finish");free(plain);free(check);
 size_t sizes[3]={packed_size,0,0};unsigned char *objects[3]={packed,NULL,NULL};
 objects[1]=small(argv[4],16384,&sizes[1]);objects[2]=small(argv[5],4096,&sizes[2]);
 need(sizes[1]>=13&&!memcmp(objects[1],"ssh-ed25519 ",12)&&!memchr(objects[1],0,sizes[1]),"generated recovery public key");
 uint32_t at=HEADER;
 for(unsigned i=0;i<3;i++){
  uint32_t end=(at+sizes[i]+4095)&~4095U;need(end<=SIZE,"vault object capacity");
  put32(b+160+i*40,at);put32(b+164+i*40,sizes[i]);sha(objects[i],sizes[i],b+168+i*40);memcpy(b+at,objects[i],sizes[i]);at=end;free(objects[i]);
 }
 sha(b,HEADER-32,b+HEADER-32);
 /* Hashes must still describe the source at the end of preparation. */
 unsigned char h[32];digest(raw,stock,0x3200000,h);need(!memcmp(h,b+48,32),"stock changed during preparation");digest(raw,0x6480000,0x5380000,h);need(!memcmp(h,b+80,32),"vendor state changed during preparation");close(raw);
 int out=open(argv[6],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);need(out>=0,"new private vault output only");
 size_t left=SIZE;unsigned char *p=b;while(left){ssize_t k=write(out,p,left);need(k>0,"complete vault output");p+=k;left-=k;}need(!fsync(out)&&!close(out),"vault sync");free(b);
 puts("DEVICE_VAULT_PREPARED_IN_RAM_NO_FULL_BACKUP_NO_FLASH_WRITE");return 0;
}
