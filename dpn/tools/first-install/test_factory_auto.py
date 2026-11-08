#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the real shell coordinator with mocked destructive boundaries.

No device connections, Flash operations, root privileges or reboots.
"""
import os
from pathlib import Path
import subprocess
import tempfile

R = Path(__file__).resolve().parents[2]
source = (R/'tools/generic-ram/overlay/lib/upgrade/dpn-factory-auto.sh').read_text()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    library = root/'functions'
    library.write_text(source.replace('local work=/tmp/dpn-factory-auto', 'local work="$AUTO_TEST_WORK"')
                      .replace('echo b > /proc/sysrq-trigger', 'dpn_test_reboot'))
    harness = r'''
set -eu
. "$1"
dpn_auto_status() { printf '%s\n' "$1" >> "$AUTO_TEST_LOG"; }
phase() { printf '%s\n' "$1" >> "$AUTO_TEST_LOG"; [ "$AUTO_TEST_FAIL" != "$1" ]; }
dpn_auto_preflight() { phase preflight; }
dpn_auto_seed() { phase seed; }
dpn_auto_prepare() { phase prepare; }
dpn_auto_provision() { phase provision; }
dpn_auto_install() { phase install; }
sync() { phase sync; }
dpn_test_reboot() { phase reboot; }
dpn_auto_run
'''
    phases = ['preflight', 'seed', 'prepare', 'provision', 'install']
    for fail in [*phases, 'sync', 'none']:
        work = root/fail
        log = root/(fail+'.log')
        env = os.environ | {'AUTO_TEST_WORK': str(work), 'AUTO_TEST_LOG': str(log), 'AUTO_TEST_FAIL': fail}
        # The test reboot returns; production must stop, never retry the reboot.
        result = subprocess.run(['sh', '-c', harness, 'test', str(library)], env=env)
        assert result.returncode != 0
        seen = log.read_text().splitlines()
        called = [x for x in seen if x in phases]
        assert called == (phases if fail in ('none', 'sync') else phases[:phases.index(fail)+1]), seen
        assert ('reboot' in seen) == (fail == 'none'), seen
        assert seen.count('reboot') <= 1
        assert work.is_dir() and work.stat().st_mode & 0o777 == 0o700
        log.write_text('')
        subprocess.run(['sh', '-c', harness, 'test', str(library)], env=env, stderr=subprocess.DEVNULL)
        assert not log.read_text(), 'Existing transaction must refuse before any stage or status overwrite'

    # Exercise the real seed function using host GNU tar and a synthetic
    # dropbearkey executable, verifying the resulting archive rather than only
    # checking command strings.
    etc = root/'etc'; (etc/'config').mkdir(parents=True)
    (etc/'config/network').write_text("config interface 'lan'\n option proto 'static'\n")
    (etc/'config/wireless').write_text('')
    for name in ('passwd', 'group', 'shells'): (etc/name).write_text('fixture\n')
    (etc/'shadow').write_text('root:!:0:0:99999:7:::\n')
    bin_dir = root/'bin'; bin_dir.mkdir()
    keygen = bin_dir/'dropbearkey'
    keygen.write_text('''#!/bin/sh
if [ "$1" = -y ]; then echo 'Public key portion is:'; echo 'ssh-ed25519 AAAAFixtureOnly fixture'; exit; fi
[ "$1" = -t ] && [ "$2" = ed25519 ] && [ "$3" = -f ] || exit 1
dd if=/dev/urandom of="$4" bs=32 count=1 2>/dev/null
'''); keygen.chmod(0o755)
    seed_source = root/'seed-functions'
    # Substitute only target paths; retain the production seed/archive logic.
    seed_source.write_text(source.replace('/usr/libexec/tar-gnu', 'tar')
                           .replace('for file in /etc/config/*', 'for file in '+str(etc)+'/config/*')
                           .replace('"/etc/$file"', '"'+str(etc)+'/$file"')
                           .replace(' /etc/shadow ', ' '+str(etc/'shadow')+' ')
                           .replace('[ -f /etc/sysupgrade.conf ]', '[ -f '+str(etc/'sysupgrade.conf')+' ]')
                           .replace('cp /etc/sysupgrade.conf ', 'cp '+str(etc/'sysupgrade.conf')+' '))
    import tarfile
    generated = []
    for index in range(2):
        work = root/('seed-'+str(index)); work.mkdir()
        subprocess.run(['sh', '-ec', 'umask 077; . "$1"; dpn_auto_seed "$2"', 'test', str(seed_source), str(work)],
                       env=os.environ | {'PATH': str(bin_dir)+':'+os.environ['PATH']}, check=True)
        with tarfile.open(work/'config.tar.gz') as archive:
            names = set(archive.getnames())
            assert not any('factory-auto' in n or 'factory-installer' in n for n in names)
            assert archive.extractfile('etc/shadow').read().startswith(b'root::')
            assert b'/etc/dpn-recovery/' in archive.extractfile('etc/sysupgrade.conf').read().splitlines()
            assert archive.getmember('etc/dpn-recovery/access.key').mode == 0o600
            assert archive.getmember('etc/dropbear').mode == 0o700
            generated.append(archive.extractfile('etc/dpn-recovery/access.key').read())
    assert generated[0] != generated[1], 'No common recovery identity across installations'
    # Physical defaults reset must retain the actual client private key, not
    # merely the authorized public key or host identity.
    defaults = root/'defaults'; (defaults/'config').mkdir(parents=True)
    for name in ('network', 'dhcp'): (defaults/'config'/name).write_text('fixture\n')
    (defaults/'shadow').write_text('root:!:0:0:99999:7:::\n')
    uci = bin_dir/'uci'; uci.write_text('#!/bin/sh\nexit 0\n'); uci.chmod(0o755)
    reset = R/'tools/generic-ram/overlay/lib/upgrade/dpn-reset-defaults.sh'
    stage = root/'reset-stage'
    subprocess.run(['sh', '-ec', '. "$1"; dpn_reset_seed "$2" "$3" "$4"', 'test',
                    str(reset), str(stage), str(root/'seed-0/seed/etc'), str(defaults)],
                   env=os.environ | {'PATH': str(bin_dir)+':'+os.environ['PATH']}, check=True)
    assert (stage/'etc/dpn-recovery/access.key').read_bytes() == generated[0]
    assert (stage/'etc/dpn-recovery/access.key').stat().st_mode & 0o777 == 0o600
    assert (stage/'etc/dpn-recovery').stat().st_mode & 0o777 == 0o700
    assert '/etc/dpn-recovery/' in (stage/'etc/sysupgrade.conf').read_text().splitlines()
print('Automatic installer: ordered stages, failure at every boundary, no write/reboot retries, private fresh configuration and per-device recovery key preservation passed')
