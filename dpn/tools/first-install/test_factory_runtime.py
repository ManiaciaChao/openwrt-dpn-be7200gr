#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run packaged AArch64 utilities in QEMU user mode, without any device access.

Only syntax checking, help/version output, and key generation in a temporary
host directory are permitted here. Never executes the installation worker.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

R = Path(__file__).resolve().parents[2]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); root = a.root.resolve()
    def target_path(path):
        for _ in range(16):
            if not path.is_symlink(): return path
            target = path.readlink()
            path = root/str(target).lstrip('/') if target.is_absolute() else path.parent/target
        raise AssertionError('Target symlink loop')
    def run(name, *arguments, expected=0):
        binary = target_path(root/name.lstrip('/'))
        assert binary.is_file(), name
        result = subprocess.run([str(R/'tools/with_openwrt_env.sh'), 'qemu-aarch64', '-L', str(root),
                                 '-0', Path(name).name, str(binary), *map(str, arguments)], capture_output=True, timeout=30)
        assert result.returncode == expected, (name, result.returncode, result.stderr.decode(errors='replace')[:400])
        return result.stdout
    required = {'cat','chmod','cmp','cp','cut','dd','echo','grep','insmod','mkdir','rm','rmmod',
                'sed','sha256sum','sh','sync','tr','wc','mount','umount','ln','readlink'}
    def target_file(path):
        # Absolute links in an unpacked target root refer to the target, not
        # to similarly named host tools (insmod -> /sbin/kmodloader, etc.).
        return target_path(path).is_file()
    for name in required:
        assert any(target_file(root/path/name) for path in ('bin','sbin','usr/bin','usr/sbin')), name
    for name in ('lib/upgrade/dpn-factory-auto.sh', 'usr/libexec/dpn-factory-auto',
                 'lib/upgrade/dpn-factory-provision', 'lib/upgrade/dpn-layout4-upgrade.sh'):
        run('/bin/busybox', 'sh', '-n', root/name)
    assert b'GNU tar' in run('/usr/libexec/tar-gnu', '--version')
    # Bare native commands refuse at argument validation, before opening NAND.
    run('/usr/libexec/dpn-vault-build', expected=2)
    run('/usr/libexec/dpn-vault-check', expected=64)
    for name in ('ubiattach','ubidetach','ubiformat','ubimkvol','ubiupdatevol','ubiblock'):
        binary = next((x for x in (root/'sbin'/name, root/'usr/sbin'/name) if x.is_file()), None)
        assert binary is not None, name
        run('/'+binary.relative_to(root).as_posix(), '--help')
    # Exercise the exact target key generator used by the worker, including its
    # output format. Private bytes remain temporary and are never reported.
    with tempfile.TemporaryDirectory() as temporary:
        publics = []
        for index in (0, 1):
            key = Path(temporary)/str(index)
            run('/usr/bin/dropbearkey', '-t', 'ed25519', '-f', key)
            lines = run('/usr/bin/dropbearkey', '-y', '-f', key).splitlines()
            public = next(x for x in lines if x.startswith(b'ssh-ed25519 '))
            assert re.fullmatch(rb'ssh-ed25519 [A-Za-z0-9+/=]+(?: .*)?', public)
            publics.append(public.split()[1])
        assert publics[0] != publics[1]
    a.output.write_text(json.dumps({'packaged_AArch64_tools_executed_in_QEMU': True,
        'required_utilities_present': sorted(required), 'installer_shell_syntax_passed': True,
        'GNU_tar_and_UBI_tools_load': True, 'native_vault_tools_load_and_refuse_missing_arguments': True,
        'target_Dropbear_generates_distinct_Ed25519_keys': True,
        'installer_executed': False, 'device_accessed': False, 'hardware_qualified': False}, indent=2)+'\n')
    print('Packaged AArch64 shell, applets, tar, UBI/native tools and distinct target-generated recovery keys passed QEMU smoke checks; installer not executed')

if __name__ == '__main__':
    main()
