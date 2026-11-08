#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""ASAN/UBSAN native firmware-boundary and interruption tests. Synthetic NAND."""
import argparse,hashlib,json,os,subprocess,tempfile,struct,zlib
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,default=R/'build/layout4-profiles');a=p.parse_args();profile=a.profile
    fip=(profile/'normal.fip').read_bytes();image=fip+b'\xff'*(0x1000000-len(fip));root=(profile/'rootfs.squashfs').read_bytes()
    recovery=sha(bytes(0x1000000));results=[]
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);raw=p/'mtd0';target=p/'mtd5';inp=p/'image';sq=p/'root';guard=p/'guard'
        with raw.open('wb') as f:f.truncate(0x20000000)
        def put(off,b):
            with raw.open('r+b') as f:f.seek(off);f.write(b)
        put(0x1bfc0000,b'1');sq.write_bytes(root);inp.write_bytes(image)
        env=os.environ|{'DPN_TEST_NAND_DIR':str(p),'DPN_TEST_BOOT_ID':'00000000-0000-0000-0000-000000000001'}
        def reset():
            guard.unlink(missing_ok=True)
            with target.open('wb') as f:f.truncate(0x1000000)
            inp.write_bytes(image);sq.write_bytes(root);put(0,b'\0');put(0x1bfc0000,b'1')
        def run(mode,ok=True,extra=None,pin=None):
            q=subprocess.run([str(R/'build/storage-layout/normal16-host'),mode,str(inp),str(sq),pin or sha(image),recovery,str(guard)],env=env|(extra or {}),capture_output=True)
            assert (q.returncode==0)==ok,(q.stdout,q.stderr)
            assert b'AddressSanitizer' not in q.stderr and b'runtime error:' not in q.stderr,q.stderr
            return q
        reset();run('--snapshot');run('--write');assert target.read_bytes()==image;results.append('complete-16MiB-header-last-readback-and-496MiB-protection')
        for case in ['changed-image','changed-root','changed-boot','changed-target','changed-protected','wrong-selector','corrupt-fit','non-FF-tail','recovery-role-in-main','wrong-certificate-offset','component-hash-mismatch']:
            reset();run('--snapshot');extra=None;pin=None
            if case=='changed-image':inp.write_bytes(b'!'+image[1:])
            if case=='changed-root':sq.write_bytes(root[:-1]+b'!')
            if case=='changed-boot':extra={'DPN_TEST_BOOT_ID':'00000000-0000-0000-0000-000000000002'}
            if case=='changed-target':
                with target.open('r+b') as f:f.write(b'!')
            if case=='changed-protected':put(0,b'!')
            if case=='wrong-selector':put(0x1bfc0000,b'0')
            if case=='corrupt-fit':
                bad=bytearray(image);bad[0x2200]^=1;inp.write_bytes(bad);pin=sha(bad)
            if case=='non-FF-tail':bad=image[:-1]+b'!';inp.write_bytes(bad);pin=sha(bad)
            if case=='recovery-role-in-main':
                b=(profile/'recovery.fip').read_bytes();b+=b'\xff'*(0x1000000-len(b));inp.write_bytes(b);pin=sha(b)
            if case=='wrong-certificate-offset':
                bad=bytearray(image);bad[32]^=1;inp.write_bytes(bad);pin=sha(bad)
            if case=='component-hash-mismatch':
                bad=bytearray(image);fit=memoryview(bad)[0x2100:len(fip)]
                at=struct.unpack_from('>I',fit,8)[0];strings=struct.unpack_from('>I',fit,12)[0];stack=[]
                while True:
                    token=struct.unpack_from('>I',fit,at)[0];at+=4
                    if token==1:
                        end=bytes(fit).index(b'\0',at);stack.append(bytes(fit[at:end]).decode());at=(end+4)&~3
                    elif token==2:stack.pop()
                    elif token==3:
                        n,nameoff=struct.unpack_from('>II',fit,at);at+=8
                        end=bytes(fit).index(b'\0',strings+nameoff);name=bytes(fit[strings+nameoff:end]).decode()
                        if stack==['','images','kernel@1'] and name=='data':fit[at]^=1;break
                        at=(at+n+3)&~3
                    elif token==4:pass
                    else:raise AssertionError('kernel data not found')
                del fit
                struct.pack_into('<I',bad,0x200c,zlib.crc32(bad[0x2100:len(fip)])^0xffffffff);inp.write_bytes(bad);pin=sha(bad)
            before=sha(target.read_bytes());q=run('--write',False,extra,pin);assert b'mutations=0' in q.stderr and sha(target.read_bytes())==before
            results.append(case+'-rejected-before-mutation')
        for phase,page in [('body',0x40000),('header',0)]:
            reset();run('--snapshot');run('--write',False,{'DPN_TEST_FAIL_PHASE':phase,'DPN_TEST_FAIL_PAGE':str(page)})
            assert target.read_bytes()[:0x40000]==b'\xff'*0x40000
            with raw.open('rb') as f:f.seek(0x1bfc0000);assert f.read(1)==b'1'
            results.append(phase+'-failure-retains-invalid-main-header-and-selected-recovery')
    print(json.dumps({'synthetic_only':True,'native_ASAN_UBSAN':True,'passed':results},indent=2))
if __name__=='__main__':main()
