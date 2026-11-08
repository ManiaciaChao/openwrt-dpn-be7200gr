#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Expanded return sanitizer/fault tests on synthetic ECC-main-data files."""
import hashlib,json,os,struct,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools/stock_return'));from test_inspect_image import fixture
SLOT=0x3200000;VENDOR=0x5380000;ART=0x1bc80000;FLAG=0x1bfc0000
def sha(b):return hashlib.sha256(b).digest()
def main():
    stock=bytes(fixture());stock+=bytes(SLOT-len(stock));vendor=bytes(range(256))*16+b'\xff'*(VENDOR-4096)
    ep=b'\x92\x79'+bytes(0x1dfe);mac=bytes.fromhex('001122334455');header=bytearray(b'\xff'*4096);header[:16]=b'DPNVLT1\0'+struct.pack('<II',1,0x400000);header[16:48]=sha(b'DPN-BE7200GR-factory-v1\0'+ep+mac);header[48:80]=sha(stock);header[80:112]=sha(vendor);struct.pack_into('<I',header,144,VENDOR);header[4064:]=sha(header[:4064])
    rec=hashlib.sha256(bytes(0x1000000)).hexdigest();results=[]
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);raw=p/'mtd0';t0=p/'mtd5';t1=p/'mtd6';s=p/'stock';v=p/'vendor';guard=p/'guard'
        with raw.open('wb') as f:f.truncate(0x20000000)
        def put(off,data):
            with raw.open('r+b') as f:f.seek(off);f.write(data)
        put(ART+0x40000,ep);put(ART+0x301055,b'00:11:22:33:44:55');put(FLAG,b'1');put(0x4280000,header);s.write_bytes(stock);v.write_bytes(vendor)
        env=os.environ|{'DPN_TEST_NAND_DIR':str(p),'DPN_TEST_BOOT_ID':'00000000-0000-0000-0000-000000000001'}
        def reset():
            for f,n in [(t0,SLOT),(t1,VENDOR)]:
                with f.open('wb') as q:q.truncate(n)
            guard.unlink(missing_ok=True)
        def run(mode,ok=True,extra=None,r=rec):
            q=subprocess.run([str(R/'build/storage-layout/expanded-return-host'),mode,str(s),str(v),r,str(guard)],env=env|(extra or {}),capture_output=True)
            assert (q.returncode==0)==ok,(q.stdout,q.stderr)
            assert b'AddressSanitizer' not in q.stderr and b'runtime error:' not in q.stderr,q.stderr
            return q
        reset();run('--snapshot');run('--write');assert t0.read_bytes()==stock and t1.read_bytes()==vendor;results.append('stock50-and-vendor83.5-complete-header-last-success')
        for name in ['wrong-stock','wrong-vendor','wrong-recovery','wrong-boot','changed-target','changed-protected','wrong-factory','selector-not-recovery','corrupt-vault']:
            reset();run('--snapshot');extra=None;r=rec
            if name=='wrong-stock':s.write_bytes(b'!'+stock[1:])
            if name=='wrong-vendor':v.write_bytes(b'!'+vendor[1:])
            if name=='wrong-recovery':r='0'*64
            if name=='wrong-boot':extra={'DPN_TEST_BOOT_ID':'00000000-0000-0000-0000-000000000002'}
            if name=='changed-target':
                with t0.open('r+b') as f:f.write(b'!')
            if name=='changed-protected':put(0,b'!')
            if name=='wrong-factory':put(ART+0x40000,b'!')
            if name=='selector-not-recovery':put(FLAG,b'0')
            if name=='corrupt-vault':put(0x4280000+4064,b'!')
            before0=t0.read_bytes();before1=t1.read_bytes();q=run('--write',False,extra,r);assert b'mutations=0' in q.stderr and t0.read_bytes()==before0 and t1.read_bytes()==before1
            s.write_bytes(stock);v.write_bytes(vendor);put(0,b'\0');put(ART+0x40000,ep);put(FLAG,b'1');put(0x4280000,header);results.append(name+'-rejects-before-mutation')
        for phase,offset in [('vendor',0),('stock-body',0x40000),('stock-header',0)]:
            reset();run('--snapshot');run('--write',False,{'DPN_TEST_FAIL_PHASE':phase,'DPN_TEST_FAIL_PAGE':str(offset)});assert t0.read_bytes()[:0x40000]==b'\xff'*0x40000
            with raw.open('rb') as f:f.seek(FLAG);assert f.read(1)==b'1'
            results.append('injected-'+phase+'-failure-keeps-main-header-invalid-and-recovery-selected')
    print(json.dumps({'synthetic_only':True,'native_sanitizers':True,'passed':results},indent=2))
if __name__=='__main__':main()
