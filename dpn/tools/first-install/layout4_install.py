#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Owner-side layout4 installer. No serial port, stored credential or lab receipt.

Factory Web upload boots a RAM installer. Configure a root password and your
public key in its LuCI first. This tool pins that SSH identity, exports and
decrypt-verifies your backup, then performs separately journaled bounded writes.
All files in the session are private; none belongs in a firmware repository.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import tarfile
import time

R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R/'tools/storage_layout'))
from vault import build as build_vault, fingerprint, parse as parse_vault

REGIONS = {
    'bootloader.bin': (0, 2),
    'vendor-state.bin': (402, 334),
    'ART.bin': (1778, 14),
    'reserved-tail.bin': (1792, 256),
}
PAYLOADS = {'normal.fip', 'recovery.fip', 'rootfs.squashfs'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def private_write(path, data):
    with path.open('xb') as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def configuration_members(data):
    """Reject unsafe archive semantics before any target write is requested."""
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        members = tar.getmembers()
        names = set()
        for m in members:
            name = m.name
            if (not name.startswith('etc/') or any(x in ('.', '..', '') for x in name.rstrip('/').split('/'))
                    or name in names or name in ('etc/dpn-build-id', 'etc/dpn-upgrade-layout', 'etc/dpn-factory-installer')
                    or not (m.isfile() or (m.issym() and name == 'etc/resolv.conf'
                            and m.linkname in ('/tmp/resolv.conf.d/resolv.conf', '/tmp/resolv.conf.d/resolv.conf.auto')))):
                raise ValueError('Unsupported configuration archive member')
            names.add(name)
        required = ('etc/dropbear/authorized_keys', 'etc/dropbear/dropbear_ed25519_host_key', 'etc/shadow')
        if not all(x in names for x in required):
            raise ValueError('Root password and owner SSH identity must be in configuration backup')
        values = {name: tar.extractfile(name).read() for name in required}
        shadow = values['etc/shadow']
        if not re.search(rb'^root:\$[^:\r\n]+:', shadow, re.M):
            raise ValueError('Set a root password in installer LuCI before migration')
        return values

def parse_slot(line):
    tokens = line.split()
    flags = [x for x in tokens if x.startswith('bootflag=')]
    roots = [x for x in tokens if x.startswith('root=')]
    if len(flags) != 1 or len(roots) != 1:
        raise ValueError('Ambiguous original boot handoff')
    pair = (flags[0], roots[0])
    if pair == ('bootflag=0', 'root=/dev/mtdblock3'):
        return 0
    if pair == ('bootflag=1', 'root=/dev/mtdblock6'):
        return 1
    raise ValueError('Unsupported original boot handoff')

class Installer:
    def __init__(self, args):
        self.a = args
        if args.session.is_symlink():
            raise ValueError('Session must be a real private directory')
        self.p = args.session.resolve()
        if any((parent/'.git').exists() for parent in (self.p, *self.p.parents)):
            raise ValueError('Keep the private owner session outside all Git checkouts')
        if args.action == 'prepare':
            self.p.mkdir(mode=0o700, parents=True, exist_ok=False)
        st = self.p.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise ValueError('Session must be owned by you and mode 0700')
        if args.host.startswith('-') or any(c.isspace() for c in args.host) or '@' in args.host:
            raise ValueError('Supply a host address without user or SSH options')
        self.ssh = ['ssh', '-F', '/dev/null', '-i', str(args.identity.resolve()),
                    '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                    '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlgorithms=ssh-ed25519',
                    '-o', 'UserKnownHostsFile='+str(args.known_hosts.resolve()),
                    '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=5',
                    '-o', 'ServerAliveCountMax=2']
        if getattr(args, 'ssh_proxy_command', None):
            self.ssh += ['-o', 'ProxyCommand='+args.ssh_proxy_command]
        self.ssh += ['root@'+args.host]

    def call(self, command, data=None, timeout=120):
        q = subprocess.run(self.ssh+['set -e; '+command], input=data, capture_output=True, timeout=timeout)
        if q.returncode:
            # Never echo remote output: a failing script may have printed private data.
            error = self.p/('ssh-error-'+str(time.time_ns())+'.log')
            private_write(error, q.stderr)
            raise RuntimeError('Pinned SSH command failed; exit='+str(q.returncode)+'; see '+str(error))
        return q.stdout

    def upload(self, path, data):
        self.call('umask 077; test ! -e '+shlex.quote(path)+' && cat > '+shlex.quote(path), data)
        if self.call('sha256sum '+shlex.quote(path)).split()[0].decode() != sha(data):
            raise ValueError('Uploaded file readback mismatch')

    def read_region(self, start, count):
        data = self.call(f'dd if=/dev/mtd0 bs=262144 skip={start} count={count} 2>/dev/null', timeout=900)
        if len(data) != count*262144:
            raise ValueError('Incomplete ECC backup read')
        return data

    def configuration(self):
        # Upstream sysupgrade intentionally refuses -b on tmpfs roots, even
        # returning zero without producing an archive. Reuse its file selection
        # (-l) and archive those files directly in the RAM installer instead.
        lines = self.call('sysupgrade -l').decode().splitlines()
        if not lines or len(lines) != len(set(lines)):
            raise ValueError('Empty or duplicate configuration file list')
        names = []
        for line in lines:
            if not line.startswith('/etc/') or any(x in ('', '.', '..') for x in line[1:].split('/')):
                raise ValueError('Only explicit /etc configuration files can be migrated')
            names.append(line[1:])
        stem = '/tmp/dpn-first-config-'+secrets.token_hex(8)
        self.upload(stem+'.list', ('\n'.join(names)+'\n').encode())
        self.call('/usr/libexec/tar-gnu --warning=no-timestamp --no-recursion --numeric-owner '
                  '-czf '+stem+'.tar.gz -C / -T '+stem+'.list')
        data = self.call('cat '+stem+'.tar.gz')
        configuration_members(data)
        self.call('rm '+stem+'.list '+stem+'.tar.gz')
        return data

    def state(self):
        return json.loads((self.p/'prepared.json').read_text())

    def prepare(self):
        a = self.a
        if not a.age_recipient or not a.age_identity:
            raise ValueError('prepare requires backup age recipient and matching identity for decrypt verification')
        self.call('test -f /etc/dpn-factory-installer; test ! -e /sys/class/ubi/ubi0; '
                  'test -e /sys/firmware/devicetree/base/dpn-layout4/factory-first-install; '
                  'test "$(tr -d "\\000" < /sys/firmware/devicetree/base/dpn-layout4/write-profile)" = provision')
        boot = self.call('cat /proc/sys/kernel/random/boot_id').decode().strip()
        slot = parse_slot(self.call('cat /proc/cmdline').decode())
        config = self.configuration()
        objects = {name: self.read_region(*region) for name, region in REGIONS.items()}
        objects['stock-slot.bin'] = self.read_region(2 if slot == 1 else 202, 200)
        # This is a full original slot, not an OEM download/update container.
        if objects['stock-slot.bin'][:4] != bytes.fromhex('010064aa'):
            raise ValueError('Opposite full stock slot has no FIP header; stop before writes')
        objects['owner-config.tar.gz'] = config
        keys = configuration_members(objects['owner-config.tar.gz'])
        for name in PAYLOADS:
            objects[name] = self.call('cat /usr/share/dpn-install/'+name)
        self.call('/usr/libexec/dpn-image4-check /usr/share/dpn-install/normal.fip '
                  '/usr/share/dpn-install/rootfs.squashfs normal; '
                  '/usr/libexec/dpn-image4-check /usr/share/dpn-install/recovery.fip - recovery')
        vault = build_vault(objects['ART.bin'], bytes.fromhex(sha(objects['stock-slot.bin'])),
                            objects['vendor-state.bin'], keys['etc/dropbear/authorized_keys'],
                            keys['etc/dropbear/dropbear_ed25519_host_key'])
        parse_vault(vault, fingerprint(objects['ART.bin']), True)
        recovery = objects['recovery.fip']
        if not 0 < len(recovery) <= 0x1000000:
            raise ValueError('Recovery exceeds its physical window')
        objects['recovery-and-vault.bin'] = recovery+b'\xff'*(0x1000000-len(recovery))+vault
        state = {'schema': 'dpn-factory-layout4-owner-session-v1', 'factory_boot_ID': boot,
                 'factory_slot': slot, 'original_stock_slot': 1-slot,
                 'files_SHA256': {n: sha(b) for n, b in objects.items()},
                 'factory_fingerprint': fingerprint(objects['ART.bin']).hex(),
                 'no_Flash_write_requested': True}
        for name, data in objects.items():
            private_write(self.p/name, data)
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as tar:
            for name, data in objects.items():
                m = tarfile.TarInfo(name); m.size = len(data); m.mode = 0o600
                tar.addfile(m, io.BytesIO(data))
        encrypted = subprocess.check_output([a.age, '-r', a.age_recipient], input=archive.getvalue())
        backup = self.p/'factory-recovery-backup.tar.gz.age'
        private_write(backup, encrypted)
        plain = subprocess.check_output([a.age, '-d', '-i', str(a.age_identity.resolve()), str(backup)])
        if plain != archive.getvalue():
            raise ValueError('External backup decrypt comparison failed; no write permitted')
        state.update(encrypted_backup_SHA256=sha(encrypted), backup_decrypt_byte_comparison_passed=True)
        private_write(self.p/'prepared.json', (json.dumps(state, indent=2)+'\n').encode())
        print('FACTORY_BACKUP_DECRYPT_VERIFIED_AND_PER_DEVICE_VAULT_PREPARED_NO_FLASH_WRITES')

    def verify_files(self):
        s = self.state()
        if not s['backup_decrypt_byte_comparison_passed']:
            raise ValueError('Verified external backup required')
        for name, expected in s['files_SHA256'].items():
            if sha((self.p/name).read_bytes()) != expected:
                raise ValueError('Prepared file changed: '+name)
        if sha((self.p/'factory-recovery-backup.tar.gz.age').read_bytes()) != s['encrypted_backup_SHA256']:
            raise ValueError('Encrypted backup changed')
        return s

    def job(self, stage, command):
        if not self.a.execute:
            raise ValueError(stage+' requires --execute; no write requested')
        private_write(self.p/(stage+'-requested.json'), (json.dumps({'stage': stage, 'epoch': time.time(),
                      'automatic_retry': False})+'\n').encode())
        quoted = shlex.quote(command+' > /tmp/dpn-factory-'+stage+'.log 2>&1; '
                            'r=$?; printf "%s\\n" "$r" > /tmp/dpn-factory-'+stage+'.exit')
        self.call('setsid sh -c '+quoted+' </dev/null >/dev/null 2>&1 &')
        for _ in range(300):
            time.sleep(4)
            status = self.call('if [ -f /tmp/dpn-factory-'+stage+'.exit ]; then cat /tmp/dpn-factory-'+stage+'.exit; else echo RUNNING; fi').strip()
            if status != b'RUNNING':
                private_write(self.p/(stage+'-device.log'), self.call('cat /tmp/dpn-factory-'+stage+'.log'))
                if status != b'0':
                    raise RuntimeError('Device transaction stopped. Inspect private log; do not retry.')
                private_write(self.p/(stage+'-complete.json'), b'{"verified_job_exit":0}\n')
                return
        raise TimeoutError('Transaction result unknown. Observe existing job; do not retry.')

    def provision(self):
        s = self.verify_files()
        if self.call('cat /proc/sys/kernel/random/boot_id').decode().strip() != s['factory_boot_ID']:
            raise ValueError('Factory boot changed; prepared session no longer applies')
        if not self.a.execute:
            raise ValueError('provision requires --execute; no upload or write requested')
        candidate = (self.p/'recovery-and-vault.bin').read_bytes()
        self.upload('/tmp/dpn-first-recovery-and-vault.bin', candidate)
        self.job('provision', 'sh /lib/upgrade/dpn-factory-provision /tmp/dpn-first-recovery-and-vault.bin '+sha(candidate))
        readback = self.read_region(202, 80)
        if readback != candidate:
            raise ValueError('REC/vault readback mismatch')
        private_write(self.p/'provision-verified.json', b'{"full_REC16_VLT4_host_readback_matches":true}\n')
        print('RECOVERY_AND_VAULT_READBACK_VERIFIED_USE_BOOT_RECOVERY_NEXT')

    def reboot(self, recovery):
        self.verify_files()
        proof = 'provision-verified.json' if recovery else 'migrate-complete.json'
        if not (self.p/proof).exists() or not self.a.execute:
            raise ValueError('Completed transaction and --execute required')
        flag = self.read_region(1791, 1)
        if flag != (b'1' if recovery else b'0')+b'\xff'*(262144-1):
            raise ValueError('Unexpected boot selector')
        # The SSH connection may close before a reply; never auto-retry a reboot.
        private_write(self.p/('boot-recovery-requested' if recovery else 'boot-normal-requested'), b'once\n')
        try:
            q = subprocess.run(self.ssh+['sync; echo b > /proc/sysrq-trigger'], capture_output=True, timeout=20)
            if q.returncode not in (0, 255):
                raise RuntimeError('Reboot result requires observation')
        except subprocess.TimeoutExpired:
            # sysrq resets TCP without a FIN. The request must never be sent
            # twice; install's next stage verifies actual independent boot.
            pass
        print('REBOOT_REQUESTED_ONCE_WAIT_FOR_PINNED_SSH_BEFORE_NEXT_STAGE')

    def migrate(self):
        s = self.verify_files()
        if not self.a.execute or not (self.p/'provision-verified.json').exists():
            raise ValueError('Verified provisioning and --execute required')
        self.call('test "$(cat /etc/dpn-vault-source)" = NAND_DEVICE_BOUND_VAULT; '
                  'test -f /tmp/dpn-vault-recovery.ready; test ! -e /sys/class/ubi/ubi0')
        if self.call('cat /proc/sys/kernel/random/boot_id').decode().strip() == s['factory_boot_ID']:
            raise ValueError('Independent NAND recovery boot not yet verified')
        if sha(self.read_region(202, 80)) != s['files_SHA256']['recovery-and-vault.bin']:
            raise ValueError('Independent recovery/vault changed')
        for name in ('normal.fip', 'rootfs.squashfs', 'owner-config.tar.gz'):
            self.upload('/tmp/dpn-first-'+name, (self.p/name).read_bytes())
        self.job('migrate', 'sh /lib/upgrade/dpn-factory-migrate /tmp/dpn-first-normal.fip '
                 '/tmp/dpn-first-rootfs.squashfs /tmp/dpn-first-owner-config.tar.gz /tmp/dpn-first-work')
        print('LAYOUT4_INSTALLED_USE_BOOT_NORMAL_THEN_VERIFY')

    def verify(self):
        s = self.verify_files()
        self.call('test -f /tmp/dpn-layout4.ready; test ! -f /etc/dpn-factory-installer; '
                  'grep -q " /overlay ubifs " /proc/mounts; grep -q " / overlay " /proc/mounts')
        actual = self.call('sha256sum /dev/ubi0_0').split()[0].decode()
        if actual != s['files_SHA256']['rootfs.squashfs']:
            raise ValueError('Installed base root mismatch')
        for name in ('bootloader.bin', 'reserved-tail.bin'):
            if sha(self.read_region(*REGIONS[name])) != s['files_SHA256'][name]:
                raise ValueError('Protected region changed')
        art = bytearray(self.read_region(*REGIONS['ART.bin']))
        original = bytearray((self.p/'ART.bin').read_bytes())
        art[0x340000] = original[0x340000] = ord('0')
        if art != original:
            raise ValueError('ART changed outside selector')
        if sha(self.read_region(202, 80)) != s['files_SHA256']['recovery-and-vault.bin']:
            raise ValueError('Recovery/vault changed')
        keys = configuration_members((self.p/'owner-config.tar.gz').read_bytes())
        for name, data in keys.items():
            if self.call('cat /'+name) != data:
                raise ValueError('Owner identity changed')
        private_write(self.p/'normal-verified.json', b'{"layout4_root_owner_and_protection_verified":true}\n')
        print('LAYOUT4_NORMAL_BOOT_OWNER_IDENTITY_AND_PROTECTED_REGIONS_VERIFIED')

    def wait_ready(self, command):
        for _ in range(100):
            time.sleep(4)
            try:
                self.call(command, timeout=15)
                return
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
        raise TimeoutError('Boot readiness not proven. Inspect this session; do not repeat installation.')

    def install(self):
        """Single command after prepare; every mutation remains exclusive."""
        if not self.a.execute:
            raise ValueError('install requires --execute; no write requested')
        self.verify_files()
        self.provision()
        self.reboot(True)
        self.wait_ready('test "$(cat /etc/dpn-vault-source)" = NAND_DEVICE_BOUND_VAULT; '
                        'test -f /tmp/dpn-vault-recovery.ready')
        self.migrate()
        self.reboot(False)
        self.wait_ready('test -f /tmp/dpn-layout4.ready')
        self.verify()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'install', 'provision', 'boot-recovery', 'migrate', 'boot-normal', 'verify'])
    p.add_argument('--host', required=True)
    p.add_argument('--identity', type=Path, required=True)
    p.add_argument('--known-hosts', type=Path, required=True)
    p.add_argument('--ssh-proxy-command', help='Optional owner-supplied SSH transport, e.g. for an isolated test namespace')
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--age', default='age')
    p.add_argument('--age-recipient')
    p.add_argument('--age-identity', type=Path)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    instance = Installer(a)
    if a.action.startswith('boot-'):
        instance.reboot(a.action == 'boot-recovery')
    else:
        getattr(instance, a.action)()

if __name__ == '__main__':
    main()
