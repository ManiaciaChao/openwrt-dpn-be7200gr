/* SPDX-License-Identifier: MIT
 * Physical reads only. Never opens a device writable or issues a write ioctl.
 * raw: 4096 main + 256 spare per physical page; ecc: 4096 corrected main.
 * markers: byte 0 of OOB in both first and second pages of every block.
 */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mtd/mtd-user.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
static void fail(const char *s) { perror(s); exit(1); }
static void output(const void *buf, size_t n) {
 const unsigned char *b=buf;
 while(n) { ssize_t r=write(1,b,n); if(r<0) { if(errno==EINTR)continue;fail("stdout"); } if(!r)exit(2); b+=r;n-=r; }
}
int main(int argc,char **argv) {
 if(argc<2 || (strcmp(argv[1],"raw") && strcmp(argv[1],"ecc") && strcmp(argv[1],"markers"))) {
  fprintf(stderr,"usage: nand_readonly_dump raw|ecc|markers [start_page [page_count]]\n");return 2;
 }
 int markers=!strcmp(argv[1],"markers"),raw=strcmp(argv[1],"ecc")!=0;
 unsigned long start=argc>2?strtoul(argv[2],NULL,0):0;
 unsigned long count=argc>3?strtoul(argv[3],NULL,0):131072-start;
 if(start>=131072 || !count || count>131072-start || (markers && argc!=2))return 2;
 int fd=open("/dev/mtd0",O_RDONLY|O_CLOEXEC);if(fd<0)fail("open read-only");
 struct mtd_info_user info;
 if(ioctl(fd,MEMGETINFO,&info))fail("MEMGETINFO");
 if(info.type!=MTD_NANDFLASH || info.size!=536870912 || info.writesize!=4096 || info.oobsize!=256 || info.erasesize!=262144 || (info.flags & MTD_WRITEABLE)) {
  fprintf(stderr,"Refusing unexpected geometry or writable MTD\n");return 3;
 }
 unsigned char page[4096],oob[256];
 uint64_t corrected=0,failed=0;unsigned maxbits=0,bad=0;
 for(unsigned long p=start;p<start+count;p++) {
  if(markers && p%64>=2)continue;
  struct mtd_read_req req={0};req.start=(uint64_t)p*4096;req.len=sizeof(page);req.ooblen=sizeof(oob);
  req.usr_data=(uintptr_t)page;req.usr_oob=(uintptr_t)oob;req.mode=raw?MTD_OPS_RAW:MTD_OPS_PLACE_OOB;
  int ret=ioctl(fd,MEMREAD,&req);
  if(ret<0 && errno!=EBADMSG && errno!=EUCLEAN)fail("MEMREAD");
  if(ret<0)fprintf(stderr,"ECC_EVENT page=%lu errno=%d corrected=%u failed=%u maxbits=%u\n",p,errno,req.ecc_stats.corrected_bitflips,req.ecc_stats.uncorrectable_errors,req.ecc_stats.max_bitflips);
  if(req.len!=sizeof(page) || req.ooblen!=sizeof(oob)) { fprintf(stderr,"Short page %lu\n",p);return 4; }
  corrected+=req.ecc_stats.corrected_bitflips;failed+=req.ecc_stats.uncorrectable_errors;
  if(req.ecc_stats.max_bitflips>maxbits)maxbits=req.ecc_stats.max_bitflips;
  if(markers) {
   if(oob[0]!=255) {printf("{\"block\":%lu,\"page\":%lu,\"marker\":%u}\n",p/64,p%64,oob[0]);bad++;}
  }else { output(page,sizeof(page));if(raw)output(oob,sizeof(oob)); }
  if((p+1)%4096==0)fprintf(stderr,"READ_PROGRESS page=%lu/%lu\n",p+1,start+count);
 }
 fprintf(stderr,"READ_COMPLETE mode=%s pages=%lu corrected=%"PRIu64" failed=%"PRIu64" maxbits=%u marker_records=%u\n",argv[1],count,corrected,failed,maxbits,bad);
 close(fd);return failed?5:0;
}
