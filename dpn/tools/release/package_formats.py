#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Package audited generic sysupgrade and stock Web formats; never upload.
Public Web uses a factory-independent FIP for the recorded tested boot profile.
An optional target-derived wrapper remains a private, target-local format.
"""
from pathlib import Path
import argparse,hashlib,json,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ummtk import pack,unpack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'generic-ram'))
from public_fip import build as public_fip

def digest(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--format',choices=['sysupgrade','factory-web','both'],default='sysupgrade');p.add_argument('--target-fip',type=Path,help='Optional private target-derived wrapper; omitted for the public factory-independent format')
 a=p.parse_args();root=a.artifacts;manifest=json.loads((root/'persistent-manifest.json').read_text());audit=json.loads((root/'persistent-content-audit.json').read_text())
 if manifest.get('development_recovery_self_test'):p.error('A recovery self-test image must not be packaged for distribution')
 required=['actual_SquashFS_extracted','private_key_and_authentication_scan_passed','runtime_ART_NVMEM','production_DT_no_inline_factory_identity','root_password_locked','radio_AP_configuration_empty']
 if manifest['layout']!=3 or not all(audit.get(k) is True for k in required):p.error('Require audited generic layout 3 inputs')
 def read(name):
  b=(root/name).read_bytes()
  if len(b)!=manifest['files'][name]['bytes'] or digest(b)!=manifest['files'][name]['sha256']:raise ValueError('Artifact manifest mismatch: '+name)
  return b
 if digest(read('rootfs.squashfs'))!=audit['SquashFS_SHA256'] or digest(read('Image'))!=audit['Image_SHA256'] or digest(read('board.dtb'))!=audit['DTB_SHA256']:p.error('Audit does not bind current payloads')
 files={};factory=a.format!='sysupgrade';private=factory and a.target_fip is not None
 if a.format in ['sysupgrade','both']:files['dpn-be7200gr-sysupgrade.bin']=read('generic-sysupgrade.bin')
 if factory:
  if private:
   b=a.target_fip.read_bytes()
   if b[0x2100:]!=read('generic-persistent.itb'):p.error('Target FIP does not contain the checked generic FIT')
   name='dpn-be7200gr-target-local-factory-web.bin'
  else:
   caps=json.loads((root/'manifest.json').read_text()).get('capabilities',{})
   if not all(caps.get(k)==1 for k in ['slot_aware_readonly_root','slot_aware_update','readonly_network_recovery','factory_first_boot']):p.error('Public Web needs slot-aware root/update and first-boot/recovery support')
   b=public_fip(read('generic-persistent.itb'));name='dpn-be7200gr-factory-web.bin'
  files[name]=pack(b);assert unpack(files[name])==b
 a.output.mkdir(mode=0o700 if private else 0o755,parents=True,exist_ok=True)
 if private and (a.output.stat().st_uid!=os.getuid() or a.output.stat().st_mode&0o077):p.error('Factory Web output directory must be owned by you and mode 0700')
 if any((a.output/n).exists() for n in [*files,'package-manifest.json','SHA256SUMS']):p.error('Refuse to replace an existing package set')
 for name,b in files.items():
  with (a.output/name).open('xb') as f:(a.output/name).chmod(0o600 if private else 0o644);f.write(b)
 summary=dict(format=a.format,layout=3,public_release_qualified=False,target_local_factory_header_required=private,factory_independent_public_Web_header=factory and not private,factory_Web_slot_is_selected_by_stock_system_not_package=factory,original_bootloader_retained=factory,factory_Web_retains_running_stock_slot_as_fallback=factory,hardware_validation_reference="artifacts/stock-web-upgrade/public-validation-summary.json",hardware_validation_limited_to_recorded_unit_and_profile=True,tested_boot_profile='DPN-BE7200GR original bootloader; stock Linux 5.4.55; documented zero-bad-block empty-mapping NAND profile' if factory else None,files={n:dict(bytes=len(b),sha256=digest(b)) for n,b in files.items()})
 (a.output/'package-manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
 (a.output/'SHA256SUMS').write_text(''.join(digest(b)+'  '+n+'\n' for n,b in files.items()))
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
