#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Continue a completed clean base build into audited candidate containers.
No upload or flash operation. Hardware qualification remains separate.
"""
import argparse,json,subprocess,os
from pathlib import Path
R=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-id',required=True);a=p.parse_args()
assert json.loads((R/'CLEAN-BASE-STATUS.json').read_text())['base_build_passed']
def run(args):subprocess.run([str(R/'tools/with_openwrt_env.sh'),*map(str,args)],cwd=R,check=True)
run(['python3',R/'tools/release/build_clean_helpers.py'])
run(['python3',R/'tools/generic-ram/build.py','--persistent','--firmware-dir',R/'build/public-firmware'])
run(['python3',R/'tools/generic-ram/pack-persistent.py','--build-id',a.build_id])
run(['python3',R/'tools/generic-ram/audit-persistent.py',R/'build/generic-persistent/output'])
run(['bash',R/'tools/first-install/build-writer.sh','host'])
for slot in [0,1]:
    subprocess.run([str(R/'tools/with_openwrt_env.sh'),'python3',str(R/'tools/first-install/test-writer.py')],cwd=R,env=os.environ|{'DPN_TEST_SLOT':str(slot)},check=True)
run(['python3',R/'tools/generic-ram/test-first-boot.py'])
run(['python3',R/'tools/generic-ram/test-recovery-firewall.py'])
run(['python3',R/'tools/generic-ram/test-owner-upgrade-keys.py'])
run(['python3',R/'tools/first-install/test-stock-layout.py'])
run(['python3',R/'tools/release/test_source_stage.py'])
run(['python3',R/'tools/release/package_formats.py','--artifacts',R/'build/generic-persistent/output','--output',R/'dist/clean-candidate','--format','both'])
print('CLEAN_CANDIDATE_ASSEMBLED; public_release_qualified remains false')
