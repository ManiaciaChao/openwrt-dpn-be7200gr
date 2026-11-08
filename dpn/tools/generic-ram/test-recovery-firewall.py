#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Actual target UCI under QEMU: RAM firewall binding, retained policy and refusal."""
from pathlib import Path
import hashlib,os,shutil,subprocess,tempfile
R=Path(__file__).resolve().parents[2];root=R/'build/generic-persistent/root';helper=R/'tools/generic-ram/overlay/lib/upgrade/dpn-recovery-firewall.sh';qemu=shutil.which('qemu-aarch64');assert qemu
with tempfile.TemporaryDirectory(prefix='dpn-recovery-fw-') as name:
 t=Path(name);bin=t/'bin';bin.mkdir();delta=t/'delta';delta.mkdir()
 uci=bin/'uci';uci.write_text('#!/bin/sh\nexec '+qemu+' -L '+str(root)+' '+str(root/'sbin/uci')+' -t '+str(delta)+' "$@"\n');uci.chmod(0o755);env=os.environ|{'PATH':str(bin)+':'+os.environ['PATH']}
 for device in ['br-ap','br-lan','br-lan.10']:
  cfg=t/device;cfg.mkdir();(cfg/'network').write_text("config interface 'lan'\n option device '"+device+"'\n option proto 'dhcp'\n")
  (cfg/'firewall').write_text("config defaults\n option input 'REJECT'\nconfig zone\n option name 'lan'\n list network 'lan'\n list network 'management'\n option input 'ACCEPT'\nconfig zone\n option name 'wan'\n list network 'wan'\n option input 'REJECT'\n")
  before=(cfg/'network').read_bytes();args=['sh','-c','. "$1"; dpn_recovery_bind_firewall "$2"','_',str(helper),str(cfg)];subprocess.run(args,env=env,check=True)
  once=(cfg/'firewall').read_bytes();subprocess.run(args,env=env,check=True);assert (cfg/'firewall').read_bytes()==once and (cfg/'network').read_bytes()==before
  value=subprocess.check_output([uci,'-c',cfg,'get','firewall.@zone[0].device'],env=env).decode().strip();assert value==device,(repr(value),device,once)
  assert subprocess.check_output([uci,'-c',cfg,'get','firewall.@zone[1].input'],env=env).strip()==b'REJECT'
  (cfg/'network').write_text("config interface 'lan'\n option device 'br ap'\n");bad=(cfg/'firewall').read_bytes();assert subprocess.run(args,env=env).returncode!=0 and (cfg/'firewall').read_bytes()==bad
print('TARGET_UCI_RECOVERY_DEVICE_BINDING_IDEMPOTENCE_NETWORK_UNCHANGED_WAN_POLICY_AND_INVALID_DEVICE_REFUSAL_PASS; filesystem only')
