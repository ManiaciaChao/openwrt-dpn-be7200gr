#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Actual target host-key parser and GNU tar; no NAND or device access."""
from pathlib import Path
import tempfile,subprocess,shutil,os,tarfile
R=Path(__file__).resolve().parents[2];root=R/'build/generic-persistent/root';helper=R/'tools/generic-ram/overlay/lib/upgrade/dpn-generic-upgrade.sh'
qemu=shutil.which('qemu-aarch64');tar=shutil.which('tar');assert tar and qemu
with tempfile.TemporaryDirectory(prefix='dpn-owner-key-test-') as td:
 t=Path(td);keys=t/'keys';keys.mkdir();bin=t/'bin';bin.mkdir()
 exe=bin/'dropbearkey';exe.write_text('#!/bin/sh\nexec '+str(qemu)+' -L '+str(root)+' '+str(root/'usr/bin/dropbearkey')+' "$@"\n');exe.chmod(0o755);env=os.environ|{'PATH':str(bin)+':'+os.environ['PATH']}
 private=keys/'dropbear_ed25519_host_key';subprocess.run([str(exe),'-t','ed25519','-f',str(private)],check=True,capture_output=True,env=env)
 pub=subprocess.check_output([str(exe),'-y','-f',str(private)],env=env).decode();pub=next(x for x in pub.splitlines() if x.startswith('ssh-ed25519 '));auth=keys/'authorized_keys';auth.write_text(pub+'\n')
 def ready():return subprocess.run(['sh','-c','. "$1"; dpn_owner_recovery_keys_ready "$2"','test',str(helper),str(keys)],env=env,capture_output=True).returncode==0
 assert ready();auth.write_text('# no owner key\n');assert not ready();auth.write_text('# '+pub+'\n');assert not ready();auth.write_text(pub+'\n')
 b=private.read_bytes();private.write_text('not a host key');assert not ready();private.write_bytes(b)
 auth.unlink();auth.symlink_to(t/'missing');assert not ready();auth.unlink();auth.write_text(pub+'\n')
 def backup(name,omit=False,alter=False):
  stage=t/name;target=stage/'etc/dropbear';target.mkdir(parents=True);shutil.copy2(private,target/private.name)
  if not omit:(target/'authorized_keys').write_text('changed\n' if alter else auth.read_text())
  archive=t/(name+'.tgz')
  with tarfile.open(archive,'w:gz') as f:
   for p in target.iterdir():f.add(p,arcname=str(p.relative_to(stage)))
  return subprocess.run(['sh','-c','. "$1"; dpn_owner_backup_ready "$2" "$3" "$4"','test',str(helper),str(archive),str(keys),tar],env=env,capture_output=True).returncode==0
 assert backup('valid');assert not backup('missing',omit=True);assert not backup('altered',alter=True)
print('OWNER_KEYS_HOST_PARSER_SYMLINK_COMMENTS_AND_BACKUP_MISSING_OR_CHANGED_REFUSAL_PASS; no device access')
