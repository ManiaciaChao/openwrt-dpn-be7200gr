#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Audit actual layout4 SquashFS and DTBs, without device access."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();manifest=json.loads((a.profile/'manifest.json').read_text())
    assert hashlib.sha256((a.profile/'rootfs.squashfs').read_bytes()).hexdigest()==manifest['UBI_rootfs_SHA256']
    with tempfile.TemporaryDirectory() as tmp:
        dest=Path(tmp)/'root';subprocess.run([str(R/'tools/with_openwrt_env.sh'),str(R/'openwrt/staging_dir/host/bin/unsquashfs4'),'-no-progress','-d',str(dest),str(a.profile/'rootfs.squashfs')],check=True,stdout=subprocess.DEVNULL)
        issues=[];count=0
        for f in dest.rglob('*'):
            if not f.is_file() or f.is_symlink():continue
            name=f.relative_to(dest).as_posix();b=f.read_bytes();count+=1
            if name.startswith(('root/.ssh/','etc/dpn-provision/')) and b:issues.append((name,'owner provisioning'))
            if name.startswith('etc/dropbear/') and ('host_key' in name or name.endswith('authorized_keys')) and b:issues.append((name,'SSH identity'))
            if re.search(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----\r?\n(?:(?:Proc-Type|DEK-Info):[^\n]*\r?\n)*\r?\n?[A-Za-z0-9+/=]{16}',b):issues.append((name,'private key'))
        rootpw=next(l.split(':')[1] for l in (dest/'etc/shadow').read_text().splitlines() if l.startswith('root:'));assert rootpw in ['!','*']
        assert not (dest/'etc/config/wireless').read_bytes().strip()
        assert (dest/'etc/dpn-upgrade-layout').read_text().strip()=='4'
        for role in ['normal','recovery']:
            dt=(a.profile/(role+'.dtb')).read_bytes();assert b'local-mac-address\0' not in dt and b'mediatek,eeprom-data\0' not in dt
        assert not issues,issues
        for tool in ['dpn-normal16-write','dpn-image4-check']:
            assert (dest/'usr/libexec'/tool).read_bytes()==(R/'build/storage-layout'/tool).read_bytes(),tool
    report={'layout':4,'actual_SquashFS_extracted_and_scanned':True,'regular_files_inspected':count,'private_SSH_identity_and_owner_provisioning_absent':True,'root_password_locked':True,'radio_AP_configuration_empty':True,'DT_no_inline_calibration_or_MAC':True,'actual_native_tools_match_current_build':True,'rootfs_SHA256':manifest['UBI_rootfs_SHA256'],'hardware_boot_not_implied':True,'public_release_qualified':False}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print('LAYOUT4_ACTUAL_SQUASHFS_PRIVACY_AND_NATIVE_TOOL_CONTENT_AUDIT_PASSED')
if __name__=='__main__':main()
