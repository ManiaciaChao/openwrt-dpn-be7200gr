#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check actual audited package formats, refusal gates and checksum manifests."""
from pathlib import Path
import argparse,tempfile,subprocess,sys,json,hashlib,struct
p=argparse.ArgumentParser();p.add_argument('artifacts',type=Path);p.add_argument('--self-test-artifacts',type=Path,required=True);a=p.parse_args();R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'));from ummtk import unpack
root=a.artifacts.resolve();helper=Path(__file__).with_name('package_formats.py')
with tempfile.TemporaryDirectory(prefix='dpn-package-tests-') as td:
 t=Path(td);out=t/'public'
 def run(src,dst,extra=()):return subprocess.run([sys.executable,str(helper),'--artifacts',str(src),'--output',str(dst),'--format','both',*extra],capture_output=True)
 r=run(root,out);assert r.returncode==0,r.stderr.decode();meta=json.loads((out/'package-manifest.json').read_text());assert not meta['target_local_factory_header_required'] and meta['factory_independent_public_Web_header']
 assert (out/'dpn-be7200gr-sysupgrade.bin').read_bytes()==(root/'generic-sysupgrade.bin').read_bytes()
 fip=unpack((out/'dpn-be7200gr-factory-web.bin').read_bytes());assert fip[0x2100:]==(root/'generic-persistent.itb').read_bytes()
 for i in range(3):
  uuid,off,size,flags=struct.unpack_from('<16sQQQ',fip,16+i*40);assert size==2 and flags==0 and fip[off:off+size]==b'\x30\x00'
 for name,v in meta['files'].items():assert (out/name).stat().st_size==v['bytes'] and hashlib.sha256((out/name).read_bytes()).hexdigest()==v['sha256']
 assert run(root,out).returncode!=0
 assert run(a.self_test_artifacts,t/'forbidden-selftest').returncode!=0
 minimal=t/'missing-capability';minimal.mkdir()
 for name in ['persistent-manifest.json','persistent-content-audit.json','rootfs.squashfs','Image','board.dtb','generic-persistent.itb','generic-sysupgrade.bin']:(minimal/name).symlink_to(root/name)
 m=json.loads((root/'manifest.json').read_text());m['capabilities']['slot_aware_update']=0;(minimal/'manifest.json').write_text(json.dumps(m));assert run(minimal,t/'forbidden-capability').returncode!=0
 # The optional target-local wrapper remains explicitly private and distinct.
 target=t/'target-wrapper.fip';target.write_bytes(fip);r=run(root,t/'private',['--target-fip',str(target)]);assert r.returncode==0,r.stderr.decode();assert (t/'private').stat().st_mode&0o777==0o700
 assert json.loads((t/'private/package-manifest.json').read_text())['target_local_factory_header_required'];assert (t/'private/dpn-be7200gr-target-local-factory-web.bin').exists()
print('PUBLIC_BOTH_FORMATS_CHECKSUMS_EMPTY_CERTIFICATES_PRIVATE_OPTION_SELFTEST_CAPABILITY_AND_OVERWRITE_GATES_PASS; no upload')
