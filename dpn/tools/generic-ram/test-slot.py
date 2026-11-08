#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check slot root bounds, ambiguous bootargs, and unchanged write permissions."""
from pathlib import Path
import subprocess,tempfile
R=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temp:
 binary=str(Path(temp)/'slot-test')
 subprocess.run([str(R/'tools/with_openwrt_env.sh'),'cc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(R/'tools/generic-ram/test_slot.c'),'-o',binary],check=True)
 subprocess.run([binary],check=True)
for cmd,expected in [('bootflag=0 root=/dev/mtdblock3',b'0'),('root=/dev/mtdblock6 ro bootflag=1',b'1'),('root=/dev/mtdblock6 bootflag=0',None),('root=/dev/mtdblock3 bootflag=0 bootflag=0',None),('root=/dev/mtdblock3 root=/dev/mtdblock3 bootflag=0',None),('bootflag=2 root=/dev/mtdblock6',None),('root=/dev/mtdblock3',None),('bootflag=0',None)]:
 p=subprocess.run(['sh','-c','. "$1"; dpn_boot_slot "$2"','slot-test',str(R/'tools/generic-ram/overlay/lib/upgrade/dpn-boot-slot.sh'),cmd],capture_output=True)
 assert (p.returncode==0 and p.stdout.strip()==expected) if expected is not None else p.returncode!=0
print('SLOT_ROOT_BOUNDS_BOOTARGS_AND_BACKUP_WRITE_REFUSAL_PASS')
