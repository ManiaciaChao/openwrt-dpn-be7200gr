#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build layout4 standard sysupgrade tar+fwtool metadata, never upload."""
import argparse,hashlib,io,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--build-id',required=True);a=p.parse_args()
    manifest=json.loads((a.profile/'manifest.json').read_text());assert manifest['layout']==4
    fip=(a.profile/'normal.fip').read_bytes();root=(a.profile/'rootfs.squashfs').read_bytes()
    assert len(fip)<=0x1000000 and hashlib.sha256(fip).hexdigest()==manifest['profiles']['normal']['SHA256'] and hashlib.sha256(root).hexdigest()==manifest['UBI_rootfs_SHA256']
    a.output.mkdir(parents=True,exist_ok=False);image=a.output/'dpn-be7200gr-sysupgrade.bin'
    control=b'BOARD=dlink_dpn-be7200gr\nDPN_UPGRADE_LAYOUT=4\nPAYLOAD=thin-fip-and-ubi-root\n'
    with tarfile.open(image,'w',format=tarfile.USTAR_FORMAT) as tar:
        for name,b in [('CONTROL',control),('kernel',fip),('root',root)]:
            m=tarfile.TarInfo('sysupgrade-dpn-be7200gr/'+name);m.size=len(b);m.mode=0o644;m.mtime=0;tar.addfile(m,io.BytesIO(b))
    meta={'metadata_version':'1.1','compat_version':'1.0','supported_devices':['dlink,dpn-be7200gr'],'version':{'dist':'OpenWrt','version':a.build_id,'revision':'development','target':'airoha/an7581','board':'dlink_dpn-be7200gr'}}
    (a.output/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    subprocess.run([str(R/'openwrt/staging_dir/host/bin/fwtool'),'-I',str(a.output/'metadata.json'),str(image)],check=True)
    b=image.read_bytes();sha=hashlib.sha256(b).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps({'layout':4,'build_id':a.build_id,'bytes':len(b),'SHA256':sha,'normal_FIP_SHA256':hashlib.sha256(fip).hexdigest(),'rootfs_SHA256':hashlib.sha256(root).hexdigest(),'standard_tar_and_fwtool_metadata':True,'only_for_already_installed_layout4':True,'factory_first_install':False,'public_release_qualified':False},indent=2)+'\n')
    (a.output/'SHA256SUMS').write_text(sha+'  '+image.name+'\n')
    print('LAYOUT4_STANDARD_SYSUPGRADE_TAR_AND_FWTOOL_METADATA_PACKAGED_NO_DEVICE_WRITE')
if __name__=='__main__':main()
