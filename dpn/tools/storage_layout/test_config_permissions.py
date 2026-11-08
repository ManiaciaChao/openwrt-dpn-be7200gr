#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Regression: private umask must not make the overlay root non-traversable."""
import io,json,os,stat,subprocess,tarfile,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);data=p/'data';data.mkdir();backup=p/'backup.tar.gz';source=p/'functions.sh'
    # Only the external GNU tar pathname differs on the host. The production
    # restore function runs unchanged with the same restrictive caller umask.
    source.write_text((R/'tools/generic-ram/overlay/lib/upgrade/dpn-layout4-upgrade.sh').read_text().replace('/usr/libexec/tar-gnu','tar'))
    with tarfile.open(backup,'w:gz') as tar:
        for name,mode,b in [('etc/passwd',0o644,b'ubus:x:81:81:ubus:/var/run/ubus:/bin/false\n'),('etc/config/system',0o600,b'config system\n'),('etc/dropbear/authorized_keys',0o600,b'private-fixture-only\n')]:
            m=tarfile.TarInfo(name);m.mode=mode;m.uid=os.getuid();m.gid=os.getgid();m.size=len(b);tar.addfile(m,io.BytesIO(b))
    subprocess.run([str(R/'tools/with_openwrt_env.sh'),'sh','-c','umask 077; . "$1"; dpn_l4_restore_config "$2" "$3"','test',str(source),str(backup),str(data)],check=True)
    for n in ['upper','upper/etc','upper/etc/config','upper/etc/dropbear']:assert stat.S_IMODE((data/n).stat().st_mode)==0o755,n
    for n in ['upper/etc/config/system','upper/etc/dropbear/authorized_keys']:assert stat.S_IMODE((data/n).stat().st_mode)==0o600,n
    assert stat.S_IMODE((data/'work').stat().st_mode)==0o700 and os.readlink(data/'.fs_state')=='2'
print(json.dumps({'restrictive_caller_umask':'077','upper_root_and_implicit_parent_directories_traversable':True,'private_file_modes_preserved':True,'work_directory_private':True,'GNU_tar_compare_passed':True},indent=2))
