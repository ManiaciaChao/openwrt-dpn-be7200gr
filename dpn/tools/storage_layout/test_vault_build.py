#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Native auto-installer vaults versus the independent Python format reader.

All NAND inputs are sparse synthetic files, never a router or private dump.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from vault import fingerprint, parse, critical_state

R = Path(__file__).resolve().parents[2]
binary = R/'build/storage-layout/vault-build-host'
env = os.environ | {'ASAN_OPTIONS': 'detect_leaks=0'}
with tempfile.TemporaryDirectory() as temporary:
    p = Path(temporary)
    raw = p/'nand'
    with raw.open('wb') as f:
        f.truncate(0x20000000)
        for start in (0x80000, 0x3280000):
            f.seek(start); f.write(bytes.fromhex('010064aa'))
        f.seek(0x1bc80000+0x40000); f.write(b'\x92\x79')
        f.seek(0x1bc80000+0x301055); f.write(b'02:12:34:56:78:90')
        f.seek(0x6480000); f.write(b'synthetic-essential-vendor-state')
        f.seek(0xb780000); f.write(b'synthetic-tail')
    authorized = p/'authorized_keys'; authorized.write_bytes(b'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixtureForFormatOnly synthetic\n')
    host = p/'host'; host.write_bytes(b'fixture-not-a-real-private-key')
    art = raw.read_bytes()[0x1bc80000:0x1c000000]
    with raw.open('rb') as f:
        f.seek(0x6480000); vendor = f.read(0x5380000)
    original = hashlib.sha256(raw.read_bytes()).hexdigest()
    def run(slot, target, success=True):
        result = subprocess.run([binary, '--build', raw, str(slot), authorized, host, target],
                                env=env, capture_output=True)
        assert (result.returncode == 0) == success, result.stderr.decode()
        return result
    for slot in (0, 1):
        out = p/('vault-'+str(slot))
        run(slot, out)
        result = parse(out.read_bytes(), fingerprint(art), True)
        assert result['objects']['authorized_keys'] == authorized.read_bytes()
        assert result['objects']['dropbear_ed25519_host_key'] == host.read_bytes()
        assert result['full_external_vendor_state_SHA256'] == hashlib.sha256(vendor).hexdigest()
        assert result['essential_plain_SHA256'] == hashlib.sha256(critical_state(vendor)).hexdigest()
        with raw.open('rb') as f:
            f.seek(0x80000 if slot == 1 else 0x3280000)
            stock = f.read(0x3200000)
        assert result['original_stock_SHA256'] == hashlib.sha256(stock).hexdigest()
        assert out.stat().st_mode & 0o777 == 0o600
        before = out.read_bytes(); run(slot, out, False); assert before == out.read_bytes()
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == original
    run('bad', p/'invalid-slot', False)
    with raw.open('r+b') as f:
        f.seek(0x4280000); f.write(b'DPNV')
    run(1, p/'existing-vault', False); assert not (p/'existing-vault').exists()
    with raw.open('r+b') as f:
        f.seek(0x4280000); f.write(b'\0'*4)
        f.seek(0x1bc80000+0x40000); f.write(b'\0\0')
    run(1, p/'bad-calibration', False); assert not (p/'bad-calibration').exists()
    with raw.open('r+b') as f:
        f.seek(0x1bc80000+0x40000); f.write(b'\x92\x79')
        f.seek(0x6480000); f.write(os.urandom(0x500000))
    run(1, p/'oversized-vault', False); assert not (p/'oversized-vault').exists()
print('Native vault: both boot slots, Python deep format verification, no source mutation, exclusive output, invalid slot/calibration/existing vault/capacity refusals passed')
