#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the real WPS LED loop against temporary files, never host GPIOs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

R = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary); led = root/'mesh'; led.mkdir()
    binary = root/'bin'; binary.mkdir()
    config = root/'config.json'
    def write_config(trigger='none', state='Disabled'):
        draft = root/'next.json'
        draft.write_text(json.dumps({'system.dpn_mesh.sysfs': 'mesh',
                                    'system.dpn_mesh.trigger': trigger,
                                    'pbc_status': state}))
        draft.replace(config)
    for name in ('uci', 'ubus', 'jsonfilter'):
        command = binary/name
        command.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
d=json.loads(Path(os.environ['FIXTURE_CONFIG']).read_text())
name=Path(sys.argv[0]).name
if name=='uci': print(d[sys.argv[-1]])
elif name=='ubus':
 if 'list' in sys.argv: print('hostapd.fixture')
 else: print(json.dumps({'pbc_status':d['pbc_status']}))
else: print(json.load(sys.stdin)['pbc_status'])
''')
        command.chmod(0o755)
    command = binary/'sleep'
    command.write_text('#!/bin/sh\nexec '+shutil.which('sleep')+' 0.03\n')
    command.chmod(0o755)
    source = root/'worker.sh'
    source.write_text((R/'tools/generic-ram/overlay/usr/libexec/dpn-wps-led').read_text()
                      .replace('/sys/class/leds/mesh', str(led)))
    env = os.environ | {'PATH': str(binary)+':'+os.environ['PATH'],
                        'FIXTURE_CONFIG': str(config)}
    def value(name):
        try: return (led/name).read_text().strip()
        except FileNotFoundError: return ''
    def wait_for(predicate):
        for _ in range(150):
            if predicate(): return
            time.sleep(0.02)
        raise AssertionError('LED state transition timed out')
    write_config(state='Active')
    process = subprocess.Popen(['sh', str(source)], env=env)
    try:
        wait_for(lambda: value('trigger')=='timer' and value('delay_on')=='500'
                 and value('delay_off')=='500')
        write_config(state='Disabled')
        wait_for(lambda: value('trigger')=='none' and value('brightness')=='0')
        write_config(trigger='default-on', state='Active')
        (led/'trigger').write_text('default-on\n')
        time.sleep(0.4)
        assert value('trigger')=='default-on', 'Owner trigger overridden'
    finally:
        process.terminate(); process.wait(timeout=5)
    assert value('trigger')=='default-on', 'Stop clobbered owner trigger'
    write_config(state='Active')
    process = subprocess.Popen(['sh', str(source)], env=env)
    try:
        wait_for(lambda: value('trigger')=='timer')
    finally:
        process.terminate(); process.wait(timeout=5)
    assert value('trigger')=='none' and value('brightness')=='0'
print('WPS active/cancel, owner trigger precedence and clean stop passed')
