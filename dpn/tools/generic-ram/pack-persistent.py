#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Pack a generic FIT/SquashFS and sysupgrade bundle; never open factory dumps."""
from pathlib import Path
import argparse,hashlib,io,json,os,re,shutil,subprocess,tarfile
p=argparse.ArgumentParser(description=__doc__);p.add_argument("--build-id",default="generic-layout3-v1");p.add_argument("--recovery-self-test",action="store_true",help="Private lab image: intentionally enter the wired recovery branch; not a first-install or release image");args=p.parse_args()
if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}",args.build_id):p.error("Invalid build ID")
R=Path(__file__).resolve().parents[2];C=R/'tools/generic-ram';B=R/'build/generic-persistent';O=B/'output';root=B/'root'
for name in ['kexec-aarch64','mk-session-initrd','ram-launch','nand-reader','COPYING.kexec-tools']:
 shutil.copy2(R/'build/generic-ram/output'/name,O/name)
epoch=str(json.loads((O/'manifest.json').read_text())['source_epoch'])
dtc=Path(shutil.which('dtc') or '/missing-required-dtc').parent;env=os.environ|{'PATH':str(dtc)+':'+os.environ['PATH'],'SOURCE_DATE_EPOCH':epoch}
for p in (C/'overlay').rglob('*'):
 if p.is_file():
  q=root/p.relative_to(C/'overlay');q.parent.mkdir(parents=True,exist_ok=True);q.unlink(missing_ok=True);shutil.copy2(p,q)
shutil.copy2(R/'build/generic-ram/output/dpn-install',root/'usr/libexec/dpn-install')
shutil.copy2(R/'build/generic-ram/output/dpn-install',O/'dpn-install')
shutil.copy2(R/'tools/first-install/configure.sh',O/'first-install-configure.sh')
(root/'etc/dpn-build-id').write_text(args.build_id+'\n');(root/'etc/dpn-upgrade-layout').write_text('3\n')
board=root/'etc/board.d/02_network';s=board.read_text();s=s.replace('dlink,dpn-be7200gr-ram)\n\t\t# Keep the first RAM experiment isolated until ports are verified.','dlink,dpn-be7200gr|\\\n\tdlink,dpn-be7200gr-ram)\n\t\tucidef_set_interfaces_lan_wan "ge4 ge3 ge2 ge1 lan10" "wan10"');board.write_text(s)
with (B/'squashfs.log').open('w') as log:
 subprocess.run([str(R/'openwrt/staging_dir/host/bin/mksquashfs4'),str(root),str(O/'rootfs.squashfs'),'-comp','xz','-b','262144','-noappend','-all-root','-no-xattrs','-processors','4','-mkfs-time',epoch,'-all-time',epoch],check=True,env={k:v for k,v in env.items() if k!='SOURCE_DATE_EPOCH'},stdout=log,stderr=subprocess.STDOUT)
fs=(O/'rootfs.squashfs').read_bytes();digest=hashlib.sha256(fs).hexdigest()
# Reuse only the publicly compiled, calibration-free board description.
shutil.copy2(O/'board.dtb',O/'persistent.dtb')
def put(name,typ,*values):
 subprocess.run([str(dtc/'fdtput'),'-t',typ,str(O/'persistent.dtb'),'/dpn-flash-layout',name,*values],check=True)
subprocess.run([str(dtc/'fdtput'),'-c',str(O/'persistent.dtb'),'/dpn-flash-layout'],check=True)
subprocess.run([str(dtc/'fdtput'),'-t','s',str(O/'persistent.dtb'),'/','model','D-Link DPN-BE7200GR (generic persistent OpenWrt)'],check=True)
subprocess.run([str(dtc/'fdtput'),'-t','s',str(O/'persistent.dtb'),'/','compatible','dlink,dpn-be7200gr','dlink,dpn-be7200gr-ram','dlink,dpn-be7200gr-install','dlink,dpn-be7200gr-persist','dlink,dpn-be7200gr-upgrade','dlink,dpn-be7200gr-expand','airoha,an7581','airoha,en7581'],check=True)
for n,v in [('format-version',1),('upgrade-layout',3),('config-bank',2),('config-start',0xb800000),('config-size',0x10000000),('rootfs-offset',0x100000),('rootfs-size',len(fs))]:put(n,'x',format(v,'x'))
put('rootfs-sha256','bx',*[digest[i:i+2] for i in range(0,64,2)])
subprocess.run([str(dtc/'fdtput'),str(O/'persistent.dtb'),'/dpn-flash-layout','persistent-root'],check=True)
if json.loads((O/'manifest.json').read_text()).get('capabilities',{}).get('slot_aware_readonly_root')==1:
 subprocess.run([str(dtc/'fdtput'),str(O/'persistent.dtb'),'/dpn-flash-layout','slot-relative-root'],check=True)
if json.loads((O/'manifest.json').read_text()).get('capabilities',{}).get('factory_first_boot')==1:
 subprocess.run([str(dtc/'fdtput'),str(O/'persistent.dtb'),'/dpn-flash-layout','factory-first-boot'],check=True)
