#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise reset timing and failure behavior without rebooting or erasing data."""
import os
from pathlib import Path
import subprocess
import tempfile
import shutil

R = Path(__file__).resolve().parents[2]
source = (R/'tools/generic-ram/overlay/etc/rc.button/reset').read_text()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    binary = root/'bin'; binary.mkdir()
    log = root/'actions'
    for name in ('reboot', 'sync', 'logger', 'dpn-factory-reset'):
        script = binary/name
        script.write_text('#!/bin/sh\necho "'+name+'" >> "$BUTTON_TEST_LOG"\n'
                          + ('exit "${RESET_RESULT:-0}"\n' if name == 'dpn-factory-reset' else 'exit 0\n'))
        script.chmod(0o755)
    handler = root/'reset'
    handler.write_text(source.replace('/tmp/dpn-layout4.ready', str(root/'ready'))
                      .replace('/etc/dpn-vault-source', str(root/'recovery'))
                      .replace('/usr/libexec/dpn-factory-reset', str(binary/'dpn-factory-reset')))
    def event(action, seen, ready=True, recovery=False, result='0'):
        (root/'ready').unlink(missing_ok=True)
        (root/'recovery').unlink(missing_ok=True)
        if ready: (root/'ready').touch()
        if recovery: (root/'recovery').touch()
        log.unlink(missing_ok=True)
        env = os.environ | {'PATH': str(binary)+':'+os.environ['PATH'],
                            'BUTTON_TEST_LOG': str(log), 'ACTION': action,
                            'SEEN': str(seen), 'RESET_RESULT': result}
        outcome = subprocess.run(['sh', str(handler)], env=env, check=False)
        return outcome.returncode, log.read_text().splitlines() if log.exists() else []
    assert event('pressed', 0) == (5, [])
    for duration in (1, 2, 4): assert event('released', duration) == (0, [])
    assert event('released', 0) == (0, ['sync', 'reboot'])
    assert event('released', 5) == (0, ['dpn-factory-reset', 'sync', 'reboot'])
    assert event('released', 10) == (0, ['dpn-factory-reset', 'sync', 'reboot'])
    assert event('released', 5, result='1')[1] == ['dpn-factory-reset']
    for duration in ('', '-1', 'bad'): assert event('released', duration) == (1, [])
    assert event('released', 10, ready=False) == (0, [])
    assert event('released', 10, recovery=True) == (0, [])
print('Reset timing, invalid events, recovery exclusion and preparation failure passed')

# Interrupt the real commit helper after each filesystem operation. At early
# boot a retry must retain the staged keys and remove the old overlay.
helper = R/'tools/generic-ram/overlay/lib/upgrade/dpn-config-commit.sh'
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    binary = root/'bin'; binary.mkdir()
    for name in ('mv', 'rm', 'mkdir', 'sync'):
        script = binary/name
        script.write_text('#!/bin/sh\n'+shutil.which(name)+' "$@" || exit $?\n'
                          'n=$(cat "$COUNTER"); n=$((n+1)); echo "$n" > "$COUNTER"\n'
                          '[ "$n" != "$FAIL_AFTER" ] || exit 97\n')
        script.chmod(0o755)
    for fail in range(8):
        data = root/str(fail)
        (data/'upper/etc').mkdir(parents=True)
        (data/'upper/etc/old-package').touch()
        (data/'work').mkdir()
        (data/'dpn-upgrade-next/upper/etc/dropbear').mkdir(parents=True)
        (data/'dpn-upgrade-next/upper/etc/dropbear/authorized_keys').write_text('fixture-owner-key')
        (data/'dpn-upgrade.pending').write_text('v1\n')
        counter = root/'counter'; counter.write_text('0')
        env = os.environ | {'PATH': str(binary)+':'+os.environ['PATH'],
                            'COUNTER': str(counter), 'FAIL_AFTER': str(fail)}
        command = ['sh', '-c', '. "$1"; dpn_config_commit "$2"',
                   'test', str(helper), str(data)]
        subprocess.run(command, env=env, check=False)
        env['FAIL_AFTER'] = '-1'
        subprocess.run(command, env=env, check=True)
        assert (data/'upper/etc/dropbear/authorized_keys').read_text() == 'fixture-owner-key'
        assert not (data/'upper/etc/old-package').exists()
        assert not (data/'dpn-upgrade.pending').exists()
        assert (data/'work').is_dir()
print('Eight real directory-commit interruption/retry cases passed')
