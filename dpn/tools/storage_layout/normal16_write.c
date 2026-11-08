/* SPDX-License-Identifier: GPL-2.0-only */
/* Main prefix only, independent recovery selected, header last. */
#include "image4.h"
#include <sys/mman.h>
#define SIZE 0x1000000U
struct guard {char magic[8],boot[37],image[65],root[65],recovery[65],before[65],protected[2][65];};
static void protected_hashes(int raw,char hashes[2][65]){digest(raw,0,0x80000,hashes[0]);digest(raw,0x1080000,0x1ef80000,hashes[1]);}
int main(int argc,char **argv){
 setvbuf(stdout,NULL,_IOLBF,0);require(argc==7&&(!strcmp(argv[1],"--snapshot")||!strcmp(argv[1],"--write")),"usage --snapshot|--write IMAGE16 ROOT_SQUASHFS IMAGE_SHA RECOVERY16_SHA GUARD");
 bool commit=!strcmp(argv[1],"--write");struct guard g={.magic="DPNFW4"},old;ram_detached_mode("update",g.boot);
 require(digest_valid(argv[4])&&digest_valid(argv[5]),"externally pinned firmware and recovery SHA");strcpy(g.recovery,argv[5]);
 int raw=open_mtd(0,"dpn-physical-nand-ro",0x20000000,false),target=open_mtd(5,"dpn-layout4-normal",SIZE,true);
 unsigned char flag;readat(raw,&flag,1,0x1bfc0000);require(flag=='1',"independent recovery must remain selected");char h[65];digest(raw,0x3280000,SIZE,h);require(!strcmp(h,g.recovery),"known-good recovery16 readback");
 int input=open_input(argv[2],SIZE);digest(input,0,SIZE,g.image);require(!strcmp(g.image,argv[4]),"complete image SHA pinned");
 int root=open(argv[3],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;require(root>=0&&!fstat(root,&st)&&S_ISREG(st.st_mode)&&st.st_size>=96&&st.st_size<=0x4000000,"bounded regular SquashFS root");unsigned char sq[96];readat(root,sq,sizeof sq,0);require(little32(sq)==0x73717368&&little64(sq+40)<=((uint64_t)st.st_size),"SquashFS root superblock");digest(root,0,st.st_size,g.root);unsigned char rootsha[32];for(unsigned i=0;i<32;i++){unsigned x;require(sscanf(g.root+2*i,"%2x",&x)==1,"root digest");rootsha[i]=x;}close(root);
 const unsigned char *b=mmap(NULL,SIZE,PROT_READ,MAP_PRIVATE,input,0);require(b!=MAP_FAILED,"read-only firmware mapping");validate_image4(b,SIZE,"normal",rootsha);
 digest(target,0,SIZE,g.before);protected_hashes(raw,g.protected);
 if(!commit){int f=open(argv[6],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);require(f>=0&&write(f,&g,sizeof g)==sizeof g&&!fsync(f)&&!close(f),"exclusive same-boot guard");puts("NORMAL16_INPUT_ROOT_BINDING_AND_496_MIB_PROTECTED_SNAPSHOT_VERIFIED");return 0;}
 int f=open_input(argv[6],sizeof old);readat(f,&old,sizeof old,0);close(f);require(!memcmp(&old,&g,sizeof g),"same boot/image/root/recovery/target/protected regions");
 erase_block(target,0,SIZE);unsigned char check[DPN_BLOCK];
 for(uint32_t off=DPN_BLOCK;off<SIZE;off+=DPN_BLOCK){erase_block(target,off,SIZE);for(unsigned p=0;p<DPN_BLOCK;p+=DPN_PAGE)program_page(target,b+off+p,off+p,SIZE,"body");readat(target,check,sizeof check,off);require(!memcmp(check,b+off,sizeof check),"body block readback");}
 char hashes[2][65];protected_hashes(raw,hashes);require(!memcmp(hashes,g.protected,sizeof hashes),"all outside 16 MiB unchanged before header");puts("NORMAL16_BODY_VERIFIED_RECOVERY_SELECTED_COMMITTING_HEADER_LAST");
 for(unsigned p=0;p<DPN_BLOCK;p+=DPN_PAGE)program_page(target,b+p,p,SIZE,"header");digest(target,0,SIZE,h);require(!strcmp(h,g.image),"full 16 MiB readback");protected_hashes(raw,hashes);require(!memcmp(hashes,g.protected,sizeof hashes),"496 MiB outside prefix unchanged");
 puts("NORMAL16_COMMITTED_HEADER_LAST_FULL_READBACK_496_MIB_UNCHANGED_RECOVERY_SELECTED");return 0;
}
