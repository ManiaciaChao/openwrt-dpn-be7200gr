/* SPDX-License-Identifier: GPL-2.0-only */
/* Exercise the actual writer helpers on bounded regular host files, never MTD. */
#define DPN_UPGRADE_HOST_TEST
#define main dpn_unused_writer_main
#include "writer.c"
#undef main
int main(int argc,char **argv){
 if(argc!=2)return 64;
 int fd=open(argv[1],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<0||st.st_size>2*1024*1024)return 65;
 size_t n=st.st_size;unsigned char *b=malloc(n?n:1),d[20];char h[65],h1[41],stream[65];
 if(!b)return 66;readat(fd,b,n,0);sha(b,n,h);digest1(b,n,d);hex(d,20,h1);hashfd(fd,0,n,stream);
 printf("%s\n%s\n%s\n",h,h1,stream);free(b);close(fd);return 0;
}
