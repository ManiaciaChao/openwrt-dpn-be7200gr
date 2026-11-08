#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Create a reviewable source snapshot from an explicit allowlist, not a workspace copy.
The result is a prototype requiring a prepared OpenWrt build, not a release.
Never follows symlinks, copies binaries, stages credentials, or contacts a remote.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess
from check_source_stage import audit
R=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
if a.output.exists():p.error('Use a new stage directory')
files=['LICENSE-STATUS.md','LICENSES/GPL-2.0-only.txt','LICENSES/MIT.txt','Makefile','.gitignore','.gitattributes','README.md','docs/clean-build.md','docs/generic-first-install.md','docs/release-and-upstream.md','docs/stock-web-upgrade-analysis.md','docs/factory-web-and-recovery.md','configs/release-helper-sources.json','configs/release-sources.json','configs/release-base.config','configs/build-host.json','configs/generic-kernel.config','configs/luci-apk-inputs.json','configs/apk-repositories.list','tools/with_openwrt_env.sh','tools/openwrt-shell.nix','tools/nand_readonly_dump.c','tools/ummtk.py','tools/test_ummtk.py','tools/audit_stock_web_upgrade.py','tools/stock_web_offline_harness.c','artifacts/offload/firmware-source.json','artifacts/stock-web-upgrade/public-validation-summary.json']
for path in sorted((R/'tools/first-install').glob('*')):
 if path.suffix in ['.py','.c','.sh']:files.append(str(path.relative_to(R)))
for path in sorted((R/'tools/generic-ram').rglob('*')):
 if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts and (path.suffix in ['.py','.sh','.dts','.c','.h'] and not path.name.endswith('.mod.c') or path.name=='Makefile' or 'overlay' in path.parts):files.append(str(path.relative_to(R)))
for path in sorted((R/'tools/release').glob('*.py')):files.append(str(path.relative_to(R)))
for path in sorted((R/'drafts/nand').glob('*.h')):files.append(str(path.relative_to(R)))
for n in [953,956,957,958,959,960,961,962,963,964]:
 files.extend(str(path.relative_to(R)) for path in (R/'drafts/kernel-patches').glob(str(n)+'-*.patch'))
files.extend(str(p.relative_to(R)) for p in (R/'LICENSES/third-party').glob('*') if p.is_file())
files.extend(str(p.relative_to(R)) for p in (R/'tools/release/bootstrap').glob('*') if p.is_file())
# Public layout4 implementation only. Laboratory orchestration and receipts
# deliberately remain outside the export.
storage_sources = [
 'vault.py','vault_check.c','native_io.h','image4.h','image4_check.c',
 'normal16_write.c','bootflag_select.c','expanded_stock_return.c',
 'provision_recovery.c','factory_read.c','build_profiles.py','package_layout4.py','audit_profile.py',
 'build-vault-check.sh','build-image4-check.sh','build-normal16.sh',
 'build-bootflag.sh','build-provisioner.sh','build-expanded-return.sh',
 'build-factory-read.sh','test_vault.py','native_vault_test.py',
 'test_factory_read.py','test_config_permissions.py','test_normal16.py',
 'test_provisioner.py','test_bootflag.py','test_expanded_return.py',
]
files.extend('tools/storage_layout/'+n for n in storage_sources)
files.extend(['tools/stock_return/test_inspect_image.py','tools/stock_return/inspect_image.py','docs/storage-expansion.md','docs/stock-backup.md','docs/buttons.md'])
for n in ('local-standard-sysupgrade-v3.json','local-expanded-roundtrip-v2.json','local-final-coldboot-v1.json'):
 files.append('artifacts/storage-layout/'+n)
if (R/'artifacts/storage-layout/generic-factory-Web-and-sysupgrade-RC2.json').is_file():
 files.append('artifacts/storage-layout/generic-factory-Web-and-sysupgrade-RC2.json')
if (R/'artifacts/storage-layout/button-support-v1.json').is_file():
 files.append('artifacts/storage-layout/button-support-v1.json')
manifest={}
for name in sorted(set(files)):
 src=R/name
 if not src.is_file() or src.is_symlink():raise ValueError('Expected regular source: '+name)
 dst=a.output/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);manifest[name]=hashlib.sha256(src.read_bytes()).hexdigest()
ref=json.loads((R/'configs/release-sources.json').read_text())['openwrt']['revision']
(a.output/'SOURCE-MANIFEST.json').write_text(json.dumps({'OpenWrt_commit':ref,'source_snapshot_only':True,'clean_build_qualified':False,'public_binary_release_qualified':False,'files':manifest},indent=2)+'\n')
(a.output/'REPOSITORY-STATUS.md').write_text('''# Reviewed DPN source export

This allowlisted source tree excludes owner credentials, calibration dumps,
factory firmware/header copies, private vaults and research workspace history.
The layout4 implementation retains the original bootloader, compact SSH recovery
and per-device identity while allocating 408 MiB raw UBI space to OpenWrt.

Hardware qualification belongs to exact artifact hashes and de-identified
receipts; source privacy checks alone do not qualify binaries. Build from pinned
sources using docs/clean-build.md and read docs/generic-first-install.md before
installation. Private OEM backups stay external to this repository.
''')
findings=audit(a.output)
print(json.dumps({'stage':str(a.output),'files':len(manifest),'passed':not findings,'findings':findings,'remote_published':False},indent=2))
if findings:raise SystemExit(1)
