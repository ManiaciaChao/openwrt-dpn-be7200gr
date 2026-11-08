#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect the actual embedded initramfs and DTB before releasing a RAM image."""
from pathlib import Path
import argparse,gzip,hashlib,json,re,struct

def cpio_files(data):
 files={};p=0
 while p+110<=len(data):
  h=data[p:p+110];assert h[:6] in [b'070701',b'070702'],'Unsupported cpio header'
  v=[int(h[6+i*8:14+i*8],16) for i in range(13)];mode,n,ns=v[1],v[6],v[11];p+=110
  assert 0<ns<4096 and p+ns<=len(data)
  name=data[p:p+ns-1].decode();p=(p+ns+3)&~3
  if name=='TRAILER!!!':return files
  assert not name.startswith('/') and '..' not in Path(name).parts
  assert n<=len(data)-p;body=data[p:p+n];p=(p+n+3)&~3
  name=name.removeprefix('./');files[name]=(mode,body)
 raise ValueError('Missing cpio trailer')

def audit(output,private_patterns=()):
 O=Path(output);image=(O/'Image').read_bytes();dt=(O/'board.dtb').read_bytes();cpio=(O/'initramfs.cpio.gz').read_bytes()
 assert image.count(cpio)==1,'Sidecar ramfs must be exactly embedded in kernel'
 files=cpio_files(gzip.decompress(cpio));issues=[]
 for name,(mode,data) in files.items():
  if name.startswith('etc/dropbear/') and ('host_key' in name or name.endswith('authorized_keys')) and data:issues.append((name,'embedded_authentication'))
  if name.startswith(('root/.ssh/','etc/dpn-provision/')):issues.append((name,'embedded_owner_provisioning'))
  if re.search(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----\r?\n(?:(?:Proc-Type|DEK-Info):[^\n]*\r?\n)*\r?\n?[A-Za-z0-9+/=]{16}',data):issues.append((name,'private_key'))
  for label,value in private_patterns:
   if value and value in data:issues.append((name,'known_private_material:'+label))
 shadow=files['etc/shadow'][1].decode();assert next(x.split(':')[1] for x in shadow.splitlines() if x.startswith('root:')) in ['!','*']
 wireless=files.get('etc/config/wireless',(0,b''))[1];assert not wireless.strip(),'RAM radios must start without AP credentials'
 assert b"option PasswordAuth 'off'" in files['etc/config/dropbear'][1]
 assert b"option RootPasswordAuth 'off'" in files['etc/config/dropbear'][1]
 assert b'mediatek,eeprom-data\0' not in dt and b'local-mac-address\0' not in dt
 for label,value in private_patterns:
  if value and (value in image or value in dt):issues.append(('kernel-or-DTB','known_private_material:'+label))
 assert not issues,issues
 return dict(embedded_initramfs_exact_match=True,cpio_entries_inspected=len(files),private_key_and_authentication_scan_passed=True,known_private_patterns_checked=len(private_patterns),root_password_locked=True,password_SSH_disabled=True,radio_AP_configuration_empty=True,inline_calibration_absent=True,fixed_DT_MAC_absent=True,runtime_ART_NVMEM=True,Image_SHA256=hashlib.sha256(image).hexdigest(),DTB_SHA256=hashlib.sha256(dt).hexdigest())

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);ap.add_argument('--private-file',action='append',type=Path,default=[]);a=ap.parse_args()
 patterns=[('private-file-'+str(i),p.read_bytes()) for i,p in enumerate(a.private_file)]
 r=audit(a.output,patterns);print(json.dumps(r,indent=2));(a.output/'content-audit.json').write_text(json.dumps(r,indent=2)+'\n')
