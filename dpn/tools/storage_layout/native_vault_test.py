#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""ASAN native vault tests with synthetic keys on host tmpfs only."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from test_vault import art
from vault import build,VENDOR_BYTES,HEADER

def main():
    r=Path(__file__).resolve().parents[2];exe=r/'build/storage-layout/vault-check-host'
    results=[]
    with tempfile.TemporaryDirectory(prefix='dpn-native-vault-',dir='/dev/shm') as name:
        p=Path(name);a=art();(p/'ART').write_bytes(a)
        b=build(a,b'S'*32,bytes(VENDOR_BYTES),b'ssh-ed25519 Tk9UX0FfUkVBTF9LRVk= synthetic-only\n',b'NOT_A_REAL_PRIVATE_HOST_KEY')
        image=p/'vault';image.write_bytes(b)
        def call(args,ok=True):
            q=subprocess.run([str(exe),*map(str,args)],capture_output=True)
            assert (q.returncode==0)==ok,q.stderr
            assert b'AddressSanitizer' not in q.stderr and b'runtime error:' not in q.stderr
            return q
        call(['--check',image,p/'ART']);results.append('valid-synthetic-vault')
        d=p/'identity';d.mkdir(mode=0o700);call(['--extract-identity',image,p/'ART',d])
        assert (d/'dropbear_ed25519_host_key').read_bytes()==b'NOT_A_REAL_PRIVATE_HOST_KEY'
        assert (d/'authorized_keys').stat().st_mode&0o777==0o600
        call(['--extract-identity',image,p/'ART',d],False);results.append('RAM-extraction-and-no-overwrite')
        a[-1]=1;a[0x301065]=ord('2');(p/'ART-wrong').write_bytes(a)
        call(['--check',image,p/'ART-wrong'],False);results.append('wrong-device-rejected')
        for kind in ['header','payload','bounds','tail']:
            bad=bytearray(b)
            if kind=='header':bad[112]^=1
            elif kind=='payload':bad[HEADER+10]^=1
            elif kind=='tail':bad[-1]=0
            else:
                struct.pack_into('<I',bad,160,HEADER-1)
                bad[HEADER-32:HEADER]=hashlib.sha256(bad[:HEADER-32]).digest()
            image.write_bytes(bad);call(['--check',image,p/'ART'],False);results.append(kind+'-corruption-rejected')
    print(json.dumps({'synthetic_only':True,'ASAN_UBSAN_passed':True,'passed':results},indent=2))

if __name__=='__main__':main()
