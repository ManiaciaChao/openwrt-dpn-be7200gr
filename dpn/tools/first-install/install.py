#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Guarded first installation from a pinned, verified generic RAM session.
Separate phases deliberately prevent automatic retry of firmware programming.
Only fresh all-FF config banks or verified prior expanded installations qualify.
"""
import argparse,hashlib,json,re,shlex,time
from pathlib import Path
from transport import RAM
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('phase',choices=['preflight','stage-config','finish-config-stage','write-firmware','verify-firmware','commit-config','rollback-firmware'])
p.add_argument('--session',type=Path,required=True);p.add_argument('--client-key',type=Path,required=True)
p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--mode',choices=['fresh','migrate'],required=True)
p.add_argument('--development-image',action='store_true',help='Explicitly allow a locally built, not release-qualified development candidate')
a=p.parse_args();session=a.session.resolve();r=RAM(session,a.client_key)
assert r.state.get('RAM_verified') and r.state.get('profile')=='installer','Requires a verified installer RAM session'
assert r.call('cat /tmp/dpn-session').decode().strip()==r.state['nonce'],'Wrong RAM session'
manifest=json.loads((a.artifacts/'persistent-manifest.json').read_text())
assert manifest['layout']==3 and (manifest['public_release_qualified'] or a.development_image),'Not a release-qualified image'
journal=session/'install.json';state=json.loads(journal.read_text()) if journal.exists() else {}
nonce=r.state['nonce'];remote='/tmp/dpn-first-'+nonce
if state:
 assert state['nonce']==nonce and state['mode']==a.mode and state['payload_SHA256']==manifest['files']['generic-persistent.itb']['sha256'],'Installation journal does not match these inputs'

def save():
 with journal.open('w') as f:journal.chmod(0o600);json.dump(state,f,indent=2);f.write('\n')
def call(command,timeout=600):
 out=r.call(command,timeout=timeout)
 return out.decode(errors='strict')
def backups():
 for mode,size in [('ecc',536870912),('raw',570425344)]:
  receipt=json.loads((session/('nand-'+mode+'-backup-verified.json')).read_text())
  source=json.loads((session/('nand-'+mode+'-backup.json')).read_text())
  assert receipt['session_nonce']==nonce and receipt['mode']==mode and receipt['plaintext_bytes']==size
  assert receipt['age_decryption_verified'] and not receipt['plaintext_written_to_disk']
  digest=hashlib.sha256()
  with Path(source['encrypted_file']).open('rb') as f:
   while block:=f.read(1024*1024):digest.update(block)
  assert digest.hexdigest()==receipt['encrypted_SHA256']==source['encrypted_SHA256'],'NAND backup changed'

tool=remote+'/dpn-install';fit=remote+'/generic-persistent.itb';guard=remote+'/guard.bin';fip=remote+'/target.fip';config=remote+'/first-install-configure.sh'
previous=remote+'/previous-prefix.bin'
def program_job(label,arguments,marker):
 script=remote+'/'+label+'.sh';status=remote+'/'+label+'.status';log=remote+'/'+label+'.log'
 body='#!/bin/sh\n'+shlex.join([tool,*arguments])+'\nrc=$?\nprintf "%s\\n" "$rc" > '+status+'.new\nmv '+status+'.new '+status+'\nexit "$rc"\n'
 r.call('umask 077; cat > '+script,body.encode());call('chmod 700 '+script+'; '+remote+'/ram-launch '+script+' '+log)
 deadline=time.monotonic()+900
 while time.monotonic()<deadline:
  result=call('if test -f '+status+'; then cat '+status+'; else echo RUNNING; fi',timeout=20).strip()
  if result!='RUNNING':
   output=call('cat '+log,timeout=30)
   path=session/('install-'+label+'.txt');path.write_text(output);path.chmod(0o600)
   assert result=='0' and marker in output,'Programming job failed; remain in RAM, inspect log, never retry automatically'
   return output
  time.sleep(2)
 raise TimeoutError('Programming status unknown; do not restart or retry; inspect the independent target job')
if a.phase=='preflight':
 assert not state,'An installation journal already exists; inspect it, do not retry blindly'
 backups()
 expected={}
 for name in ['dpn-install','generic-persistent.itb','first-install-configure.sh','ram-launch']:
  data=(a.artifacts/name).read_bytes();entry=manifest['files'][name]
  assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],name
  expected[name]=entry['sha256']
 state=dict(nonce=nonce,mode=a.mode,remote=remote,payload_SHA256=expected['generic-persistent.itb'],preflight_started=True,firmware_write_started=False);save()
 call('umask 077; mkdir '+remote)
 for name in expected:
  data=(a.artifacts/name).read_bytes();r.call('umask 077; cat > '+remote+'/'+name,data)
 sums=call('sha256sum '+' '.join(remote+'/'+n for n in expected))
 for name,h in expected.items():assert h+'  '+remote+'/'+name in sums
 call('chmod 700 '+tool+' '+config+' '+remote+'/ram-launch')
 call(tool+' --check-fit '+fit)
 out=call('set -e; test ! -e /sys/class/mtd/mtd2; insmod /lib/modules/6.18.60/dpn_storage.ko install=1; test "$(cat /sys/class/mtd/mtd2/name)" = dpn-firmware-update; test "$(cat /sys/class/mtd/mtd3/name)" = dpn-config; for i in 2 3; do test "$(cat /sys/class/mtd/mtd$i/dev)" = "90:$((i*2))"; test -c /dev/mtd$i || mknod /dev/mtd$i c 90 "$((i*2))"; chmod 600 /dev/mtd$i; done')
 out+=call(tool+' --snapshot '+guard)
 private=r.call('cat '+guard);target=session/'install-guard.bin';target.write_bytes(private);target.chmod(0o600)
 out+=call('umask 077; dd if=/dev/mtd0 of='+previous+' bs=262144 skip=2 count=72 2>/dev/null; '+tool+' --check-restore '+previous+' '+guard)
 if a.mode=='fresh':out+=call(tool+' --check-config-blank')
 else:out+=call(tool+' --probe-current '+guard)
 out+=call(tool+' --assemble-fit '+fit+' '+guard+' '+fip)
 log=session/'install-preflight.txt';log.write_text(out);log.chmod(0o600)
 state['preflight_complete']=True;save();print('FIRST_INSTALL_PREFLIGHT_COMPLETE; no firmware/config programming')
elif a.phase in ['stage-config','finish-config-stage']:
 assert state.get('preflight_complete') and not state.get('firmware_write_started') and not state.get('config_staged') and state['mode']==a.mode
 if a.phase=='stage-config':
  assert not state.get('config_staging_started')
  state['config_staging_started']=True;save();operation=a.mode
 else:
  assert state.get('config_staging_started')
  # Recover an already validated, nonce-tagged copy without extracting it or
  # touching firmware again. Updating this helper is explicit and hash checked.
  data=(a.artifacts/'first-install-configure.sh').read_bytes();want=manifest['files']['first-install-configure.sh']['sha256']
  assert hashlib.sha256(data).hexdigest()==want
  r.call('umask 077; cat > '+config+'.new',data)
  assert call('sha256sum '+config+'.new').startswith(want+' ')
  call('chmod 700 '+config+'.new; mv '+config+'.new '+config)
  state['configuration_helper_recovery_SHA256']=want;save();operation='finish'
 out=call(config+' '+operation+' '+guard+' '+tool)
 assert 'DPN_FIRST_CONFIG_'+operation+'_COMPLETE' in out
 key=re.findall(r'^ssh-ed25519 [A-Za-z0-9+/=]+',out,re.M);assert len(key)==1,'No unique retained/generated SSH public identity'
 file=session/'installed-known-hosts';file.write_text('dpn-installed '+key[0]+'\n');file.chmod(0o600)
 state['installed_host_public_key']=key[0];state['config_staged']=True;save();print('FIRST_INSTALL_CONFIG_STAGED; firmware not programmed, existing upper not replaced')
elif a.phase=='write-firmware':
 assert state.get('config_staged') and not state.get('firmware_write_started') and state['mode']==a.mode
 # Persist this BEFORE invoking the programmer. Any disconnect/failure requires
 # inspection and recovery, never an automatic repeated erase/program cycle.
 state['firmware_write_started']=True;save()
 out=program_job('write',['--write',fip,guard],'DPN_INSTALL_WRITE_COMPLETE_PROTECTED_REGIONS_UNCHANGED')
 state['firmware_written_and_verified']=True;save();print('FIRST_INSTALL_FIRMWARE_WRITTEN_AND_ECC_VERIFIED; original bootloader/backup/ART guarded')
elif a.phase=='verify-firmware':
 assert state.get('firmware_write_started') and not state.get('rollback_started')
 assert call('if test -f '+remote+'/write.status; then cat '+remote+'/write.status; else echo RUNNING; fi').strip()!='RUNNING','Wait for the existing target job; never launch a second programmer'
 out=call(tool+' --verify-written '+fip+' '+guard)
 assert 'DPN_INSTALLED_PREFIX_ECC_AND_PROTECTION_VERIFIED' in out
 state['firmware_written_and_verified']=True;save();print('FIRST_INSTALL_EXISTING_WRITE_VERIFIED; no programming repeated')
elif a.phase=='rollback-firmware':
 assert state.get('firmware_write_started') and not state.get('rollback_started')
 assert call('if test -f '+remote+'/write.status; then cat '+remote+'/write.status; else echo RUNNING; fi').strip()!='RUNNING','Wait for the original programmer before an explicit rollback'
 state['rollback_started']=True;save()
 program_job('rollback',['--restore-prefix',previous,guard],'DPN_PREVIOUS_PREFIX_RESTORED_AND_PROTECTED')
 call(config+' rollback '+guard+' '+tool)
 state['previous_firmware_restored']=True;save();print('PREVIOUS_FIRMWARE_RESTORED; original config upper retained; safe to sync and restart')
else:
 assert state.get('firmware_written_and_verified') and not state.get('config_committed') and state['mode']==a.mode
 out=call(tool+' --verify-written '+fip+' '+guard)
 assert 'DPN_INSTALLED_PREFIX_ECC_AND_PROTECTION_VERIFIED' in out
 out+=call(config+' commit '+guard+' '+tool)
 assert 'DPN_FIRST_CONFIG_commit_COMPLETE' in out
 state['config_committed']=True;save();print('FIRST_INSTALL_COMMITTED; safe to sync and restart after checking this journal')
