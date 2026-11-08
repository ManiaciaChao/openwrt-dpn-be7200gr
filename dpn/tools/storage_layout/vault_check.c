/* SPDX-License-Identifier: GPL-2.0-only */
/* Read-only vault validation and explicit RAM-only identity extraction. */
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
#define SIZE 0x400000U
#define HEADER 4096U
static void need(bool ok,const char *why){if(!ok){fprintf(stderr,"DPN_VAULT_STOP %s errno=%d\n",why,errno);exit(2);}}
static uint32_t le32(const unsigned char *b){return b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;}
static void readat(int fd,void *buf,size_t size,uint64_t off){unsigned char *p=buf;while(size){ssize_t n=pread(fd,p,size,off);need(n>0,"complete vault/ART read");p+=n;size-=n;off+=n;}}
static void sha(const void *b,size_t n,unsigned char h[32]){SHA2_CTX c;SHA256Init(&c);SHA256Update(&c,b,n);SHA256Final(h,&c);}
static void digest_equal(const void *b,size_t n,const unsigned char expected[32],const char *why){unsigned char h[32];sha(b,n,h);need(!memcmp(h,expected,32),why);}
static void allff(const unsigned char *b,size_t n){for(size_t i=0;i<n;i++)need(b[i]==255,"nonempty vault reserved/alignment/tail");}
static int nibble(unsigned char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
static void factory_fingerprint(const char *path,unsigned char h[32]){
 unsigned char eeprom[0x1e00],ascii[17],mac[6];SHA2_CTX c;
 int f=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);need(f>=0,"ART read-only open");
 readat(f,eeprom,sizeof eeprom,0x40000);readat(f,ascii,sizeof ascii,0x301055);close(f);
 need(eeprom[0]==0x92&&eeprom[1]==0x79,"factory EEPROM marker");
 for(unsigned i=0;i<6;i++){int a=nibble(ascii[3*i]),b=nibble(ascii[3*i+1]);need(a>=0&&b>=0&&(i==5||ascii[3*i+2]==':'),"factory MAC shape");mac[i]=(unsigned char)(a*16+b);}
 need(!(mac[0]&1)&&(mac[0]|mac[1]|mac[2]|mac[3]|mac[4]|mac[5]),"factory MAC identity");
 static const unsigned char prefix[]="DPN-BE7200GR-factory-v1";
 SHA256Init(&c);SHA256Update(&c,prefix,sizeof prefix);SHA256Update(&c,eeprom,sizeof eeprom);SHA256Update(&c,mac,sizeof mac);SHA256Final(h,&c);
}
static void output(int dir,const char *name,const unsigned char *data,size_t n){
 int f=openat(dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);need(f>=0,"new RAM identity file only");
 while(n){ssize_t k=write(f,data,n);need(k>0,"complete RAM identity write");data+=k;n-=k;}
 need(!fsync(f)&&!close(f),"identity sync/close");
}
int main(int argc,char **argv){
 bool extract=argc==5&&!strcmp(argv[1],"--extract-identity");
 if(!extract&&!(argc==4&&!strcmp(argv[1],"--check")))return 64;
 int f=open(argv[2],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;need(f>=0&&!fstat(f,&st),"vault read-only open");
 if(S_ISCHR(st.st_mode)){struct mtd_info_user m;need(!ioctl(f,MEMGETINFO,&m)&&m.size==SIZE&&!(m.flags&MTD_WRITEABLE),"read-only vault MTD required");}
 else need(S_ISREG(st.st_mode)&&st.st_size==SIZE,"exact 4 MiB vault file required");
 unsigned char *b=malloc(SIZE),identity[32];need(b,"vault memory");readat(f,b,SIZE,0);close(f);
 need(!memcmp(b,"DPNVLT1",8)&&le32(b+8)==1&&le32(b+12)==SIZE,"vault magic/version/size");
 digest_equal(b,HEADER-32,b+HEADER-32,"vault header digest");factory_fingerprint(argv[3],identity);
 need(!memcmp(identity,b+16,32),"vault belongs to another device");
 need(le32(b+144)==0x5380000&&le32(b+148)==0x1980000&&le32(b+152)==3&&!le32(b+156),"vendor state metadata");
 need(le32(b+280)==0x6480000&&le32(b+284)==0x1900000&&le32(b+288)==0xb780000&&le32(b+292)==0x80000,"essential state ranges");
 allff(b+296,HEADER-32-296);
 uint32_t at=HEADER,off[3],length[3];
 for(unsigned i=0;i<3;i++){
  const unsigned char *e=b+160+i*40;off[i]=le32(e);length[i]=le32(e+4);
  need(off[i]==at&&length[i]&&off[i]<SIZE&&length[i]<=SIZE-off[i],"vault object bounds/order");
  digest_equal(b+off[i],length[i],e+8,"vault object digest");
  uint32_t end=(off[i]+length[i]+4095)&~4095U;need(end<=SIZE,"vault alignment extent");
  allff(b+off[i]+length[i],end-off[i]-length[i]);at=end;
 }
 allff(b+at,SIZE-at);
 need(length[1]<=16384&&!memchr(b+off[1],0,length[1])&&length[2]<=4096,"identity object shape");
 if(extract){
  int dir=open(argv[4],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);struct stat s;struct statfs fs;
  need(dir>=0&&!fstat(dir,&s)&&s.st_uid==geteuid()&&!(s.st_mode&077)&&!fstatfs(dir,&fs)&&
       (fs.f_type==0x01021994||fs.f_type==0x858458f6),"private RAM directory required");
  output(dir,"authorized_keys",b+off[1],length[1]);output(dir,"dropbear_ed25519_host_key",b+off[2],length[2]);close(dir);
 }
 free(b);puts(extract?"DPN_VAULT_IDENTITY_VERIFIED_AND_EXTRACTED_TO_RAM":"DPN_VAULT_DEVICE_HEADER_OBJECT_DIGESTS_VERIFIED_READONLY");return 0;
}
