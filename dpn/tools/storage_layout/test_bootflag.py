#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Native selector tests with synthetic files; no device inputs."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def main():
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        raw=Path(tmp)/'raw';art=bytearray(b'\xff'*0x380000);art[:4096]=bytes(range(256))*16;art[0x340000]=ord('0');sha=hashlib.sha256(art).hexdigest()
        with raw.open('wb') as f:f.truncate(0x20000000)
        def put(b):
            with raw.open('r+b') as f:f.seek(0x1bc80000);f.write(b)
        def get():
            with raw.open('rb') as f:f.seek(0x1bc80000);return f.read(len(art))
        def run(value,ok=True,h=sha):
            q=subprocess.run([str(R/'build/storage-layout/bootflag-host'),value,str(raw),str(raw),h],capture_output=True)
            assert (q.returncode==0)==ok,(q.stdout,q.stderr)
            assert b'AddressSanitizer' not in q.stderr and b'runtime error:' not in q.stderr,q.stderr
            if not ok:assert b'mutations=0' in q.stderr
            return q
        put(art);run('1');expected=art.copy();expected[0x340000]=ord('1');assert get()==expected;run('0');assert get()==art;results.append('both-selector-directions-only-one-ART-byte-changes')
        assert b'NO_ERASE' in run('0').stdout;results.append('same-selector-does-not-erase')
        for name,mut in [('extra-data-in-selector-block',0x340001),('changed-calibration',0x40000),('invalid-selector',0x340000)]:
            bad=art.copy();bad[mut]=ord('!');put(bad);run('1',False);assert get()==bad;results.append(name+'-rejects-before-mutation')
        put(art);run('1',False,h='0'*64);assert get()==art;run('2',False);results.append('wrong-SHA-and-invalid-request-rejected')
        erased=art.copy();erased[0x340000]=255;put(erased);run('0');assert get()==art;results.append('explicit-repair-of-erased-selector-with-pinned-ART')
    print(json.dumps({'synthetic_only':True,'native_sanitizers':True,'passed':results},indent=2))
if __name__=='__main__':main()
