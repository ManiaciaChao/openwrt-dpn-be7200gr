#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic native sanitizer/fault tests; no device or private inputs."""
import hashlib,json,os,struct,subprocess,sys,tempfile,zlib
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tools/stock_return'));from test_inspect_image import tree
sys.path.insert(0,str(R/'tools/generic-ram'));from public_fip import build
def main():
    dt=tree(('',{'compatible':b'dlink,dpn-be7200gr-layout4\0dlink,dpn-be7200gr-persist\0'},[('dpn-layout4',{'format-version':struct.pack('>I',4),'write-profile':b'recovery\0'},[])]))
    fit=tree(('',{},[('images',{},[('fdt@1',{'data':dt},[])])]))
    fip=build(fit);eeprom=b'\x92\x79'+bytes(0x1dfe);mac=bytes.fromhex('001122334455')
    v=bytearray(b'\xff'*0x400000);v[:16]=b'DPNVLT1\0'+struct.pack('<II',1,len(v));v[16:48]=hashlib.sha256(b'DPN-BE7200GR-factory-v1\0'+eeprom+mac).digest();v[4064:4096]=hashlib.sha256(v[:4064]).digest()
    candidate=fip+b'\xff'*(0x1000000-len(fip))+v;sha=hashlib.sha256(candidate).hexdigest()
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);raw=p/'raw';target=p/'target';input=p/'input';guard=p/'guard'
        with raw.open('wb') as f:f.truncate(0x20000000)
        with raw.open('r+b') as f:f.seek(0x1bcc0000);f.write(eeprom);f.seek(0x1bf81055);f.write(b'00:11:22:33:44:55')
        input.write_bytes(candidate)
        env=os.environ|{'DPN_PROVISION_TEST_BOOT':'00000000-0000-0000-0000-000000000001'}
        def reset():target.write_bytes(bytes(0x1400000));guard.unlink(missing_ok=True)
        def run(mode,ok=True,extra=None,h=sha):
            q=subprocess.run([str(R/'build/storage-layout/provision-recovery-host'),mode,str(target),str(input),h,str(guard),str(raw)],env=env|(extra or {}),capture_output=True)
            assert (q.returncode==0)==ok,(q.stdout,q.stderr)
            assert b'AddressSanitizer' not in q.stderr and b'runtime error:' not in q.stderr,q.stderr
            return q
        reset();run('--snapshot');run('--write');assert target.read_bytes()==candidate;results.append('header-last-complete-success')
        reset();bad=bytearray(candidate.replace(b'dlink,dpn-be7200gr-persist\0',b'dlink,dpn-be7200gr-perxist\0'));n=struct.unpack_from('<I',bad,0x2008)[0]-256
        struct.pack_into('<I',bad,0x200c,zlib.crc32(bad[0x2100:0x2100+n])^0xffffffff);input.write_bytes(bad)
        q=run('--snapshot',False,h=hashlib.sha256(bad).hexdigest());assert b'persistent-write compatibility' in q.stderr and b'mutations=0' in q.stderr
        assert target.read_bytes()==bytes(0x1400000);input.write_bytes(candidate);results.append('missing-outer-persistent-gate-rejected-before-mutation')
        for name in ['wrong-boot','wrong-SHA','changed-target','changed-protected','wrong-device']:
            reset();run('--snapshot')
            extra=None;h=sha
            if name=='wrong-boot':extra={'DPN_PROVISION_TEST_BOOT':'00000000-0000-0000-0000-000000000002'}
            if name=='wrong-SHA':h='0'*64
            if name=='changed-target':
                with target.open('r+b') as f:f.write(b'!')
            if name in ['changed-protected','wrong-device']:
                with raw.open('r+b') as f:f.seek(0 if name=='changed-protected' else 0x1bcc0000);f.write(b'!')
            before=target.read_bytes();q=run('--write',False,extra,h);assert b'mutations=0' in q.stderr and target.read_bytes()==before
            if name in ['changed-protected','wrong-device']:
                with raw.open('r+b') as f:f.seek(0 if name=='changed-protected' else 0x1bcc0000);f.write(b'\0' if name=='changed-protected' else b'\x92')
            results.append(name+'-rejects-before-mutation')
        for off in [0x40000,0x1000000,0]:
            reset();run('--snapshot');run('--write',False,{'DPN_PROVISION_FAIL_PAGE':str(off)})
            assert target.read_bytes()[:0x40000]==b'\xff'*0x40000;results.append('failure-page-'+str(off)+'-keeps-header-invalid')
    print(json.dumps({'synthetic_only':True,'native_sanitizers':True,'passed':results},indent=2))
if __name__=='__main__':main()