if json.loads((O/'manifest.json').read_text()).get('capabilities',{}).get('readonly_network_recovery')==1:
 subprocess.run([str(dtc/'fdtput'),str(O/'persistent.dtb'),'/dpn-flash-layout','network-recovery-capable'],check=True)
 if args.recovery_self_test:
  subprocess.run([str(dtc/'fdtput'),str(O/'persistent.dtb'),'/dpn-flash-layout','network-recovery-self-test'],check=True)
elif args.recovery_self_test:raise ValueError('Kernel has no network recovery capability')
its='''/dts-v1/; / { description="Generic DPN-BE7200GR; original bootloader retained"; #address-cells=<1>; images {
 fdt@1 { data=/incbin/("persistent.dtb"); type="flat_dt"; arch="arm64"; compression="none"; load=<0x8d000000>; hash@1 { algo="sha1"; }; };
 kernel@1 { data=/incbin/("Image.lzma"); type="kernel"; arch="arm64"; os="linux"; compression="lzma"; load=<0x8b000000>; entry=<0x8b000000>; hash@1 { algo="sha1"; }; };
 filesystem@1 { data=/incbin/("rootfs.squashfs"); type="filesystem"; os="linux"; arch="arm64"; compression="none"; hash@1 { algo="sha1"; }; };
 }; configurations { default="conf@1"; conf@1 { kernel="kernel@1"; fdt="fdt@1"; }; }; };'''
(O/'persistent.its').write_text(its)
def pack():
 with (B/'persistent-mkimage.log').open('w') as log:subprocess.run([str(R/'openwrt/staging_dir/host/bin/mkimage'),'-f','persistent.its','generic-persistent.itb'],cwd=O,env=env,check=True,stdout=log,stderr=subprocess.STDOUT)
pack();blob=(O/'generic-persistent.itb').read_bytes();off=blob.index(fs);assert blob.find(fs,off+1)<0
put('rootfs-offset','x',format(0x80000+0x2100+off,'x'));pack();blob=(O/'generic-persistent.itb').read_bytes();assert blob.index(fs)==off
assert len(blob)+0x2100<=0x1200000,'Firmware exceeds the protected 18 MiB window'
shutil.copy2(O/'persistent.dtb',O/'persistent-ram-root.dtb')
subprocess.run([str(dtc/'fdtput'),str(O/'persistent-ram-root.dtb'),'/dpn-flash-layout','ram-root'],check=True)
subprocess.run(['python',str(C/'make-rootfs-overlay.py'),str(O/'rootfs.squashfs'),str(O/'rootfs-overlay.cpio')],check=True)
trial=its.replace('persistent.dtb','persistent-ram-root.dtb').replace('filesystem@1 { data=/incbin/("rootfs.squashfs"); type="filesystem";', 'ramdisk@1 { data=/incbin/("rootfs-overlay.cpio"); type="ramdisk"; load=<0x94000000>;').replace('fdt="fdt@1"; };','fdt="fdt@1"; ramdisk="ramdisk@1"; };')
(O/'persistent-ram-root.its').write_text(trial)
with (B/'ram-root-mkimage.log').open('w') as log:subprocess.run([str(R/'openwrt/staging_dir/host/bin/mkimage'),'-f','persistent-ram-root.its','persistent-ram-root.itb'],cwd=O,env=env,check=True,stdout=log,stderr=subprocess.STDOUT)
control=b'BOARD=dlink_dpn-be7200gr\nDPN_UPGRADE_LAYOUT=3\nPAYLOAD=generic-fit\n'
with tarfile.open(O/'generic-sysupgrade.bin','w',format=tarfile.USTAR_FORMAT) as archive:
 for name,data in [('CONTROL',control),('kernel',blob)]:
  info=tarfile.TarInfo('sysupgrade-dpn-be7200gr/'+name);info.size=len(data);info.mode=0o644;info.mtime=int(epoch);archive.addfile(info,io.BytesIO(data))
meta=dict(metadata_version='1.1',compat_version='1.0',supported_devices=['dlink,dpn-be7200gr'],version=dict(dist='OpenWrt',version=args.build_id,revision='development',target='airoha/an7581',board='dlink_dpn-be7200gr'))
(O/'sysupgrade-metadata.json').write_text(json.dumps(meta)+'\n')
subprocess.run([str(R/'openwrt/staging_dir/host/bin/fwtool'),'-I',str(O/'sysupgrade-metadata.json'),str(O/'generic-sysupgrade.bin')],check=True)
manifest=dict(development_recovery_self_test=args.recovery_self_test,layout=3,factory_wrapper_input_required=False,wrapper_assembled_on_each_target=True,firmware_bytes_including_target_wrapper=len(blob)+0x2100,firmware_limit=0x1200000,rootfs_physical_offset=0x80000+0x2100+off,rootfs_sha256=digest,bootloader_and_stock_backup_retained=True,public_release_qualified=False,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in O.iterdir() if p.is_file() and p.name not in ['persistent-manifest.json','manifest.json'] and not p.name.endswith('audit.json')})
(O/'persistent-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
general=json.loads((O/'manifest.json').read_text())
general['files']={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in O.iterdir() if p.is_file() and p.name!='manifest.json' and not p.name.endswith('audit.json')}
(O/'manifest.json').write_text(json.dumps(general,indent=2)+'\n')
print('GENERIC_PERSISTENT_CANDIDATE_PACKED',len(blob)+0x2100,'bytes; no device operation')
