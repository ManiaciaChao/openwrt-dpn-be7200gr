#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build generic RAM recovery from public sources; no factory dump input."""
from pathlib import Path
import argparse,datetime,hashlib,json,lzma,os,re,shutil,struct,subprocess
R=Path(__file__).resolve().parents[2];ap=argparse.ArgumentParser();ap.add_argument('--firmware-dir',type=Path,required=True);ap.add_argument('--reuse-root',action='store_true');ap.add_argument('--persistent',action='store_true',help='Build a wired early root; full userspace remains available for SquashFS packing');ap.add_argument('--development-kexec',action='store_true',help='Enable kexec_file_load for an explicitly selected development kernel');ap.add_argument('--stock-return-tools',action='store_true',help='Include experimental dedicated stock-return userspace tool; no automatic writes');ap.add_argument('--layout-v4-tools',action='store_true',help='Include experimental recovery-vault checker, no private vault input');ap.add_argument('--development-kexec-legacy',action='store_true',help='Laboratory DTB handoff only; requires --development-kexec');a=ap.parse_args();assert not a.development_kexec_legacy or a.development_kexec
B=R/('build/generic-persistent' if a.persistent else 'build/generic-ram');O=B/'output';ROOT=B/'root';K=next((R/'openwrt/build_dir').glob('target-aarch64*/linux-airoha_an7581/linux-6.18.*')).resolve();C=R/'tools/generic-ram'
assert not ROOT.exists() or a.reuse_root,'Candidate root exists; inspect before rebuilding'
B.mkdir(parents=True,exist_ok=True);O.mkdir(exist_ok=True)
(O/'content-audit.json').unlink(missing_ok=True)
if not ROOT.exists():shutil.copytree(R/'openwrt/build_dir/target-aarch64_cortex-a53_musl/root-airoha',ROOT,symlinks=True)
# Remove all owner authentication and laboratory configuration from the package
# root. No private file is opened or copied by this builder.
for name in ['etc/dropbear','root/.ssh']:
 p=ROOT/name
 if p.exists():shutil.rmtree(p)
(ROOT/'etc/dropbear').mkdir(mode=0o700)
for pattern in ['etc/init.d/dpn*','etc/rc.d/*dpn*','etc/uci-defaults/*dpn*','usr/libexec/dpn*']:
 for p in ROOT.glob(pattern):p.unlink()
(ROOT/'etc/config/wireless').write_text('')
(ROOT/'etc/config/system').write_text("config system\n option hostname 'OpenWrt'\n option timezone 'UTC'\n")
p=ROOT/'etc/shadow';lines=p.read_text().splitlines();lines=['root:!:0:0:99999:7:::' if x.startswith('root:') else x for x in lines];p.write_text('\n'.join(lines)+'\n')
for src in (C/'overlay').rglob('*'):
 if src.is_dir():continue
 dst=ROOT/src.relative_to(C/'overlay');dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists() or dst.is_symlink():dst.unlink()
 shutil.copy2(src,dst)
for name in ['dpn_factory_ready','dpn_wifi_ram','dpn_led_status','dpn_generic_ready']:
 n={'dpn_factory_ready':'17','dpn_wifi_ram':'18','dpn_led_status':'97','dpn_generic_ready':'99'}[name]
 p=ROOT/'etc/rc.d'/('S'+n+name)
 if p.is_symlink() or p.exists():p.unlink()
 p.symlink_to('../init.d/'+name)
(ROOT/'etc/modules.d/mt7996e').write_text('')
if a.layout_v4_tools:
 for tool in ['dpn-vault-check','dpn-image4-check','dpn-normal16-write','dpn-bootflag-select','dpn-factory-read','dpn-provision-recovery','dpn-expanded-stock-return']:
  shutil.copy2(R/'build/storage-layout'/tool,ROOT/'usr/libexec'/tool)
else:
 (ROOT/'usr/libexec/dpn-vault-check').unlink(missing_ok=True)
if a.stock_return_tools:
 shutil.copy2(R/'build/stock-return/dpn-stock-return',ROOT/'usr/libexec/dpn-stock-return')
else:
 (ROOT/'usr/libexec/dpn-stock-return').unlink(missing_ok=True)
