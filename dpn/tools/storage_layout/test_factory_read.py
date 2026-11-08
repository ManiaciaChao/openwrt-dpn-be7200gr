#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic ECC-file tests for installer extraction; never opens hardware."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R/'tools/stock_return'))
from test_inspect_image import tree
sys.path.insert(0, str(R/'tools/generic-ram'))
from public_fip import build

def main():
    filesystem = b'hsqs' + bytes(92) + b'SYNTHETIC-INSTALLER'
    fit = tree(('', {}, [('images', {}, [('filesystem@1', {'data': filesystem}, [
        ('hash@1', {'algo': b'sha1\0', 'value': hashlib.sha1(filesystem).digest()}, [])
    ])])]))
    image = build(fit)
    expected = hashlib.sha256(filesystem).hexdigest()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        raw, out = p/'raw', p/'output'
        with raw.open('wb') as f:
            f.truncate(0x20000000)
        def place(blob):
            with raw.open('r+b') as f:
                for base in (0x80000, 0x3280000):
                    f.seek(base)
                    f.write(blob)
        def run(slot='0', digest=expected, ok=True):
            q = subprocess.run([str(R/'build/storage-layout/factory-read-host'), str(raw), slot, digest, str(out)], capture_output=True)
            assert (q.returncode == 0) == ok, q.stderr
            assert b'AddressSanitizer' not in q.stderr and b'runtime error:' not in q.stderr, q.stderr
            return q
        place(image)
        for slot in ('0', '1'):
            run(slot)
            assert out.read_bytes() == filesystem
            run(slot, ok=False)
            out.unlink()
            results.append('slot-'+slot+'-verified-extraction-and-no-overwrite')
        run('2', ok=False)
        run(digest='0'*64, ok=False)
        assert not out.exists()
        results.append('invalid-slot-or-filesystem-hash-no-output')
        for kind in ('CRC', 'bounds', 'FIT-hash'):
            b = bytearray(image)
            if kind == 'CRC':
                b[-1] ^= 1
            elif kind == 'bounds':
                struct.pack_into('<I', b, 0x2008, 0x3200000)
            else:
                at = b.index(hashlib.sha1(filesystem).digest())
                b[at] ^= 1
                struct.pack_into('<I', b, 0x200c, zlib.crc32(b[0x2100:]) ^ 0xffffffff)
            place(b)
            run(ok=False)
            assert not out.exists()
            results.append(kind+'-rejected-before-output')
        place(image[:-50])
        # Recreate a genuinely truncated file rather than leaving old tail bytes.
        with raw.open('r+b') as f:
            f.truncate(0x80000+len(image)-50)
        run(ok=False)
        results.append('truncated-ECC-read-rejected')
    print(json.dumps({'synthetic_only': True, 'ASAN_UBSAN_passed': True, 'passed': results}, indent=2))

if __name__ == '__main__':
    main()
