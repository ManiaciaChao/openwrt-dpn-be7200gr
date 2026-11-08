/* SPDX-License-Identifier: GPL-2.0-only */
/* A per-install initrd overlay. Private material stays on the target's tmpfs;
 * this helper's binary and the generic kernel contain no owner's credentials. */
#define _FILE_OFFSET_BITS 64
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <ctype.h>
static void fail(const char *s){perror(s);exit(2);}
static unsigned char *readfile(const char *p,size_t *n){
 int f=open(p,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 if(f<0||fstat(f,&st)||!S_ISREG(st.st_mode)||st.st_size<1||st.st_size>16384)fail("session input");
 *n=st.st_size;unsigned char *b=malloc(*n+1);if(!b)fail("allocation");size_t k=0;
 while(k<*n){ssize_t r=read(f,b+k,*n-k);if(r<=0)fail("session read");k+=r;}
 b[*n]=0;close(f);return b;
}
static void bytes(const void *b,size_t n){if(fwrite(b,1,n,stdout)!=n)fail("archive write");}
static void pad(size_t n){static const char z[4]={0};if(n%4)bytes(z,4-n%4);}
static void entry(const char *name,unsigned mode,const void *data,size_t n){
 char header[111];static unsigned inode=1;size_t ns=strlen(name)+1;
 int len=snprintf(header,sizeof header,"070701%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x",inode++,mode,0,0,1,0,(unsigned)n,0,0,0,0,(unsigned)ns,0);
 if(len!=110)fail("archive header");bytes(header,110);bytes(name,ns);pad(110+ns);bytes(data,n);pad(n);
}
int main(int argc,char **argv){
 if(argc!=4){fputs("usage: mk-session-initrd OWNER_PUBLIC_KEY SESSION_HOST_KEY HEX_SESSION_ID > session.cpio\n",stderr);return 2;}
 if(strlen(argv[3])!=32)return 2;for(unsigned i=0;i<32;i++)if(!isxdigit((unsigned char)argv[3][i]))return 2;
 size_t pn,kn;unsigned char *pub=readfile(argv[1],&pn),*key=readfile(argv[2],&kn);
 if(pn<20||memcmp(pub,"ssh-ed25519 ",12)||kn<32)return 2;
 entry("etc",0040755,NULL,0);entry("etc/dpn-provision",0040700,NULL,0);
 entry("etc/dpn-provision/authorized_keys",0100600,pub,pn);
 entry("etc/dpn-provision/host_ed25519_key",0100600,key,kn);
 char session[34];snprintf(session,sizeof session,"%s\n",argv[3]);
 entry("etc/dpn-provision/session",0100600,session,33);
 entry("TRAILER!!!",0,NULL,0);if(fflush(stdout))fail("archive flush");free(key);free(pub);return 0;
}
