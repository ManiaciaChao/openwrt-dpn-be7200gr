#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build every native helper and fetch hash-pinned public NPU firmware inputs.
Run inside an isolated clean source tree after its OpenWrt base build succeeds.
"""
import base64,hashlib,json,shutil,subprocess,tarfile,time,urllib.request
import urllib.error
from pathlib import Path
R=Path(__file__).resolve().parents[2]
status=json.loads((R/'CLEAN-BASE-STATUS.json').read_text())
assert status['base_build_passed'], 'Clean base build must complete first'
B=R/'build';O=B/'generic-ram/output';O.mkdir(parents=True,exist_ok=True)
firmware_lock=json.loads((R/'artifacts/offload/firmware-source.json').read_text())
def fetch(spec,dest):
    if not dest.exists():
        dest.parent.mkdir(parents=True,exist_ok=True)
        candidates=[(spec['url'],False)]
        if 'path' in spec:
            candidates.append(('https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/'+firmware_lock['commit']+'/'+spec['path']+'?format=TEXT',True))
        last_error=None
        for url,encoded in candidates:
            try:
                with urllib.request.urlopen(url,timeout=60) as remote:
                    data=remote.read(32*1024*1024+1)
                assert len(data)<=32*1024*1024, 'Public source input oversized'
                if encoded:data=base64.b64decode(data,validate=True)
                assert hashlib.sha256(data).hexdigest()==spec['sha256'], 'Public source hash mismatch'
                dest.write_bytes(data)
                break
            except (urllib.error.URLError,TimeoutError) as error:
                last_error=error
        else:raise RuntimeError('All public source mirrors failed: '+spec['url']) from last_error
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==spec['sha256']
lock=json.loads((R/'configs/release-helper-sources.json').read_text())['kexec_tools']
archive=B/'public-sources'/('kexec-tools-'+lock['version']+'.tar.xz');fetch(lock,archive)
kexec=B/'generic-kexec';kexec.mkdir(exist_ok=True)
previous=kexec/('kexec-tools-'+lock['version'])
if previous.exists():
    assert not previous.is_symlink(), 'Refuse linked helper build directory'
    previous.rename(kexec/(previous.name+'.previous-'+str(time.time_ns())))
with tarfile.open(archive) as source:source.extractall(kexec,filter='data')
def run(args):subprocess.run(list(map(str,args)),cwd=R,check=True)
run([R/'tools/with_openwrt_env.sh','bash',R/'tools/generic-ram/build-kexec.sh'])
shutil.copyfile(kexec/('kexec-tools-'+lock['version'])/'COPYING',O/'COPYING.kexec-tools')
cc=R/'openwrt/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc'
for source,name in [('tools/generic-ram/mk_session_initrd.c','mk-session-initrd'),('tools/generic-ram/ram_launch.c','ram-launch'),('tools/nand_readonly_dump.c','nand-reader')]:
    run([R/'tools/with_openwrt_env.sh',cc,'-Os','-static','-Wall','-Wextra',R/source,'-o',O/name])
run(['bash',R/'tools/first-install/build-writer.sh'])
for name in ['vault-check', 'vault-build', 'image4-check', 'normal16', 'bootflag', 'provisioner', 'expanded-return', 'factory-read']:
    run(['bash', R/'tools/storage_layout'/('build-'+name+'.sh')])
firmware=json.loads((R/'artifacts/offload/firmware-source.json').read_text())
for spec in firmware['files']:
    if spec['path'].startswith('airoha/en7581_') or spec['path']=='LICENSES/LICENSE.airoha':
        fetch(spec,B/'public-firmware'/Path(spec['path']).name)
(O/'helper-source-manifest.json').write_text(json.dumps({'kexec':lock,'firmware':firmware,'writer_digest_library':'libmd','public_inputs_only':True},indent=2)+'\n')
print('CLEAN_NATIVE_HELPERS_BUILT_AND_FIRMWARE_INPUTS_VERIFIED; no device operation')
