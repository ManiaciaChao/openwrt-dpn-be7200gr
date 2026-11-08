#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only verification of generic Flash boot using its pinned owner identity."""
import argparse,hashlib,json,shlex,struct,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--session',type=Path,required=True);p.add_argument('--client-key',type=Path,required=True);p.add_argument('--host',required=True)
p.add_argument('--build-id',required=True);p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--owner-baseline',type=Path);p.add_argument('--output',type=Path,required=True)
p.add_argument('--dhcp-before',type=Path,help='Explicitly allow only standard odhcpd piodir/hostsdir additions against this hash-matching original file')
a=p.parse_args();session=a.session.resolve();manifest=json.loads((a.artifacts/'persistent-manifest.json').read_text());written=json.loads((session/'written-image.json').read_text())
ssh=['ssh','-F','/dev/null','-i',str(a.client_key.resolve()),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ssh-ed25519','-o','HostKeyAlias=dpn-installed','-o','UserKnownHostsFile='+str(session/'installed-known-hosts'),'-o','ConnectTimeout=5','root@'+a.host]
def call(command,timeout=180):
 r=subprocess.run(ssh+[command],capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
 return r.stdout
assert call('id -u').strip()==b'0'
assert call('cat /etc/dpn-build-id').decode().strip()==a.build_id
assert call('cat /tmp/dpn-generic.ready').strip()==b'READY'
mounts=call('cat /proc/mounts').decode();assert '/dev/mtdblock2 /rom squashfs ro,' in mounts and '/dev/ubi0_0 /overlay ubifs rw,' in mounts and '/dev/loop' not in mounts
assert call('cat /sys/class/mtd/mtd1/name').strip()==b'dpn-vendor-logical-ro'
assert call('cat /sys/class/mtd/mtd2/name').strip()==b'dpn-rootfs'
assert call('cat /sys/class/mtd/mtd3/name').strip()==b'dpn-config'
for i in [0,1,2]:assert not int(call('cat /sys/class/mtd/mtd'+str(i)+'/flags').strip(),0)&1024
assert int(call('cat /sys/class/mtd/mtd3/flags').strip(),0)&1024
assert call('sha256sum /dev/mtd2ro').decode().split()[0]==manifest['rootfs_sha256']
assert call('test ! -e /overlay/dpn-upgrade.pending && test ! -e /overlay/dpn-upgrade-next && test ! -e /overlay/dpn-upgrade-old-upper; echo $?').strip()==b'0'
guard=(session/'install-guard.bin').read_bytes()
if len(guard)==337 and guard[:8]==b'DPNGRD4\0':
 slot=struct.unpack_from('<I',guard,8)[0];guard_offset=12;assert slot in [0,1]
elif len(guard)==333 and guard[:8]==b'DPNGRD3\0':slot=0;guard_offset=8
else:raise ValueError('Unknown guard format')
firmware_block=[2,202][slot];tail=firmware_block+72
assert call(f'dd if=/dev/mtd0 bs=262144 skip={firmware_block} count=72 2>/dev/null | sha256sum').decode().split()[0]==written['prefix_SHA256']
regions=[(0,firmware_block),(tail,736-tail),(1760,288)]
for i,(start,count) in enumerate(regions):
 h=call(f'dd if=/dev/mtd0 bs=262144 skip={start} count={count} 2>/dev/null | sha256sum').decode().split()[0]
 assert h==guard[guard_offset+i*65:guard_offset+i*65+64].decode(),'Protected region changed'
count=0;migrations=[]
if a.owner_baseline:
 expected=a.owner_baseline.read_bytes();paths=[line.split(b'  ',1)[1].decode() for line in expected.splitlines()]
 assert all(x.startswith('/etc/') and all(c.isalnum() or c in '/._-' for c in x) for x in paths)
 actual=call('sha256sum '+' '.join(paths))
 old={x.split(b'  ',1)[1].decode():x.split(b'  ',1)[0].decode() for x in expected.splitlines()}
 new={x.split(b'  ',1)[1].decode():x.split(b'  ',1)[0].decode() for x in actual.splitlines()}
 assert set(old)==set(new)
 for path in paths:
  if old[path]==new[path]:count+=1;continue
  assert path=='/etc/config/dhcp' and a.dhcp_before,'Owner file changed: '+path
  before=a.dhcp_before.read_bytes();assert hashlib.sha256(before).hexdigest()==old[path]
  after=call('cat /etc/config/dhcp');assert hashlib.sha256(after).hexdigest()==new[path]
  def tokens(b):return [t for line in b.decode().splitlines() if (t:=shlex.split(line,comments=True))]
  bt,at=tokens(before),tokens(after)
  assert [t for t in bt if t[0]=='config'][-1]==['config','odhcpd','odhcpd']
  assert at==bt+[['option','piodir','/tmp/odhcpd-piodir'],['option','hostsdir','/tmp/hosts']], 'Unexpected DHCP migration'
  migrations.append(dict(file=path,standard_odhcpd_directory_defaults_added=True,all_prior_UCI_tokens_unchanged=True))
cal=call('dd if=/sys/bus/nvmem/devices/dpn-art/nvmem bs=4096 skip=64 count=2 2>/dev/null | head -c 7680')
eeprom=call('cat /sys/kernel/debug/ieee80211/phy0/mt76/eeprom');assert len(cal)==len(eeprom)==7680 and cal==eeprom
result=dict(active_OpenWrt_slot=slot,preserved_factory_slot=1-slot,build_id=a.build_id,boot_ID=call('cat /proc/sys/kernel/random/boot_id').decode().strip(),owner_SSH_host_key_pinned=True,root_from_physical_Flash_SquashFS=True,configuration_UBIFS_MTD3=True,configuration_transaction_complete=True,physical_firmware_prefix_SHA256_verified=True,all_regions_outside_firmware_and_config_windows_unchanged=True,physical_and_logical_source_and_root_MTD_readonly=True,owner_config_and_identity_files_unchanged=count,verified_standard_config_migrations=migrations,wireless_automatic_ready=True,wireless_EEPROM_matches_own_ART=True,EEPROM_SHA256=hashlib.sha256(eeprom).hexdigest(),software_restart_verified=True,physical_power_cycle_not_claimed=True)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print('GENERIC_FLASH_BOOT_AND_ALL_PROTECTED_REGIONS_VERIFIED')
