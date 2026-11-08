#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline first-install identity, archive and transaction refusal tests."""
import argparse
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
import subprocess
from unittest.mock import patch

from layout4_install import Installer, configuration_members, parse_slot, private_write

def config(extra=(), shadow=b'root:$6$synthetic-only:0:0:99999:7:::\n'):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode='w:gz') as t:
        for name, data in [('etc/dropbear/authorized_keys', b'ssh-ed25519 synthetic-only\n'),
                           ('etc/dropbear/dropbear_ed25519_host_key', b'synthetic-host-identity'),
                           ('etc/shadow', shadow)]:
            m = tarfile.TarInfo(name); m.size = len(data); t.addfile(m, io.BytesIO(data))
        for m in extra:
            t.addfile(m, io.BytesIO(b'x'*m.size) if m.isfile() else None)
    return b.getvalue()

class InstallTests(unittest.TestCase):
    def test_slots_require_consistent_unique_handoff(self):
        for slot, root in [(0, 3), (1, 6)]:
            self.assertEqual(parse_slot(f'console=x bootflag={slot} root=/dev/mtdblock{root}'), slot)
        for line in ('', 'bootflag=1 root=/dev/mtdblock3', 'bootflag=0 bootflag=1 root=/dev/mtdblock6',
                     'bootflag=0 root=/dev/mtdblock3 root=/dev/mtdblock3'):
            with self.assertRaises(ValueError): parse_slot(line)

    def test_owner_identity_and_password_required(self):
        self.assertIn('etc/dropbear/authorized_keys', configuration_members(config()))
        for shadow in (b'root::0:0:99999:7:::\n', b'root:!:0:0:99999:7:::\n'):
            with self.assertRaises(ValueError): configuration_members(config(shadow=shadow))

    def test_reject_archive_traversal_links_duplicate_and_image_markers(self):
        for name in ('etc/../root/key', '/etc/shadow', 'etc//config/x', 'etc/./config/x',
                     'etc/dpn-build-id', 'etc/dpn-factory-installer', 'etc/dropbear/authorized_keys'):
            with self.assertRaises(ValueError): configuration_members(config([tarfile.TarInfo(name)]))
        m = tarfile.TarInfo('etc/escape'); m.type = tarfile.SYMTYPE; m.linkname = '/root'
        with self.assertRaises(ValueError): configuration_members(config([m]))
        m = tarfile.TarInfo('etc/resolv.conf'); m.type = tarfile.SYMTYPE; m.linkname = '/tmp/resolv.conf.d/resolv.conf.auto'
        configuration_members(config([m]))

    def test_journal_private_and_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'journal'
            private_write(p, b'once')
            self.assertEqual(p.stat().st_mode&0o777, 0o600)
            with self.assertRaises(FileExistsError): private_write(p, b'twice')
            self.assertEqual(p.read_bytes(), b'once')

    def test_no_execute_never_calls_remote_transaction(self):
        with tempfile.TemporaryDirectory() as d:
            a = argparse.Namespace(session=Path(d), action='verify', host='192.0.2.1', identity=Path('key'),
                                   known_hosts=Path('hosts'), execute=False)
            i = Installer(a)
            with patch.object(i, 'call', side_effect=AssertionError('remote operation')):
                with self.assertRaises(ValueError): i.job('provision', 'must-not-run')
            self.assertFalse((Path(d)/'provision-requested.json').exists())

    def test_reboot_disconnect_timeout_is_observed_without_reissuing_request(self):
        with tempfile.TemporaryDirectory() as d:
            a = argparse.Namespace(session=Path(d), action='boot-recovery', host='192.0.2.1',
                                   identity=Path('key'), known_hosts=Path('hosts'), execute=True)
            i = Installer(a)
            private_write(Path(d)/'provision-verified.json', b'{}\n')
            with patch.object(i, 'verify_files', return_value={}), \
                 patch.object(i, 'read_region', return_value=b'1'+b'\xff'*(262144-1)), \
                 patch('layout4_install.subprocess.run', side_effect=subprocess.TimeoutExpired('ssh',20)) as run:
                i.reboot(True)
                self.assertEqual(run.call_count, 1)
                with self.assertRaises(FileExistsError): i.reboot(True)
                self.assertEqual(run.call_count, 1)

    def test_RAM_configuration_uses_standard_list_without_sysupgrade_backup(self):
        with tempfile.TemporaryDirectory() as d:
            a=argparse.Namespace(session=Path(d),action='verify',host='192.0.2.1',identity=Path('key'),
                                 known_hosts=Path('hosts'),execute=False)
            i=Installer(a); archive=config(); calls=[]
            def remote(command,*args,**kwargs):
                calls.append(command)
                if command=='sysupgrade -l': return b'/etc/shadow\n/etc/dropbear/authorized_keys\n/etc/dropbear/dropbear_ed25519_host_key\n'
                if command.startswith('cat '): return archive
                return b''
            with patch.object(i,'call',side_effect=remote), patch.object(i,'upload'):
                self.assertEqual(i.configuration(),archive)
            self.assertFalse(any('sysupgrade -b' in x for x in calls))

if __name__ == '__main__':
    unittest.main()