firmware=json.loads((R/'artifacts/offload/firmware-source.json').read_text())
for entry in firmware['files']:
 if entry['path'].startswith('airoha/en7581_'):
  src=a.firmware_dir/Path(entry['path']).name;assert hashlib.sha256(src.read_bytes()).hexdigest()==entry['sha256']
  dst=ROOT/'lib/firmware'/entry['path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
shutil.copy2(a.firmware_dir/'LICENSE.airoha',O/'LICENSE.airoha')
(O/'firmware-source.json').write_text(json.dumps(firmware,indent=2)+'\n')
# Keep the entry point in a relative cpio list to avoid host/user build paths.
rel=lambda p:os.path.relpath(p,K)
(B/'init-cpio-list').write_text('file /init '+rel(C/'overlay/init')+' 0755 0 0\n')
config=(R/'configs/generic-kernel.config').read_text()
if a.development_kexec:
 assert '# CONFIG_KEXEC_FILE is not set' in config
 config=config.replace('# CONFIG_KEXEC_FILE is not set','CONFIG_KEXEC_FILE=y')
if a.development_kexec_legacy:
 assert '# CONFIG_SUSPEND is not set' in config
 # arm64 legacy handoff depends on PM_SLEEP_SMP; laboratory kernel only.
 config=config.replace('# CONFIG_SUSPEND is not set','CONFIG_SUSPEND=y')
 config+='\nCONFIG_KEXEC=y\n'
config=config.replace('@DPN_ROOT@',rel(ROOT)).replace('@DPN_CPIO@',rel(B/'init-cpio-list')).replace('@OPENWRT_INITRAMFS_BASE@',rel(R/'openwrt/target/linux/generic/image/initramfs-base-files.txt'))
config=config.replace(str(R/'build/final-ram/root'),rel(ROOT)).replace(str(K)+'.init-cpio-list',rel(B/'init-cpio-list')).replace(str(R/'openwrt/target/linux/generic/image/initramfs-base-files.txt'),rel(R/'openwrt/target/linux/generic/image/initramfs-base-files.txt'))
config=config.replace('# CONFIG_DEVTMPFS is not set','CONFIG_DEVTMPFS=y\nCONFIG_DEVTMPFS_MOUNT=y')
config=config.replace('# CONFIG_MTD_PARTITIONED_MASTER is not set','CONFIG_MTD_PARTITIONED_MASTER=y')
config=re.sub(r'CONFIG_INITRAMFS_ROOT_UID=\d+', 'CONFIG_INITRAMFS_ROOT_UID=-1', config)
config=re.sub(r'CONFIG_INITRAMFS_ROOT_GID=\d+', 'CONFIG_INITRAMFS_ROOT_GID=-1', config)
config=config.replace('# CONFIG_BLK_DEV_LOOP is not set','CONFIG_BLK_DEV_LOOP=y')
if a.persistent:config=config.replace(rel(ROOT),rel(B/'early-root'))
# Set reproducible build identity instead of embedding the host login name.
epoch=subprocess.check_output(['git','-C',str(R/'openwrt'),'log','-1','--format=%ct'],text=True).strip()
timestamp=datetime.datetime.fromtimestamp(int(epoch),datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
(ROOT/'etc/dpn-build-epoch').write_text(epoch+'\n')
env=os.environ|{'KBUILD_BUILD_USER':'openwrt','KBUILD_BUILD_HOST':'buildhost','KBUILD_BUILD_TIMESTAMP':timestamp,'SOURCE_DATE_EPOCH':epoch,'KBUILD_BUILD_VERSION':'0'}
cross=str(R/'openwrt/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-');wrapper=str(R/'tools/with_openwrt_env.sh')
files=[K/n for n in ['.config','drivers/phy/airoha/phy-airoha-pcie.c','drivers/mtd/nand/spi/core.c','drivers/mtd/nand/spi/foresee.c','drivers/spi/spi-airoha-snfi.c']];saved={p:p.read_bytes() for p in files}
def run(args,log,cwd=None):
 with (B/log).open('w') as f:subprocess.run(args,cwd=cwd,env=env,check=True,stdout=f,stderr=subprocess.STDOUT)
headers=[K/'include/linux/mtd'/n for n in ['dpn_persist_guard.h','dpn_upgrade_guard.h','dpn_expand_guard.h','dpn_install_guard.h','dpn_slot_policy.h','dpn_stock_return_policy.h','dpn_layout4_policy.h']]
saved_headers={p:p.read_bytes() if p.exists() else None for p in headers}
try:
 (K/'.config').write_text(config)
 for name in ['dpn_persist_guard.h','dpn_upgrade_guard.h','dpn_expand_guard.h']:
  shutil.copy2(R/'drafts/nand'/name,K/'include/linux/mtd'/name)
 shutil.copy2(C/'kernel/dpn_install_guard.h',K/'include/linux/mtd/dpn_install_guard.h')
 shutil.copy2(C/'kernel/dpn_slot_policy.h',K/'include/linux/mtd/dpn_slot_policy.h')
 shutil.copy2(C/'kernel/dpn_stock_return_policy.h',K/'include/linux/mtd/dpn_stock_return_policy.h')
 shutil.copy2(C/'kernel/dpn_layout4_policy.h',K/'include/linux/mtd/dpn_layout4_policy.h')
 for name in ['953-phy-airoha-ram-clear-fll-load.patch','956-dpn-nand-ro-core.patch','957-dpn-nand-ro-foresee.patch','958-dpn-nand-ro-spi-airoha-snfi.patch','959-dpn-bounded-config-core.patch','960-dpn-bounded-config-controller.patch','961-dpn-upgrade-core.patch','962-dpn-upgrade-controller.patch','963-dpn-expand-core.patch','964-dpn-expand-controller.patch']:
  subprocess.run(['patch','-p1','--forward','-i',str(R/'drafts/kernel-patches'/name)],cwd=K,check=True,stdout=subprocess.DEVNULL)
 for name in ['drivers/mtd/nand/spi/core.c','drivers/spi/spi-airoha-snfi.c']:
  p=K/name;p.write_text(p.read_text().replace('dpn_expand_guard.h','dpn_install_guard.h'))
 run([wrapper,'make','-C',str(K),'ARCH=arm64','CROSS_COMPILE='+cross,'olddefconfig','modules_prepare'],'prepare.log')
 if a.development_kexec:
  actual=(K/'.config').read_text()
  assert 'CONFIG_KEXEC_FILE=y\n' in actual, 'Development kexec_file_load was dropped by Kconfig'
  if a.development_kexec_legacy:assert 'CONFIG_KEXEC=y\n' in actual, 'Laboratory DTB handoff support was dropped by Kconfig'
 run([wrapper,'make','-C',str(K),'M='+str(C/'kernel'),'ARCH=arm64','CROSS_COMPILE='+cross,'-j8','modules'],'module.log')
 # Use the pinned upstream OpenWrt driver, not a userspace GPIO polling daemon.
 buttons=B/'gpio-button-hotplug';buttons.mkdir(exist_ok=True)
 for name in ['Makefile','gpio-button-hotplug.c']:
  shutil.copy2(R/'openwrt/package/kernel/gpio-button-hotplug/src'/name,buttons/name)
 run([wrapper,'make','-C',str(K),'M='+str(buttons.resolve()),'ARCH=arm64','CROSS_COMPILE='+cross,'modules'],'button-module.log')
 shutil.copy2(buttons/'gpio-button-hotplug.ko',ROOT/'lib/modules/6.18.60/gpio-button-hotplug.ko')
 (ROOT/'etc/modules.d/30-gpio-button-hotplug').write_text('gpio-button-hotplug\n')
 for name in ['dpn_bmt_art.ko','dpn_storage.ko','dpn_stock_return.ko','dpn_layout4_storage.ko']:shutil.copy2(C/'kernel'/name,ROOT/'lib/modules/6.18.60'/name)
 subprocess.run([cross+'strip','--strip-debug',str(ROOT/'lib/modules/6.18.60/dpn_bmt_art.ko')],check=True)
 if a.persistent:
  early=B/'early-root';shutil.rmtree(early,ignore_errors=True);shutil.copytree(ROOT,early,symlinks=True)
  shutil.rmtree(early/'lib/firmware/mediatek',ignore_errors=True)
  for pattern in ['mt*.ko','mac80211.ko','cfg80211.ko']:
   for p in (early/'lib/modules/6.18.60').glob(pattern):p.unlink()
  for name in ['www','usr/share/ucode/luci','usr/share/rpcd/ucode','usr/lib/ucode/luci']:
   shutil.rmtree(early/name,ignore_errors=True)
  for pattern in ['*rpcd','*uhttpd','*ucitrack','*dpn_wifi_ram']:
   for p in (early/'etc/rc.d').glob(pattern):p.unlink()
  shutil.copy2(R/'build/generic-ram/output/dpn-install',early/'usr/libexec/dpn-install')
 shutil.copy2(K/'.config',O/'kernel.config')
 run([wrapper,'make','-C',str(K),'ARCH=arm64','CROSS_COMPILE='+cross,'-j8','Image'],'kernel.log')
 shutil.copy2(K/'arch/arm64/boot/Image',O/'Image')
 shutil.copy2(K/'usr/initramfs_inc_data',O/'initramfs.cpio.gz')
finally:
 for p,data in saved.items():p.write_bytes(data)
 for p,data in saved_headers.items():
  if data is None:p.unlink(missing_ok=True)
  else:p.write_bytes(data)
image=(O/'Image').read_bytes();extent=struct.unpack_from('<Q',image,16)[0];assert len(image)<=extent<0x2000000
(O/'Image.lzma').write_bytes(lzma.compress(image,format=lzma.FORMAT_ALONE,preset=6))
dtc=Path(shutil.which('dtc') or '/missing-required-dtc').parent;env['PATH']=str(dtc)+':'+env['PATH']
pre=subprocess.check_output([cross+'gcc','-E','-nostdinc','-undef','-D__DTS__','-x','assembler-with-cpp','-I',str(K/'include'),'-I',str(R/'openwrt/target/linux/airoha/dts'),str(C/'board.dts')],text=True)
pre=pre.replace('/dts-v1/;','/dts-v1/;\n/memreserve/ 0x98000000 0x08000000;\n',1);(B/'board.preprocessed.dts').write_text(pre)
run([str(dtc/'dtc'),'-I','dts','-O','dtb','-o',str(O/'board.dtb'),str(B/'board.preprocessed.dts')],'dtc.log')
its='''/dts-v1/;
/ { description="DPN-BE7200GR generic read-only RAM recovery"; #address-cells=<1>;
 images {
  fdt@1 { data=/incbin/("board.dtb"); type="flat_dt"; arch="arm64"; compression="none"; load=<0x8d000000>; hash@1 { algo="sha256"; }; };
  kernel@1 { data=/incbin/("Image.lzma"); type="kernel"; arch="arm64"; os="linux"; compression="lzma"; load=<0x8b000000>; entry=<0x8b000000>; hash@1 { algo="sha256"; }; };
 };
 configurations { default="conf@1"; conf@1 { kernel="kernel@1"; fdt="fdt@1"; }; };
};'''
(O/'recovery.its').write_text(its)
run([str(R/'openwrt/staging_dir/host/bin/mkimage'),'-f',str(O/'recovery.its'),str(O/'initramfs-recovery.itb')],'mkimage.log',cwd=O)
# An explicitly selected installer DT enables bounded write callbacks only
# after the owner loads dpn_storage install=1. Recovery DT remains read-only.
installer=(C/'board.dts').read_text()+"""
/ {
 model = "D-Link DPN-BE7200GR (generic RAM installer)";
 compatible = "dlink,dpn-be7200gr", "dlink,dpn-be7200gr-ram", "dlink,dpn-be7200gr-install", "dlink,dpn-be7200gr-persist", "dlink,dpn-be7200gr-upgrade", "dlink,dpn-be7200gr-expand", "airoha,an7581", "airoha,en7581";
 dpn-flash-layout { format-version=<1>; upgrade-layout=<3>; config-bank=<2>; config-start=<0xb800000>; config-size=<0x10000000>; ram-install; };
};
"""
(B/'installer.dts').write_text(installer)
pre=subprocess.check_output([cross+'gcc','-E','-nostdinc','-undef','-D__DTS__','-x','assembler-with-cpp','-I',str(K/'include'),'-I',str(R/'openwrt/target/linux/airoha/dts'),str(B/'installer.dts')],text=True)
pre=pre.replace('/dts-v1/;','/dts-v1/;\n/memreserve/ 0x98000000 0x08000000;\n',1);(B/'installer.preprocessed.dts').write_text(pre)
run([str(dtc/'dtc'),'-I','dts','-O','dtb','-o',str(O/'installer.dtb'),str(B/'installer.preprocessed.dts')],'installer-dtc.log')
(O/'installer.its').write_text(its.replace('board.dtb','installer.dtb').replace('read-only RAM recovery','bounded RAM installer'))
run([str(R/'openwrt/staging_dir/host/bin/mkimage'),'-f',str(O/'installer.its'),str(O/'initramfs-installer.itb')],'installer-mkimage.log',cwd=O)
manifest={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in O.iterdir() if p.is_file() and p.name!='manifest.json'}
(O/'manifest.json').write_text(json.dumps(dict(files=manifest,development_kexec_file_load=a.development_kexec,development_kexec_legacy_DTB_handoff=a.development_kexec_legacy,experimental_stock_return_tool=a.stock_return_tools,experimental_layout_v4_tools=a.layout_v4_tools,capabilities={"slot_aware_readonly_root":1,"readonly_network_recovery":1,"slot_aware_update":1,"factory_first_boot":1},private_input_required=False,inline_calibration=False,fixed_MAC=False,embedded_SSH_credentials=False,profiles={'recovery':{'DTB':'board.dtb','flash_write_enabled':False},'installer':{'DTB':'installer.dtb','automatic_flash_write':False,'explicit_storage_module_required':True,'allowed_write_windows':[[0x80000,0x1280000],[0xb800000,0x1b800000]]}},kernel_image_extent=extent,source_epoch=env['SOURCE_DATE_EPOCH']),indent=2)+'\n')
print('GENERIC_RAM_BUILD_COMPLETE; candidate output remains staged for content audit')
