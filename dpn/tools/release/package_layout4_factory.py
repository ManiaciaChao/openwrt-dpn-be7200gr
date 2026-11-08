#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a public factory RAM installer containing both final layout4 payloads.

It occupies at most the OEM 50 MiB slot, not the normal 16 MiB kernel window.
Factory-root bytes are verified and copied into RAM before provisioning can
overwrite that slot. No vault, factory dump, identity or credentials is input.
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
sys.path.insert(0, str(R/'tools/generic-ram'))
from public_fip import build
sys.path.insert(0, str(R/'tools'))
from ummtk import pack, unpack

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel-output', type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--first-install', choices=['automatic', 'host'], default='automatic',
                   help='Automatic on-device installation (default), or legacy host-driven RAM setup')
    a = p.parse_args()
    k, source, profiles, out = (x.resolve() for x in (a.kernel_output, a.root, a.profile, a.output))
    km = json.loads((k/'manifest.json').read_text())
    pm = json.loads((profiles/'manifest.json').read_text())
    if not km['experimental_layout_v4_tools'] or pm['layout'] != 4:
        raise ValueError('Layout4 kernel and normal/recovery profiles required')
    # Audit the kernel actually being packaged, including the new factory entry.
    from audit import audit, cpio_files
    import gzip
    kernel_audit = audit(k)
    import lzma
    if lzma.decompress((k/'Image.lzma').read_bytes(), format=lzma.FORMAT_ALONE) != (k/'Image').read_bytes():
        raise ValueError('Compressed kernel differs from audited kernel')
    embedded = cpio_files(gzip.decompress((k/'initramfs.cpio.gz').read_bytes()))
    for name in ('init', 'lib/upgrade/dpn-factory-ram-boot.sh'):
        if embedded[name][1] != (R/'tools/generic-ram/overlay'/name).read_bytes():
            raise ValueError('Stale embedded factory entry: '+name)
    out.mkdir(parents=True, exist_ok=False)
    root = out/'installer-root'
    shutil.copytree(source, root, symlinks=True)
    if any((root/'etc/dropbear').iterdir()) or (root/'root/.ssh').exists():
        raise ValueError('Owner identity must not be an image input')
    shadow = (root/'etc/shadow').read_text()
    if not any(x.startswith('root:!:') or x.startswith('root:*:') for x in shadow.splitlines()):
        raise ValueError('Normal root must be password locked')
    # This empty password is confined to the direct-LAN RAM setup environment.
    (root/'etc/shadow').write_text('\n'.join('root::0:0:99999:7:::' if x.startswith('root:') else x for x in shadow.splitlines())+'\n')
    (root/'etc/shadow').chmod(0o600)
    automatic = a.first_install == 'automatic'
    (root/'etc/dpn-factory-installer').write_text('AUTOMATIC_FIRST_INSTALL\n' if automatic else 'RAM_ONLY_CONFIGURE_PASSWORD_AND_PUBLIC_KEY_THEN_EXPORT_BACKUP\n')
    (root/'etc/dpn-factory-auto').unlink(missing_ok=True)
    if automatic:
        # Refuse a stale root instead of shipping a silently non-automatic image.
        for name in ('usr/libexec/dpn-vault-build', 'usr/libexec/dpn-factory-auto',
                     'lib/upgrade/dpn-factory-auto.sh', 'etc/init.d/dpn_factory_auto'):
            if not (root/name).is_file():
                raise ValueError('Missing automatic installer input: '+name)
        for name in ('usr/libexec/dpn-factory-auto', 'lib/upgrade/dpn-factory-auto.sh',
                     'etc/init.d/dpn_factory_auto'):
            if (root/name).read_bytes() != (R/'tools/generic-ram/overlay'/name).read_bytes():
                raise ValueError('Stale automatic installer source: '+name)
        if (root/'usr/libexec/dpn-vault-build').read_bytes() != (R/'build/storage-layout/dpn-vault-build').read_bytes():
            raise ValueError('Stale native vault builder')
        (root/'etc/dpn-factory-auto').write_text('automatic-v1\n')
        service = root/'etc/rc.d/S98dpn_factory_auto'
        service.unlink(missing_ok=True)
        service.symlink_to('../init.d/dpn_factory_auto')
    (root/'etc/config/network').write_text('''config interface 'loopback'
 option device 'lo'
 option proto 'static'
 option ipaddr '127.0.0.1'
 option netmask '255.0.0.0'
config device 'recovery_bridge'
 option name 'br-lan'
 option type 'bridge'
 option stp '1'
 list ports 'lan10'
 list ports 'ge1'
 list ports 'ge2'
 list ports 'ge3'
 list ports 'ge4'
config interface 'lan'
 option device 'br-lan'
 option proto 'static'
 option ipaddr '192.168.1.1'
 option netmask '255.255.255.0'
 list ip6addr 'fe80::72:104/64'
 option delegate '0'
config interface 'wan'
 option device 'wan10'
 option proto 'none'
 option delegate '0'
''')
    (root/'etc/config/dhcp').write_text('''config dnsmasq
 option port '53'
 option domainneeded '1'
 option boguspriv '1'
 option authoritative '1'
 option leasefile '/tmp/dhcp.leases'
config dhcp 'lan'
 option interface 'lan'
 option start '100'
 option limit '100'
 option leasetime '1h'
''')
    (root/'etc/config/wireless').write_text('')
    for file in (root/'etc/rc.d').glob('*dpn_wifi_ram'):
        file.unlink()
    payload = root/'usr/share/dpn-install'
    payload.mkdir(parents=True)
    for name in ('normal.fip', 'recovery.fip', 'rootfs.squashfs'):
        shutil.copy2(profiles/name, payload/name)
    shutil.copy2(profiles/'manifest.json', payload/'manifest.json')
    (payload/'SHA256SUMS').write_text(''.join(hashlib.sha256((payload/name).read_bytes()).hexdigest()+'  '+name+'\n'
                                            for name in ('normal.fip', 'recovery.fip', 'rootfs.squashfs')))
    # These non-.sh commands are explicit entrypoints, never sourced as hooks.
    for name in ('dpn-factory-provision', 'dpn-factory-migrate'):
        (root/'lib/upgrade'/name).chmod(0o755)
    host = R/'openwrt/staging_dir/host/bin'
    wrapper = R/'tools/with_openwrt_env.sh'
    epoch = str(km['source_epoch'])
    def run(*argv):
        return subprocess.check_output([str(wrapper), *map(str, argv)], cwd=out,
                                       env=os.environ|{'SOURCE_DATE_EPOCH': epoch})
    log = run('env', '-u', 'SOURCE_DATE_EPOCH', host/'mksquashfs4', root, out/'installer.squashfs',
              '-noappend', '-all-root', '-comp', 'xz', '-b', '262144', '-processors', '4',
              '-mkfs-time', epoch, '-all-time', epoch)
    (out/'squashfs.log').write_bytes(log)
    filesystem = (out/'installer.squashfs').read_bytes()
    fs_sha = hashlib.sha256(filesystem).hexdigest()
    shutil.copy2(k/'board.dtb', out/'installer.dtb')
    shutil.copy2(k/'Image.lzma', out/'Image.lzma')
    dt = out/'installer.dtb'
    run('fdtput', '-t', 's', dt, '/', 'compatible', 'dlink,dpn-be7200gr',
        'dlink,dpn-be7200gr-layout4', 'dlink,dpn-be7200gr-install',
        'dlink,dpn-be7200gr-persist', 'dlink,dpn-be7200gr-ram', 'airoha,an7581', 'airoha,en7581')
    run('fdtput', '-c', dt, '/dpn-layout4')
    for name, value in [('format-version', 4), ('normal-slot', 0), ('recovery-slot', 1), ('vault-size', 0x400000)]:
        run('fdtput', '-t', 'x', dt, '/dpn-layout4', name, format(value, 'x'))
    run('fdtput', '-t', 's', dt, '/dpn-layout4', 'write-profile', 'provision')
    run('fdtput', dt, '/dpn-layout4', 'factory-first-install')
    if automatic:
        run('fdtput', dt, '/dpn-layout4', 'factory-auto-install')
    run('fdtput', '-t', 'bx', dt, '/dpn-layout4', 'installer-rootfs-sha256', *[fs_sha[i:i+2] for i in range(0,64,2)])
    its = '''/dts-v1/; / { description="DPN-BE7200GR factory RAM first installer"; #address-cells=<1>;
images {
 fdt@1 { data=/incbin/("installer.dtb"); type="flat_dt"; arch="arm64"; compression="none"; load=<0x8d000000>; hash@1 { algo="sha1"; }; };
 kernel@1 { data=/incbin/("Image.lzma"); type="kernel"; arch="arm64"; os="linux"; compression="lzma"; load=<0x8b000000>; entry=<0x8b000000>; hash@1 { algo="sha1"; }; };
 filesystem@1 { data=/incbin/("installer.squashfs"); type="filesystem"; arch="arm64"; os="linux"; compression="none"; hash@1 { algo="sha1"; }; };
}; configurations { default="conf@1"; conf@1 { kernel="kernel@1"; fdt="fdt@1"; }; }; };'''
    (out/'installer.its').write_text(its)
    (out/'mkimage.log').write_bytes(run(host/'mkimage', '-f', 'installer.its', 'installer.itb'))
    fip = build((out/'installer.itb').read_bytes(), maximum_bytes=0x3200000)
    blob = pack(fip, maximum_bytes=0x3200000)
    if unpack(blob, maximum_bytes=0x3200000) != fip:
        raise ValueError('Factory container roundtrip failed')
    (out/'dpn-be7200gr-factory-web.bin').write_bytes(blob)
    sha = hashlib.sha256(blob).hexdigest()
    (out/'SHA256SUMS').write_text(sha+'  dpn-be7200gr-factory-web.bin\n')
    (out/'manifest.json').write_text(json.dumps({
        'layout': 4, 'factory_RAM_first_installer': True, 'bytes': len(blob), 'SHA256': sha,
        'OEM_slot_limit_bytes': 0x3200000, 'boot_does_not_format_or_provision': not automatic,
        'first_install_mode': a.first_install,
        'automatic_install_after_boot': automatic,
        'external_owner_backup_required_before_layout_migration': not automatic,
        'full_stock_backup_created_by_installer': False,
        'recovery_readback_before_migration': True,
        'independent_recovery_boot_before_migration': not automatic,
        'installer_rootfs_SHA256': fs_sha, 'kernel_audit': kernel_audit,
        'normal_recovery_payload_manifest': pm, 'private_device_inputs_embedded': False,
        'hardware_factory_installer_tested': False, 'public_release_qualified': False,
    }, indent=2)+'\n')
    print('LAYOUT4_FACTORY_RAM_INSTALLER_PACKAGED_NO_DEVICE_OPERATION', len(blob))

if __name__ == '__main__':
    main()
