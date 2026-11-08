#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect actual factory bytes and extracted installer, without a device."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R/'tools'))
sys.path.insert(0, str(R/'tools/stock_return'))
from ummtk import unpack
from inspect_image import fdt_nodes

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--factory', type=Path, required=True)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.factory/'manifest.json').read_text())
    data = (a.factory/'dpn-be7200gr-factory-web.bin').read_bytes()
    assert len(data) == manifest['bytes'] and sha(data) == manifest['SHA256']
    fip = unpack(data, maximum_bytes=0x3200000)  # Exactly one tclinux; no tcboot.
    fit = fdt_nodes(fip[0x2100:])
    for name in ('kernel@1', 'fdt@1', 'filesystem@1'):
        path = '/images/'+name
        payload = bytes(fit[path]['data'])
        hashes = [v for k,v in fit.items() if k.startswith(path+'/hash')]
        assert hashes
        for h in hashes:
            algorithm = bytes(h['algo']).rstrip(b'\0').decode()
            assert algorithm in ('sha1', 'sha256')
            assert hashlib.new(algorithm, payload).digest() == bytes(h['value'])
    dt = fdt_nodes(bytes(fit['/images/fdt@1']['data']))['/dpn-layout4']
    assert bytes(dt['write-profile']) == b'provision\0' and 'factory-first-install' in dt
    mode = manifest['first_install_mode']
    assert ('factory-auto-install' in dt) == (mode == 'automatic')
    filesystem = bytes(fit['/images/filesystem@1']['data'])
    assert sha(filesystem) == manifest['installer_rootfs_SHA256'] == bytes(dt['installer-rootfs-sha256']).hex()
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary); sq = tmp/'root.squashfs'; sq.write_bytes(filesystem)
        root = tmp/'root'
        subprocess.run([str(R/'tools/with_openwrt_env.sh'), str(R/'openwrt/staging_dir/host/bin/unsquashfs4'),
                        '-no-progress', '-d', str(root), str(sq)], check=True, stdout=subprocess.DEVNULL)
        assert not list((root/'etc/dropbear').iterdir())
        assert not (root/'root/.ssh').exists() and not (root/'etc/dpn-recovery').exists()
        assert next(x.split(':')[1] for x in (root/'etc/shadow').read_text().splitlines() if x.startswith('root:')) == ''
        assert not (root/'etc/config/wireless').read_text().strip()
        assert b"option PasswordAuth 'off'" in (root/'etc/config/dropbear').read_bytes()
        # No generated owner key, host key, calibration dump or private vault
        # is allowed in the public installer, even outside expected directories.
        for file in root.rglob('*'):
            if not file.is_file() or file.is_symlink(): continue
            body = file.read_bytes()
            assert not re.search(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{16}', body), file.relative_to(root)
        for name in ('normal.fip', 'recovery.fip', 'rootfs.squashfs'):
            assert (root/'usr/share/dpn-install'/name).read_bytes() == (a.profile/name).read_bytes()
        if mode == 'automatic':
            assert (root/'etc/dpn-factory-auto').read_text() == 'automatic-v1\n'
            assert (root/'etc/rc.d/S98dpn_factory_auto').readlink().as_posix() == '../init.d/dpn_factory_auto'
            for name in ('usr/libexec/dpn-factory-auto', 'lib/upgrade/dpn-factory-auto.sh', 'etc/init.d/dpn_factory_auto'):
                assert (root/name).read_bytes() == (R/'tools/generic-ram/overlay'/name).read_bytes()
            assert (root/'usr/libexec/dpn-factory-auto').stat().st_mode & 0o111
            assert (root/'usr/libexec/dpn-vault-build').read_bytes() == (R/'build/storage-layout/dpn-vault-build').read_bytes()
            assert manifest['automatic_install_after_boot'] and not manifest['external_owner_backup_required_before_layout_migration']
        else:
            assert not (root/'etc/dpn-factory-auto').exists()
    a.output.write_text(json.dumps({'actual_UMMtk_FIP_FIT_and_SquashFS_inspected': True,
        'first_install_mode': mode, 'bytes': len(data), 'SHA256': sha(data),
        'single_tclinux_no_bootloader_component': True, 'embedded_payloads_match_profiles': True,
        'private_owner_inputs_absent': True, 'automatic_sources_and_native_builder_match': mode == 'automatic',
        'hardware_tested': False, 'public_release_qualified': False}, indent=2)+'\n')
    print('ACTUAL_FACTORY_CONTAINER_PAYLOADS_PRIVATE_INPUTS_AND_INSTALLATION_MODE_AUDIT_PASSED', mode)

if __name__ == '__main__':
    main()
