#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Audit actual embedded early root, DTBs, and extracted SquashFS contents."""
import argparse,gzip,hashlib,importlib.util,json,re,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--private-file',type=Path,action='append',default=[]);p.add_argument('--allow-recovery-self-test',action='store_true');a=p.parse_args()
R=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('ram_audit',Path(__file__).with_name('audit.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
patterns=[('private-file-'+str(i),f.read_bytes()) for i,f in enumerate(a.private_file)]
result=m.audit(a.output,patterns);issues=[]
manifest=json.loads((a.output/'persistent-manifest.json').read_text())
assert not manifest.get('development_recovery_self_test') or a.allow_recovery_self_test, 'Private recovery self-test image; refuse production audit'
cap=json.loads((a.output/'manifest.json').read_text()).get('capabilities',{})
if cap.get('readonly_network_recovery')==1:
 embedded=m.cpio_files(gzip.decompress((a.output/'initramfs.cpio.gz').read_bytes()))
 assert b'dpn_recovery_bind_firewall' in embedded['lib/upgrade/dpn-recovery-firewall.sh'][1]
 assert b'dpn_recovery_bind_firewall || return 1' in embedded['lib/upgrade/dpn-network-recovery.sh'][1]
 result['recovery_firewall_device_binding_helper_present']=True
 assert embedded['usr/libexec/dpn-install'][1]==(a.output/'dpn-install').read_bytes()
 module=embedded['lib/modules/6.18.60/dpn_storage.ko'][1]
 assert b'config_readonly' in module and b'root_slot' in module
 assert embedded['etc/init.d/dpn_recovery_ssh'][0]&0o111
 assert b'/etc/dpn-network-recovery' in embedded['etc/init.d/dpn_recovery_ssh'][1]
 result['early_recovery_writer_and_readonly_module_present']=True
result['development_recovery_self_test']=bool(manifest.get('development_recovery_self_test'))

for name in ['persistent.dtb','persistent-ram-root.dtb','installer.dtb']:
 data=(a.output/name).read_bytes()
 assert b'mediatek,eeprom-data\0' not in data and b'local-mac-address\0' not in data
 for label,value in patterns:
  if value and value in data:issues.append((name,label))
with tempfile.TemporaryDirectory(prefix='dpn-audit-squashfs-') as td:
 tree=Path(td)/'root'
 subprocess.run([str(R/'openwrt/staging_dir/host/bin/unsquashfs4'),'-no-progress','-d',str(tree),str(a.output/'rootfs.squashfs')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 count=0
 for file in tree.rglob('*'):
  if file.is_symlink() or not file.is_file():continue
  name=str(file.relative_to(tree));data=file.read_bytes();count+=1
  if name.startswith(('root/.ssh/','etc/dpn-provision/')):issues.append((name,'owner_provisioning'))
  if name.startswith('etc/dropbear/') and data and ('host_key' in name or name.endswith('authorized_keys')):issues.append((name,'embedded_authentication'))
  if re.search(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----\r?\n(?:(?:Proc-Type|DEK-Info):[^\n]*\r?\n)*\r?\n?[A-Za-z0-9+/=]{16}',data):issues.append((name,'private_key'))
  for label,value in patterns:
   if value and value in data:issues.append((name,label))
 assert not (tree/'etc/config/wireless').read_bytes().strip()
 assert next(x.split(':')[1] for x in (tree/'etc/shadow').read_text().splitlines() if x.startswith('root:')) in ['!','*']
 assert (tree/'www/cgi-bin/luci').exists() and (tree/'usr/libexec/tar-gnu').exists()
 required_radio=['mt7992_wa.bin','mt7992_wm.bin','mt7992_dsp.bin','mt7992_rom_patch.bin','mt7992_eeprom.bin','mt7992_eeprom_2i5e.bin','mt7992_eeprom_2i5i.bin']
 for name in required_radio:
  file=tree/'lib/firmware/mediatek/mt7996'/name
  assert file.is_file() and file.stat().st_size>0, 'Missing standard wireless firmware: '+name
 result['required_mt7992_firmware_present']=True
assert not issues,issues
result.update(actual_SquashFS_extracted=True,SquashFS_regular_files_inspected=count,LuCI_and_GNU_tar_present=True,production_DT_no_inline_factory_identity=True,SquashFS_SHA256=hashlib.sha256((a.output/'rootfs.squashfs').read_bytes()).hexdigest())
(a.output/'persistent-content-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
