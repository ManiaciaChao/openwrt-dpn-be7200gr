#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Filesystem initialization with real target UCI/Dropbear under QEMU, no NAND."""
from pathlib import Path
import tempfile,subprocess,os,shutil,json,re
R=Path(__file__).resolve().parents[2];root=R/'build/generic-persistent/root'
qemu=os.environ.get('QEMU_AARCH64') or shutil.which('qemu-aarch64')
assert qemu, 'Run tests inside the pinned build environment'
helper=R/'tools/generic-ram/overlay/lib/upgrade/dpn-first-boot.sh';commit=helper.with_name('dpn-config-commit.sh')
with tempfile.TemporaryDirectory(prefix='dpn-fresh-config-test-') as td:
 t=Path(td);b=t/'bin';b.mkdir();rom=t/'rom';(rom/'etc/config').mkdir(parents=True)
 for name in ['network','dhcp','dropbear','firewall']:shutil.copy2(R/'tools/generic-ram/overlay/etc/config'/name,rom/'etc/config'/name)
 for name,text in {'shadow':'root:!:0:0:99999:7:::\n','passwd':'root:x:0:0:root:/root:/bin/ash\n','group':'root:x:0:\n','shells':'/bin/ash\n'}.items():(rom/'etc'/name).write_text(text)
 for name,target in [('uci',root/'sbin/uci'),('dropbearkey',root/'usr/bin/dropbearkey')]:
  p=b/name;extra=' -t '+str(t/'uci-delta') if name=='uci' else '';p.write_text('#!/bin/sh\nexec '+str(qemu)+' -L '+str(root)+' '+str(target)+extra+' "$@"\n');p.chmod(0o755)
 (t/'uci-delta').mkdir();(b/'sync').write_text('#!/bin/sh\nexit 0\n');(b/'sync').chmod(0o755)
 env=os.environ|{'PATH':str(b)+':'+os.environ['PATH']};pub=[]
 for i in range(2):
  cfg=t/f'cfg{i}';cfg.mkdir()
  subprocess.run(['sh','-c','. "$1"; . "$2"; dpn_fresh_configuration "$3" "$4"','fresh',str(commit),str(helper),str(rom),str(cfg)],env=env,check=True,capture_output=True)
  upper=cfg/'upper';assert (upper/'etc/shadow').read_text().startswith('root::');assert (upper/'etc/dpn-first-setup').exists();assert (cfg/'.fs_state').readlink()==Path('2');assert not (cfg/'dpn-upgrade.pending').exists()
  for key,value in [('network.lan.proto','static'),('network.lan.ipaddr','192.168.1.1'),('network.wan.proto','none'),('dhcp.lan.ignore','0'),('dhcp.@dnsmasq[0].port','53'),('dropbear.@dropbear[0].PasswordAuth','off')]:
   out=subprocess.check_output([str(b/'uci'),'-c',str(upper/'etc/config'),'get',key],env=env).decode().strip();assert out==value,(key,out)
  key=upper/'etc/dropbear/dropbear_ed25519_host_key';assert key.stat().st_mode&0o777==0o600
  out=subprocess.check_output([str(b/'dropbearkey'),'-y','-f',str(key)],env=env).decode();pub.append(re.search(r'^ssh-ed25519 \S+',out,re.M)[0])
  # A non-empty active configuration must not be replaced by first-setup logic.
  before=(upper/'etc/shadow').read_bytes();r=subprocess.run(['sh','-c','. "$1"; . "$2"; dpn_fresh_configuration "$3" "$4"','fresh',str(commit),str(helper),str(rom),str(cfg)],env=env,capture_output=True);assert r.returncode and (upper/'etc/shadow').read_bytes()==before
 assert pub[0]!=pub[1]
print('FRESH_CONFIG_TARGET_UCI_UNIQUE_TARGET_KEYS_LAN_SETUP_AND_EXISTING_CONFIG_REFUSAL_PASS; filesystem-only test, no NAND')
