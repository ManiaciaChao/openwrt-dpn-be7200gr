#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the actual read-only selector across configuration commit states."""
from pathlib import Path
import tempfile,subprocess,hashlib,os
helper=Path(__file__).parent/'overlay/lib/upgrade/dpn-recovery-state.sh'
cases=[('committed',False,True,False,False,'upper'),('prepared',True,True,False,True,'upper'),('old-renamed',True,False,True,True,'dpn-upgrade-old-upper'),('new-renamed',True,True,True,False,'dpn-upgrade-old-upper'),('cleanup-before-marker',True,True,False,False,'upper'),('unexplained-staging',False,True,False,True,None),('unexplained-old',False,True,True,False,None),('no-intact-tree',True,False,False,True,None)]
for name,pending,upper,old,next_,expected in cases:
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)
  for present,n in [(upper,'upper'),(old,'dpn-upgrade-old-upper'),(next_,'dpn-upgrade-next')]:
   if present:(p/n).mkdir();(p/n/'owner').write_text('owner-state')
  if pending:(p/'dpn-upgrade.pending').write_text('v1\n')
  def snapshot():return {str(f.relative_to(p)):f.read_bytes() if f.is_file() else None for f in p.rglob('*')}
  before=snapshot();r=subprocess.run(['sh','-c','. "$1"; dpn_recovery_upper "$2"','selector',str(helper.resolve()),td],capture_output=True)
  assert ((r.returncode==0 and r.stdout.strip().decode()==expected) if expected else r.returncode!=0),name
  assert snapshot()==before,'Selector modified configuration'
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'upper').symlink_to('/');r=subprocess.run(['sh','-c','. "$1"; dpn_recovery_upper "$2"','selector',str(helper.resolve()),td],capture_output=True);assert r.returncode
print('READONLY_RECOVERY_CONFIG_COMMIT_STATES_AND_SYMLINK_REFUSAL_PASS')
