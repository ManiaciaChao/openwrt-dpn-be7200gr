#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Collect only the two layout4 firmware outputs and their provenance files."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

def add_installation_bundle(output, source):
    """Ship the two small owner-side Python sources with the firmware set.
    Users need not clone the entire OpenWrt source just to finish first install.
    """
    for name in ('tools/first-install/layout4_install.py','tools/storage_layout/vault.py'):
        dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/name,dest)
    shutil.copy2(source/'docs/generic-first-install.md',output/'INSTALL.md')
    shutil.copy2(source/'docs/stock-backup.md',output/'stock-backup.md')
    (output/'README.txt').write_text('''D-Link DPN-BE7200GR layout4 candidate

Read INSTALL.md before uploading either firmware file.
factory-web.bin is for the original OEM Web interface; sysupgrade.bin is for
an installed layout4 OpenWrt system. The RAM first installer requires your own
LuCI password/public key and an external verified backup before persistence.
Run the included tools/first-install/layout4_install.py from this extracted
directory; Python 3, OpenSSH and age are required on the owner's computer.
Private device backups and credentials are not included in this download.
Preserve LICENSES/ and LICENSE-STATUS.md when redistributing these artifacts.
''')
    included=[p for p in output.rglob('*') if p.is_file() and p.suffix!='.zip' and p.name!='ZIP_SHA256SUMS']
    target=output/'dpn-be7200gr-layout4-install.zip'
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(included):
            entry=zipfile.ZipInfo(path.relative_to(output).as_posix(),date_time=(1980,1,1,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
            archive.writestr(entry,path.read_bytes(),compresslevel=9)
    (output/'ZIP_SHA256SUMS').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--factory', type=Path, required=True)
    p.add_argument('--sysupgrade', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--format', choices=['both', 'factory-web', 'sysupgrade'], default='both')
    p.add_argument('--qualification', type=Path, help='Reviewed hardware receipt bound to these exact image hashes')
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
    qualification=None
    if a.qualification:
        qualification=json.loads(a.qualification.read_text())
        for name,data in blobs.items():
            expected=qualification['files'][name]
            if expected['SHA256']!=hashlib.sha256(data).hexdigest() or expected['bytes']!=len(data):
                raise ValueError('Hardware receipt belongs to a different firmware image')
        required=('actual_normal_original_Web_upload_booted_generic_RAM_installer',
                  'actual_independent_NAND_recovery_boot_and_owner_SSH_passed',
                  'exact_matching_standard_sysupgrade_without_manual_checkpoint_passed',
                  'physical_OFF_5s_ON_after_final_upgrade_passed')
        if not all(qualification.get(k) is True for k in required):
            raise ValueError('Incomplete hardware qualification receipt')
    a.output.mkdir(parents=True, exist_ok=False)
    for name, data in blobs.items():
        (a.output/name).write_bytes(data)
    source = Path(__file__).resolve().parents[2]
    shutil.copytree(source/'LICENSES', a.output/'LICENSES')
    shutil.copy2(source/'LICENSE-STATUS.md', a.output/'LICENSE-STATUS.md')
    (a.output/'SHA256SUMS').write_text(''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in blobs.items()))
    if qualification:
        shutil.copy2(a.qualification,a.output/'qualification.json')
    (a.output/'package-manifest.json').write_text(json.dumps({'layout': 4, 'format': a.format,
        'public_release_qualified': qualification is not None,
        'qualification_scope': qualification.get('qualification_scope') if qualification else None,
        'production_release_qualified': False, 'private_factory_backup_included': False,
        'payloads': receipts}, indent=2)+'\n')
    add_installation_bundle(a.output, source)
    print('LAYOUT4_PUBLIC_ARTIFACT_SET_COLLECTED', a.output)

if __name__ == '__main__':
    main()
