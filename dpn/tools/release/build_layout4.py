#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Assemble the two layout4 images from a completed pinned OpenWrt base build.

Run through tools/with_openwrt_env.sh. This never connects to a router.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

R = Path(__file__).resolve().parents[2]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-id', required=True)
    p.add_argument('--output', type=Path, default=R/'dist/layout4-candidate')
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must not already exist')
    if not json.loads((R/'CLEAN-BASE-STATUS.json').read_text())['base_build_passed']:
        p.error('A completed clean base build is required')
    def run(*args):
        subprocess.run([str(R/'tools/with_openwrt_env.sh'), *map(str, args)], cwd=R, check=True)
    run('python3', R/'tools/release/build_clean_helpers.py')
    run('python3', R/'tools/generic-ram/build.py', '--persistent', '--development-kexec', '--layout-v4-tools',
        '--firmware-dir', R/'build/public-firmware')
    sys.path.insert(0, str(R/'tools/generic-ram'))
    from audit import audit
    kernel = R/'build/generic-persistent/output'
    (kernel/'content-audit.json').write_text(json.dumps(audit(kernel), indent=2)+'\n')
    root = R/'build/generic-persistent/root'
    profiles = R/'build/layout4-profiles'
    run('python3', R/'tools/storage_layout/build_profiles.py', '--kernel-output', kernel,
        '--root', root, '--output', profiles, '--build-id', a.build_id)
    run('python3', R/'tools/storage_layout/audit_profile.py', '--profile', profiles,
        '--output', profiles/'content-audit.json')
    for name in ('vault-check','normal16','bootflag','provisioner','expanded-return','factory-read'):
        run('bash', R/'tools/storage_layout'/('build-'+name+'.sh'), 'host')
    for name in ('test_vault.py','native_vault_test.py','test_bootflag.py','test_provisioner.py',
                 'test_expanded_return.py','test_factory_read.py','test_config_permissions.py'):
        run('python3', R/'tools/storage_layout'/name)
    run('python3', R/'tools/storage_layout/test_normal16.py', '--profile', profiles)
    run('python3', R/'tools/first-install/test_layout4_install.py')
    run('python3', R/'tools/release/package_layout4_factory.py', '--kernel-output', kernel,
        '--root', root, '--profile', profiles, '--output', R/'build/layout4-factory')
    run('python3', R/'tools/storage_layout/package_layout4.py', '--profile', profiles,
        '--output', R/'build/layout4-sysupgrade', '--build-id', a.build_id)
    out = a.output.resolve(); out.mkdir(parents=True)
    images = {}
    for source in (R/'build/layout4-factory/dpn-be7200gr-factory-web.bin',
                   R/'build/layout4-sysupgrade/dpn-be7200gr-sysupgrade.bin'):
        shutil.copy2(source, out/source.name)
        images[source.name] = {'bytes': source.stat().st_size, 'SHA256': hashlib.sha256(source.read_bytes()).hexdigest()}
    (out/'SHA256SUMS').write_text(''.join(v['SHA256']+'  '+n+'\n' for n,v in images.items()))
    (out/'manifest.json').write_text(json.dumps({'layout': 4, 'build_id': a.build_id, 'files': images,
        'private_factory_backups_included': False, 'device_write_performed': False,
        'source_revisions': json.loads((R/'configs/release-sources.json').read_text()),
        'hardware_first_install_qualified': False, 'public_release_qualified': False}, indent=2)+'\n')
    shutil.copytree(R/'LICENSES', out/'LICENSES')
    shutil.copy2(R/'LICENSE-STATUS.md', out/'LICENSE-STATUS.md')
    from package_layout4_set import add_installation_bundle
    add_installation_bundle(out, R)
    print('LAYOUT4_BOTH_ARTIFACTS_ASSEMBLED_NO_DEVICE_OPERATION', out)

if __name__ == '__main__':
    main()
