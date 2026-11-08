#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Authenticated stock -> generic RAM preparation. No flash writes.
The caller supplies credentials, a pinned stock host key and the owner's public
key. Per-session host keys are generated on the target, never in public images.
"""
from pathlib import Path
from stock_layout import find_art
import argparse,base64,getpass,hashlib,json,os,re,secrets,shlex,subprocess,sys
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('phase',choices=['prepare','load','schedule','check'])
ap.add_argument('--stock-host',required=True);ap.add_argument('--stock-port',type=int,default=22022)
ap.add_argument('--known-hosts',type=Path,required=True);ap.add_argument('--stock-host-alias',default='dpn-stock')
ap.add_argument('--password-file',type=Path);ap.add_argument('--public-key',type=Path)
ap.add_argument('--artifacts',type=Path,required=True);ap.add_argument('--session',type=Path,required=True)
ap.add_argument('--ram-interface',required=True);ap.add_argument('--client-key',type=Path)
ap.add_argument('--profile', choices=['recovery', 'installer', 'persistent-trial'], default='recovery',
                help='Installer permits bounded MTD views only after explicit module loading; does not write Flash')
a=ap.parse_args();assert 1<=a.stock_port<=65535
assert re.fullmatch(r'[A-Za-z0-9_.:%-]+',a.stock_host) and re.fullmatch(r'[A-Za-z0-9_.-]+',a.ram_interface)
S=a.session.resolve();S.mkdir(mode=0o700,parents=True,exist_ok=True);assert S.stat().st_uid==os.getuid() and not S.stat().st_mode&0o077
statefile=S/'state.json';state=json.loads(statefile.read_text()) if statefile.exists() else {}
def save():statefile.write_text(json.dumps(state,indent=2)+'\n');statefile.chmod(0o600)
def digest(b):return hashlib.sha256(b).hexdigest()
def stock(cmd,data=None,timeout=90):
 pw=a.password_file.read_text().rstrip('\n') if a.password_file else getpass.getpass('Stock root password: ')
 secret=S/'.stock-password';secret.write_text(pw);secret.chmod(0o600)
 helper=S/'.askpass';helper.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nimport sys\nsys.stdout.write(Path('+repr(str(secret))+').read_text())\n');helper.chmod(0o700)
 args=['ssh','-F','/dev/null','-o','BatchMode=no','-o','NumberOfPasswordPrompts=1','-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(a.known_hosts.resolve()),'-o','HostKeyAlias='+a.stock_host_alias,'-o','HostKeyAlgorithms=ssh-ed25519','-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','-p',str(a.stock_port),'root@'+a.stock_host,cmd]
 env=os.environ|{'SSH_ASKPASS':str(helper),'SSH_ASKPASS_REQUIRE':'force','DISPLAY':':dpn-install'}
 try:
  r=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,start_new_session=True,timeout=timeout)
  if r.returncode:raise RuntimeError('Stock SSH command failed: '+r.stderr.decode(errors='replace'))
  return r.stdout
 finally:secret.unlink(missing_ok=True);helper.unlink(missing_ok=True)
def ram(cmd,timeout=15):
 args=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ssh-ed25519','-o','HostKeyAlias=dpn-session-ram','-o','UserKnownHostsFile='+str(S/'known-hosts'),'-o','ConnectTimeout=5']
 if a.client_key:args+=['-i',str(a.client_key),'-o','IdentitiesOnly=yes']
 r=subprocess.run(args+['root@'+state['ram_host'],cmd],capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
 return r.stdout
if a.phase=='prepare':
 assert not state,'Existing session; do not replace its host identity'
 assert a.public_key and a.public_key.is_file()
 pub=a.public_key.read_bytes();assert pub.startswith(b'ssh-ed25519 ') and len(pub.splitlines())==1
 blob=base64.b64decode(pub.split()[1],validate=True);assert len(blob)==51 and blob[:19]==b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20'
 manifest=json.loads((a.artifacts/'manifest.json').read_text())['files']
 dtb={'recovery':'board.dtb','installer':'installer.dtb','persistent-trial':'persistent-ram-root.dtb'}[a.profile]
 assets=['Image',dtb,'kexec-aarch64','mk-session-initrd','ram-launch']
 if a.profile=='persistent-trial':assets+=['rootfs-overlay.cpio']
 for name in assets:
  p=a.artifacts/name;assert p.is_file() and digest(p.read_bytes())==manifest[name]['sha256'],name
 art=find_art(stock('cat /proc/mtd'))
 out=stock('id -u; uname -r; cat /sys/kernel/kexec_loaded; cat /etc/build_info; printf \"\\n\"; for v in name offset size writesize erasesize oobsize; do printf \"ART_%s=\" \"$v\"; cat /sys/class/mtd/mtd13/$v; done; printf \"MAC=\"; dd if=/dev/mtd13 bs=4096 skip=769 count=1 2>/dev/null | dd bs=1 skip=85 count=17 2>/dev/null; printf \"\\n\"'.replace('mtd13',art)).decode().splitlines()
 assert out[:3]==['0','5.4.55','0'],out[:3]
 assert any('PROFILE=lan_10G_4port_7581_config_dlink_singtel' in x for x in out)
 assert all(v in out for v in ['ART_name=art','ART_offset=466092032','ART_size=3670016','ART_writesize=4096','ART_erasesize=262144','ART_oobsize=128']),'Unsupported vendor ART geometry'
 # The stock kernel exposes 128 user-spare bytes; the modern physical view
 # independently verifies the full 256-byte OOB and exact chip before writes.
 mac=out[-1].removeprefix('MAC=').lower();assert re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',mac)
 b=bytearray.fromhex(mac.replace(':',''));assert b[0]&1==0 and any(b);b[0]^=2;ll=b[:3]+b'\xff\xfe'+b[3:]
 ramhost='fe80::'+':'.join(f'{int.from_bytes(ll[i:i+2],"big"):x}' for i in range(0,8,2))+'%'+a.ram_interface
 nonce=secrets.token_hex(16);remote='/tmp/dpn-install-'+nonce;stock('umask 077; mkdir '+remote)
 for name in assets:
  p=a.artifacts/name;stock('umask 077; cat > '+remote+'/'+name,p.read_bytes())
 stock('cat > '+remote+'/owner.pub',pub)
 got=stock('sha256sum '+' '.join(remote+'/'+name for name in assets)).decode()
 for name in assets:assert manifest[name]['sha256']+'  '+remote+'/'+name in got
 keys=stock('chmod 700 '+remote+'/kexec-aarch64 '+remote+'/mk-session-initrd; /usr/sbin/dropbearkey -t ed25519 -f '+remote+'/host-key; '+remote+'/mk-session-initrd '+remote+'/owner.pub '+remote+'/host-key '+nonce+' > '+remote+'/session.cpio; chmod 600 '+remote+'/session.cpio; /usr/sbin/dropbearkey -y -f '+remote+'/host-key').decode()
 key=re.findall(r'^ssh-ed25519 [A-Za-z0-9+/=]+',keys,re.M);assert key
 if a.profile=='persistent-trial':stock('umask 077; cat '+remote+'/session.cpio '+remote+'/rootfs-overlay.cpio > '+remote+'/boot.cpio')
 p=S/'known-hosts';p.write_text('dpn-session-ram '+key[-1]+'\n');p.chmod(0o600)
 state=dict(nonce=nonce,remote=remote,ram_host=ramhost,factory_mac=mac,host_public_key=key[-1],asset_SHA256={n:manifest[n]['sha256'] for n in assets},profile=a.profile,dtb=dtb,initrd='boot.cpio' if a.profile=='persistent-trial' else 'session.cpio',prepared=True,flash_writes=0);save()
 print('SESSION_PREPARED; fresh host identity generated on target; no Flash writes')
elif a.phase=='load':
 assert state.get('prepared') and not state.get('loaded');d=state['remote']
 out=stock(d+'/kexec-aarch64 -y -c -l '+d+'/Image --dtb='+d+'/'+state.get('dtb','board.dtb')+' --initrd='+d+'/'+state.get('initrd','session.cpio')+' --append='+shlex.quote('console=ttyS0,115200n8 earlycon loglevel=7 rdinit=/init')+' --mem-min=0x8b000000 --mem-max=0x97ffffff; echo LOAD_STATUS=$?; cat /sys/kernel/kexec_loaded',timeout=90).decode()
 (S/'load.txt').write_text(out);assert 'LOAD_STATUS=0\n1\n' in out,out
 state['loaded']=True;save();print('RAM_IMAGE_LOADED; kernel accepted image, DTB and session initrd')
elif a.phase=='schedule':
 assert state.get('loaded') and not state.get('scheduled');d=state['remote']
 # The caller must restore the original disabled Dropbear setting through its
 # authenticated web interface. If that has not happened, the job aborts.
 script='''#!/bin/sh
sleep 60
if pidof dropbear >/dev/null; then echo ABORT_SERVICE_STILL_ENABLED; exit 1; fi
set -e
sync
for p in /extcfg /extcfg_backup /um_ext; do mount -o remount,ro "$p"; done
sync
echo DPN_KEXEC_EXECUTE
exec "'''+d+'''/kexec-aarch64" -y -e
'''
 stock('cat > '+d+'/execute.sh',script.encode());stock('chmod 700 '+d+'/execute.sh '+d+'/ram-launch; '+d+'/ram-launch '+d+'/execute.sh '+d+'/execute-detached.log')
 state['scheduled']=True;save();print('RAM_EXECUTION_SCHEDULED; restore stock Dropbear OFF within 60 seconds; otherwise aborts')
else:
 assert state.get('profile')!='persistent-trial','Existing-config trial retains the owner host identity; validate with its original pinned key, not the temporary RAM key'
 out=ram('cat /tmp/dpn-session; cat /tmp/dpn-generic.ready; uname -r; id -u; cat /sys/class/net/br-lan/address; cat /proc/mtd').decode()
 assert out.startswith(state['nonce']+'\nREADY\n6.18.60\n0\n'+state['factory_mac']+'\n'),out
 (S/'RAM-proof.txt').write_text(out);state['RAM_verified']=True;save();print('GENERIC_RAM_VERIFIED; session, pinned new host key, UID0 and own factory MAC match')
