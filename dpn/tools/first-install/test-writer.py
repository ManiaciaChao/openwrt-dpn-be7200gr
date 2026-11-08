#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic files only: native installer validation and interrupted programming."""
from pathlib import Path
import shutil,fcntl,hashlib,json,os,struct,subprocess,tempfile,zlib
R=Path(__file__).resolve().parents[2]
exe=R/'build/generic-ram/writer-host-test'
dtc=Path(shutil.which('dtc') or '/missing-required-dtc').parent
mk=R/'openwrt/staging_dir/host/bin/mkimage'
active_slot=int(os.environ.get("DPN_TEST_SLOT","0"));assert active_slot in [0,1]
firmware_start=[0x80000,0x3280000][active_slot];factory_start=[0x3280000,0x80000][active_slot]
results=[]
with tempfile.TemporaryDirectory(prefix='dpn-generic-writer-') as temp:
 d=Path(temp);source=d/'mtd0'
 with source.open('wb') as f:f.truncate(0x20000000)
 header=os.urandom(0x2100)
 with source.open('r+b') as f:
  f.seek(factory_start);f.write(header);f.seek(0x1bfc0000);f.write(str(active_slot).encode())
 def run(args,ok=True,env=None):
  p=subprocess.run([str(exe),*map(str,args),str(d)],capture_output=True,env=env)
  assert (p.returncode==0)==ok,(args,p.stdout.decode(),p.stderr.decode())
  assert b'AddressSanitizer' not in p.stderr and b'runtime error:' not in p.stderr
  return p
 run(['--snapshot',d/'guard'])
 fs=b'hsqs'+b'SYNTHETIC_NOT_BOOTABLE_TEST_FIXTURE'*128
 (d/'fs').write_bytes(fs);(d/'kernel').write_bytes(b'SYNTHETIC_NOT_BOOTABLE_KERNEL')
 sha=' '.join(f'{x:02x}' for x in hashlib.sha256(fs).digest())
 (d/'board.dts').write_text('''/dts-v1/;
 /memreserve/ 0x98000000 0x08000000;
 / { compatible="dlink,dpn-be7200gr", "dlink,dpn-be7200gr-install", "dlink,dpn-be7200gr-persist", "dlink,dpn-be7200gr-upgrade", "dlink,dpn-be7200gr-expand";
 dpn-art { compatible="dlink,dpn-be7200gr-art"; };
 dpn-flash-layout { persistent-root; slot-relative-root; format-version=<1>; upgrade-layout=<3>; config-bank=<2>; config-start=<0xb800000>; config-size=<0x10000000>; rootfs-offset=<0x100000>; rootfs-size=<SIZE>; rootfs-sha256=[HASH]; }; };
 '''.replace('SIZE',str(len(fs))).replace('HASH',sha))
 subprocess.run([str(dtc/'dtc'),'-I','dts','-O','dtb','-o',str(d/'board.dtb'),str(d/'board.dts')],check=True)
 (d/'fixture.its').write_text('''/dts-v1/; / { description="Synthetic test only"; #address-cells=<1>;
 images {
 fdt@1 { data=/incbin/("board.dtb"); type="flat_dt"; arch="arm64"; compression="none"; load=<0x8d000000>; hash@1 { algo="sha1"; }; };
 kernel@1 { data=/incbin/("kernel"); type="kernel"; arch="arm64"; os="linux"; compression="lzma"; load=<0x8b000000>; entry=<0x8b000000>; hash@1 { algo="sha1"; }; };
 filesystem@1 { data=/incbin/("fs"); type="filesystem"; os="linux"; arch="arm64"; compression="none"; hash@1 { algo="sha1"; }; };
 }; configurations { default="conf@1"; conf@1 { kernel="kernel@1"; fdt="fdt@1"; }; }; };''')
 def pack():
  subprocess.run([str(mk),'-f','fixture.its','fixture.itb'],cwd=d,env=os.environ|{'PATH':str(dtc)+':'+os.environ['PATH']},check=True,stdout=subprocess.DEVNULL)
 pack();off=(d/'fixture.itb').read_bytes().index(fs)
 subprocess.run([str(dtc/'fdtput'),'-t','x',str(d/'board.dtb'),'/dpn-flash-layout','rootfs-offset',format(0x80000+0x2100+off,'x')],check=True)
 pack();assert (d/'fixture.itb').read_bytes().index(fs)==off
 run(['--check-fit',d/'fixture.itb'])
 run(['--assemble-fit',d/'fixture.itb',d/'guard',d/'image'])
 data=(d/'image').read_bytes();prefix=0x1200000;old=bytes(prefix);outside=os.urandom(4096)
 body=(prefix-262144)//4096
 cases=[('check',False,None,None),('success',True,None,None),('body_first_fail',True,0,None),('body_last_fail',True,body-1,None),('header_first_fail',True,body,None),('bad_header',True,None,'header'),('bad_fit_sha',True,None,'fit'),('wrong_guard',True,None,'guard'),('changed_protected',True,None,'protected'),('changed_prior_firmware',True,None,'prior')]
 for name,write,fault,bad in cases:
  (d/'mtd2').write_bytes(old+outside);image=bytearray(data);guard=bytearray((d/'guard').read_bytes())
  if bad=='header':image[32]^=1
  if bad=='fit':image[0x2100+off+20]^=1;struct.pack_into('<I',image,0x200c,zlib.crc32(image[0x2100:])^0xffffffff)
  if bad=='guard':guard[12]=ord('1') if guard[12]!=ord('1') else ord('2')
  if bad in ('protected','prior'):
   with source.open('r+b') as f:f.seek(0 if bad=='protected' else firmware_start);f.write(b'!')
  (d/'candidate').write_bytes(image);(d/'current-guard').write_bytes(guard)
  env=os.environ.copy()
  if fault is not None:env['DPN_TEST_FAIL_WRITE_AT']=str(fault)
  p=run(['--write' if write else '--check-image',d/'candidate',d/'current-guard'],ok=name in ('check','success'),env=env)
  target=(d/'mtd2').read_bytes();assert target[prefix:]==outside
  if name=='success':assert target[:prefix]==data+b'\xff'*(prefix-len(data))
  elif fault is not None:assert target[:262144]==b'\xff'*262144
  else:assert target[:prefix]==old and (not write or b'mutations=0' in p.stderr)
  if bad in ('protected','prior'):
   with source.open('r+b') as f:f.seek(0 if bad=='protected' else firmware_start);f.write(b'\0')
  results.append(dict(case=name,expected_result=True,outside_write_view_unchanged=True))
 # An otherwise valid guard for the other runtime slot may never program.
 env=os.environ.copy();env['DPN_TEST_SLOT']=str(1-active_slot)
 before=(d/'mtd2').read_bytes()
 q=run(['--write',d/'image',d/'guard'],ok=False,env=env)
 assert b'mutations=0' in q.stderr and (d/'mtd2').read_bytes()==before
 results.append(dict(case='other_running_slot_guard_rejected',expected_result=True,outside_write_view_unchanged=True))
 # An explicit rollback accepts only this target's exact pre-install prefix.
 (d/'previous').write_bytes(old)
 run(['--check-restore',d/'previous',d/'guard'])
 (d/'mtd2').write_bytes(data+b'\xff'*(prefix-len(data))+outside)
 run(['--restore-prefix',d/'previous',d/'guard'])
 assert (d/'mtd2').read_bytes()==old+outside
 run(['--verify-restored',d/'previous',d/'guard'])
 results.append(dict(case='explicit_previous_prefix_restore',expected_result=True,outside_write_view_unchanged=True))
 wrong=bytearray(old);wrong[100]=1;(d/'wrong-previous').write_bytes(wrong)
 q=run(['--restore-prefix',d/'wrong-previous',d/'guard'],ok=False)
 assert b'mutations=0' in q.stderr and (d/'mtd2').read_bytes()==old+outside
 results.append(dict(case='wrong_previous_prefix_rejected',expected_result=True,outside_write_view_unchanged=True))
 with (d/'firmware.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  q=run(['--write',d/'image',d/'guard'],ok=False)
  assert b'mutations=0' in q.stderr and (d/'mtd2').read_bytes()==old+outside
 results.append(dict(case='concurrent_programmer_rejected',expected_result=True,outside_write_view_unchanged=True))
 run(['--check-config-blank'],ok=False)
 with source.open('r+b') as f:
  f.seek(0xb800000);block=b'\xff'*(1024*1024)
  for _ in range(256):f.write(block)
 run(['--check-config-blank'])
 with source.open('r+b') as f:f.seek(0x1b800000-1);f.write(b'!')
 run(['--check-config-blank'],ok=False)
 results.append(dict(case='fresh_bank_entire_range_checked',expected_result=True,outside_write_view_unchanged=True))
 out=R/'artifacts/generic-ram'/('writer-host-tests-slot'+str(active_slot)+'.json');out.parent.mkdir(exist_ok=True)
 out.write_text(json.dumps(dict(active_update_slot=active_slot,guard_format=4,synthetic_fixture=True,ASAN_UBSAN=True,tests=results),indent=2)+'\n')
 print('slot='+str(active_slot)+' '+str(len(results))+' generic native installer/guard/rollback/fault cases passed; synthetic files only')
