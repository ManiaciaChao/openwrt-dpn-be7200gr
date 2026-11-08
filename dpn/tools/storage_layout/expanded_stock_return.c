/* SPDX-License-Identifier: GPL-2.0-only */
/* Fixed stock0 50 MiB + vendor83.5 MiB return; REC/VLT/ART/BMT protected. */
#include "native_io.h"
#include <libfdt.h>
#include <sys/mman.h>
#include <sys/wait.h>
#define STOCK_SIZE 0x3200000U
#define VENDOR_SIZE 0x5380000U
#define REC_START 0x3280000U
#define ART_START 0x1bc80000U
struct guard {char magic[8],boot[37],recovery[65],input[2][65],before[2][65],protected[3][65];};
_Static_assert(sizeof(struct guard)==565,"fixed byte-only guard representation");
static void protected_hashes(int raw,char h[3][65]){digest(raw,0,0x80000,h[0]);digest(raw,0x3280000,0x3200000,h[1]);digest(raw,0xb800000,0x14800000,h[2]);}
static int nibble(unsigned char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
static void vault_inputs(int raw,char stock[65],char vendor[65]){
#ifndef DPN_LAYOUT4_HOST_TEST
 pid_t pid=fork();require(pid>=0,"vault check process");if(!pid){execl("/usr/libexec/dpn-vault-check","dpn-vault-check","--check","/dev/mtd3ro","/sys/bus/nvmem/devices/dpn-art/nvmem",(char *)NULL);_exit(127);}int status;require(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0,"complete NAND vault/identity validation");
#endif
 unsigned char v[4096],h[32],eeprom[0x1e00],ascii[17],mac[6];readat(raw,v,sizeof v,0x4280000);
 require(!memcmp(v,"DPNVLT1",8)&&little32(v+8)==1&&little32(v+12)==0x400000&&little32(v+144)==VENDOR_SIZE,"vault header/version/vendor size");memory_sha(v,4064,h);require(!memcmp(h,v+4064,32),"vault header SHA");
 readat(raw,eeprom,sizeof eeprom,ART_START+0x40000);readat(raw,ascii,sizeof ascii,ART_START+0x301055);require(eeprom[0]==0x92&&eeprom[1]==0x79,"factory EEPROM marker");
 for(unsigned i=0;i<6;i++){int a=nibble(ascii[3*i]),b=nibble(ascii[3*i+1]);require(a>=0&&b>=0&&(i==5||ascii[3*i+2]==':'),"factory MAC shape");mac[i]=a*16+b;}
 SHA2_CTX c;static const unsigned char prefix[]="DPN-BE7200GR-factory-v1";SHA256Init(&c);SHA256Update(&c,prefix,sizeof prefix);SHA256Update(&c,eeprom,sizeof eeprom);SHA256Update(&c,mac,sizeof mac);SHA256Final(h,&c);require(!memcmp(h,v+16,32),"vault belongs to this factory identity");hex(v+48,stock);hex(v+80,vendor);
}
static void valid_stock(int fd){
 const unsigned char *b=mmap(NULL,STOCK_SIZE,PROT_READ,MAP_PRIVATE,fd,0);require(b!=MAP_FAILED,"stock read-only mapping");
 require(little32(b)==0xaa640001&&little64(b+152)==0x2000,"stock FIP payload");uint64_t n=little64(b+160);require(n>296&&n<=STOCK_SIZE-0x2000&&little32(b+0x2000)==0x32524448&&little32(b+0x2004)==256&&little32(b+0x2008)==n,"stock HDR2 bounds");
 n-=256;const void *fit=b+0x2100;require(!fdt_check_full(fit,n)&&fdt_totalsize(fit)==n,"stock FIT structure");uint32_t crc=~0U;for(size_t i=0;i<n;i++){crc^=b[0x2100+i];for(unsigned j=0;j<8;j++)crc=(crc>>1)^((0U-(crc&1))&0xedb88320U);}require(crc==little32(b+0x200c),"stock HDR2 CRC");require(fdt_path_offset(fit,"/images/kernel@1")>=0&&fdt_path_offset(fit,"/images/fdt@1")>=0&&fdt_path_offset(fit,"/images/filesystem@1")>=0,"stock FIT components");munmap((void *)b,STOCK_SIZE);
}
static void write_body(int target,int input,uint32_t start,uint32_t bytes,const char *phase){unsigned char *b=malloc(DPN_BLOCK),*check=malloc(DPN_BLOCK);require(b&&check,"block buffers");for(uint32_t off=start;off<bytes;off+=DPN_BLOCK){readat(input,b,DPN_BLOCK,off);erase_block(target,off,bytes);for(unsigned p=0;p<DPN_BLOCK;p+=DPN_PAGE)program_page(target,b+p,off+p,bytes,phase);readat(target,check,DPN_BLOCK,off);require(!memcmp(b,check,DPN_BLOCK),"body block readback");}free(b);free(check);}
int main(int argc,char **argv){
 setvbuf(stdout,NULL,_IOLBF,0);
 require(argc==6&&(!strcmp(argv[1],"--snapshot")||!strcmp(argv[1],"--write")),"usage --snapshot|--write STOCK50 VENDOR83.5 PINNED_RECOVERY16_SHA GUARD");bool commit=!strcmp(argv[1],"--write");struct guard g={.magic="DPNRET4"},old;ram_detached_mode("stock_return",g.boot);require(digest_valid(argv[4]),"externally pinned known recovery16 SHA");strcpy(g.recovery,argv[4]);
 int raw=open_mtd(0,"dpn-physical-nand-ro",0x20000000,false),target[2]={open_mtd(5,"dpn-layout4-stock-target",STOCK_SIZE,true),open_mtd(6,"dpn-layout4-vendor-target",VENDOR_SIZE,true)};
 unsigned char selected;readat(raw,&selected,1,0x1bfc0000);require(selected=='1',"known-good independent recovery must be selected before restore");
 char rec[65];digest(raw,REC_START,0x1000000,rec);require(!strcmp(rec,g.recovery),"known-good NAND recovery16 unchanged");
 char pinned[2][65];vault_inputs(raw,pinned[0],pinned[1]);int input[2]={open_input(argv[2],STOCK_SIZE),open_input(argv[3],VENDOR_SIZE)};uint32_t bytes[2]={STOCK_SIZE,VENDOR_SIZE};
 for(unsigned i=0;i<2;i++){digest(input[i],0,bytes[i],g.input[i]);require(!strcmp(g.input[i],pinned[i]),"stock/vendor input SHA matches original device vault");digest(target[i],0,bytes[i],g.before[i]);}
 valid_stock(input[0]);protected_hashes(raw,g.protected);
 if(!commit){int f=open(argv[5],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);require(f>=0&&write(f,&g,sizeof g)==sizeof g&&!fsync(f)&&!close(f),"exclusive same-boot guard snapshot");for(unsigned i=0;i<2;i++){close(input[i]);close(target[i]);}close(raw);puts("EXPANDED_STOCK_RETURN_INPUTS_FACTORY_BOUND_RECOVERY_SELECTED_PROTECTED_SNAPSHOT_VERIFIED");return 0;}
 int f=open(argv[5],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;require(f>=0&&!fstat(f,&st)&&S_ISREG(st.st_mode)&&st.st_size==sizeof old,"guard size");readat(f,&old,sizeof old,0);close(f);require(!memcmp(&old,&g,sizeof g),"same boot, recovery, inputs, targets and protected regions");
 /* Main header is invalid until every restored vendor byte is verified. */
 puts("EXPANDED_RETURN_SAME_BOOT_GUARD_RECHECKED_RECOVERY_SELECTED");
 erase_block(target[0],0,STOCK_SIZE);write_body(target[1],input[1],0,VENDOR_SIZE,"vendor");puts("EXPANDED_RETURN_VENDOR83_5_BLOCK_READBACK_COMPLETE");write_body(target[0],input[0],DPN_BLOCK,STOCK_SIZE,"stock-body");puts("EXPANDED_RETURN_STOCK_BODY_BLOCK_READBACK_COMPLETE_HEADER_STILL_INVALID");
 char check[65],expected[65],after[3][65];digest(target[1],0,VENDOR_SIZE,check);require(!strcmp(check,g.input[1]),"complete vendor83.5 readback before main header");digest(input[0],DPN_BLOCK,STOCK_SIZE-DPN_BLOCK,expected);digest(target[0],DPN_BLOCK,STOCK_SIZE-DPN_BLOCK,check);require(!strcmp(check,expected),"stock body readback before main header");protected_hashes(raw,after);require(!memcmp(after,g.protected,sizeof after),"protected NAND unchanged before main header");
 puts("EXPANDED_RETURN_ALL_PROTECTED_REGIONS_MATCH_BEFORE_HEADER_COMMIT");unsigned char header[DPN_BLOCK];readat(input[0],header,sizeof header,0);for(unsigned p=0;p<DPN_BLOCK;p+=DPN_PAGE)program_page(target[0],header+p,p,STOCK_SIZE,"stock-header");puts("EXPANDED_RETURN_HEADER_COMMITTED_FINAL_COMPLETE_READBACK_IN_PROGRESS");
 for(unsigned i=0;i<2;i++){digest(target[i],0,bytes[i],check);require(!strcmp(check,g.input[i]),"complete stock and vendor readback");}
 protected_hashes(raw,after);require(!memcmp(after,g.protected,sizeof after),"recovery/vault/bootloader/ART/BMT and all outside targets unchanged");for(unsigned i=0;i<2;i++){close(input[i]);close(target[i]);}close(raw);puts("EXPANDED_STOCK50_AND_VENDOR83_5_COMMITTED_HEADER_LAST_RECOVERY_VAULT_ART_BMT_PROTECTED");return 0;
}
