/* SPDX-License-Identifier: GPL-2.0-only */
/* Detach a prepared root-owned RAM script without relying on stock setsid. */
#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
static void fail(const char *s){perror(s);exit(2);}
int main(int argc,char **argv){
 if(argc!=3||geteuid()!=0)return 2;
 struct stat st;if(lstat(argv[1],&st)||!S_ISREG(st.st_mode)||st.st_uid!=0||(st.st_mode&022)||st.st_size>16384)fail("prepared script");
 int log=open(argv[2],O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);if(log<0)fail("new private log");
 pid_t p=fork();if(p<0)fail("fork");
 if(p){printf("RAM_EXECUTOR_CREATED=%ld\n",(long)p);close(log);return 0;}
 if(setsid()<0)_exit(3);p=fork();if(p<0)_exit(4);if(p)_exit(0);
 int null=open("/dev/null",O_RDONLY);if(null<0)_exit(5);
 if(dup2(null,0)<0||dup2(log,1)<0||dup2(log,2)<0)_exit(6);
 for(int i=3;i<1024;i++)close(i);
 execl("/bin/sh","sh",argv[1],(char*)NULL);perror("execute prepared RAM script");_exit(7);
}
