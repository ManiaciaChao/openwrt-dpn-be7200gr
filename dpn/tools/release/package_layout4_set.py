#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Collect only the two layout4 firmware outputs and their provenance files."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--factory', type=Path, required=True)
    p.add_argument('--sysupgrade', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--format', choices=['both', 'factory-web', 'sysupgrade'], default='both')
    a = p.parse_args()
    selected = []
    if a.format != 'sysupgrade': selected.append((a.factory, 'dpn-be7200gr-factory-web.bin'))
    if a.format != 'factory-web': selected.append((a.sysupgrade, 'dpn-be7200gr-sysupgrade.bin'))
    receipts = {}; blobs = {}
    for directory, name in selected:
        manifest = json.loads((directory/'manifest.json').read_text())
        data = (directory/name).read_bytes()
        if manifest['layout'] != 4 or hashlib.sha256(data).hexdigest() != manifest['SHA256'] or len(data) != manifest['bytes']:
            raise ValueError('Current layout4 artifact not bound by its manifest')
        receipts[name] = manifest
        blobs[name] = data
    if len(receipts) == 2:
        factory = receipts['dpn-be7200gr-factory-web.bin']['normal_recovery_payload_manifest']
        upgrade = receipts['dpn-be7200gr-sysupgrade.bin']
        if factory['profiles']['normal']['SHA256'] != upgrade['normal_FIP_SHA256'] or factory['UBI_rootfs_SHA256'] != upgrade['rootfs_SHA256']:
            raise ValueError('Factory installer and sysupgrade contain different normal payloads')
    a.output.mkdir(parents=True, exist_ok=False)
    for name, data in blobs.items():
        (a.output/name).write_bytes(data)
    source = Path(__file__).resolve().parents[2]
    shutil.copytree(source/'LICENSES', a.output/'LICENSES')
    shutil.copy2(source/'LICENSE-STATUS.md', a.output/'LICENSE-STATUS.md')
    (a.output/'SHA256SUMS').write_text(''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in blobs.items()))
    (a.output/'package-manifest.json').write_text(json.dumps({'layout': 4, 'format': a.format,
        'public_release_qualified': False, 'private_factory_backup_included': False,
        'payloads': receipts}, indent=2)+'\n')
    print('LAYOUT4_PUBLIC_ARTIFACT_SET_COLLECTED', a.output)

if __name__ == '__main__':
    main()
