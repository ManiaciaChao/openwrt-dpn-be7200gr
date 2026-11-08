/* SPDX-License-Identifier: GPL-2.0-only */
#include "image4.h"
#include <sys/mman.h>
int main(int argc,char **argv){
 require(argc==4&&(!strcmp(argv[3],"normal")||!strcmp(argv[3],"recovery")),"usage FIP ROOT_SQUASHFS normal|recovery");
 int f=open(argv[1],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;require(f>=0&&!fstat(f,&st)&&S_ISREG(st.st_mode)&&st.st_size>0x2100&&st.st_size<=0x1000000,"bounded regular FIP");size_t n=st.st_size;const unsigned char *b=mmap(NULL,n,PROT_READ,MAP_PRIVATE,f,0);require(b!=MAP_FAILED,"firmware read-only mapping");
 if(!strcmp(argv[3],"recovery")&&!strcmp(argv[2],"-")){validate_image4(b,n,"recovery",NULL);puts("LAYOUT4_RECOVERY_FIP_VERIFIED");return 0;}
 int root=open(argv[2],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);require(root>=0&&!fstat(root,&st)&&S_ISREG(st.st_mode)&&st.st_size>=96&&st.st_size<=0x4000000,"bounded regular root");unsigned char sq[96],h[32];readat(root,sq,96,0);require(little32(sq)==0x73717368&&little64(sq+40)<=(uint64_t)st.st_size,"root SquashFS superblock");char hexsha[65];digest(root,0,st.st_size,hexsha);for(unsigned i=0;i<32;i++){unsigned x;require(sscanf(hexsha+2*i,"%2x",&x)==1,"digest");h[i]=x;}
 validate_image4(b,n,argv[3],h);puts("LAYOUT4_FIP_COMPONENTS_DTB_AND_ACTUAL_UBI_ROOT_HASH_VERIFIED");return 0;
}
