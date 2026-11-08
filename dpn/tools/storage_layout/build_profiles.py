#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stage layout4 thin FIPs and separate SquashFS. No device/Flash access.

These development outputs are NOT factory-Web or sysupgrade release packages.
The original bootloader consumes the same three-component FIT structure, while
Linux mounts its real root from UBI. Dummy filesystem bytes satisfy that original
container structure and are never used as the operating system root.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tools/generic-ram'))
from public_fip import build as fip
from audit import cpio_files
import gzip
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel-output',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--build-id',default='generic-layout4-development-v1');a=p.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',a.build_id):p.error('Invalid build ID')
    k=a.kernel_output.resolve();root=a.root.resolve();out=a.output.resolve()
    manifest=json.loads((k/'manifest.json').read_text());audit=json.loads((k/'content-audit.json').read_text())
    assert manifest['experimental_layout_v4_tools'] and audit['private_key_and_authentication_scan_passed']
    assert hashlib.sha256((k/'Image').read_bytes()).hexdigest()==audit['Image_SHA256']
    import lzma
    assert lzma.decompress((k/'Image.lzma').read_bytes(),format=lzma.FORMAT_ALONE)==(k/'Image').read_bytes(), 'Compressed kernel mismatch'
    files=cpio_files(gzip.decompress((k/'initramfs.cpio.gz').read_bytes()))
    for name in ['init','lib/upgrade/dpn-layout4-boot.sh','lib/upgrade/dpn-vault-recovery.sh']:
        assert files[name][1]==(R/'tools/generic-ram/overlay'/name).read_bytes(),('stale embedded source',name)
    assert not out.exists();out.mkdir(parents=True)
    wrapper=str(R/'tools/with_openwrt_env.sh');host=R/'openwrt/staging_dir/host/bin'
    epoch=str(manifest['source_epoch'])
    def run(*args,cwd=None):return subprocess.check_output([wrapper,*map(str,args)],cwd=cwd,env=os.environ|{'SOURCE_DATE_EPOCH':epoch})
    (root/'etc/dpn-build-id').write_text(a.build_id+'\n');(root/'etc/dpn-upgrade-layout').write_text('4\n')
    def sq(src,dst):
        env=os.environ.copy();env.pop('SOURCE_DATE_EPOCH',None)
        result=subprocess.check_output([wrapper,'env','-u','SOURCE_DATE_EPOCH',str(host/'mksquashfs4'),str(src),str(dst),'-noappend','-all-root','-comp','xz','-b','262144','-processors','4','-mkfs-time',epoch,'-all-time',epoch],env=env)
        (out/(dst.name+'.log')).write_bytes(result)
    sq(root,out/'rootfs.squashfs')
    dummy=out/'dummy-root';dummy.mkdir();(dummy/'LAYOUT4_CONTAINER_ONLY').write_text('Actual OpenWrt root is UBI static rootfs.\n');sq(dummy,out/'container-only.squashfs')
    rootsha=hashlib.sha256((out/'rootfs.squashfs').read_bytes()).hexdigest()
    shutil.copy2(k/'Image.lzma',out/'Image.lzma')
    profiles={}
    for role in ['normal','recovery']:
        dt=out/(role+'.dtb');shutil.copy2(k/'board.dtb',dt)
        compatible=run('fdtget',dt,'/','compatible').decode().strip().split()
        # The existing core/controller outer gate also controls ECC write
        # preparation. Layout4's narrower range policy remains authoritative.
        compatible=list(dict.fromkeys(['dlink,dpn-be7200gr','dlink,dpn-be7200gr-layout4','dlink,dpn-be7200gr-install','dlink,dpn-be7200gr-persist',*compatible]))
        run('fdtput','-t','s',dt,'/','compatible',*compatible)
        actual=run('fdtget',dt,'/','compatible').decode().split()
        assert actual[0]=='dlink,dpn-be7200gr' and 'dlink,dpn-be7200gr-persist' in actual
        # No legacy root/CFG metadata may select the old boot path.
        nodes=run('fdtget','-l',dt,'/').decode().splitlines()
        if 'dpn-flash-layout' in nodes:run('fdtput','-r',dt,'/dpn-flash-layout')
        run('fdtput','-c',dt,'/dpn-layout4')
        for name,value in [('format-version',4),('normal-slot',0),('recovery-slot',1),('vault-size',0x400000)]:run('fdtput','-t','x',dt,'/dpn-layout4',name,format(value,'x'))
        run('fdtput','-t','s',dt,'/dpn-layout4','write-profile',role)
        run('fdtput','-t','bx',dt,'/dpn-layout4','rootfs-sha256',*[rootsha[i:i+2] for i in range(0,64,2)])
        its='''/dts-v1/; / { description="DPN-BE7200GR layout4 development thin Linux"; #address-cells=<1>;
images {
 fdt@1 { data=/incbin/("ROLE.dtb"); type="flat_dt"; arch="arm64"; compression="none"; load=<0x8d000000>; hash@1 { algo="sha1"; }; };
 kernel@1 { data=/incbin/("Image.lzma"); type="kernel"; arch="arm64"; os="linux"; compression="lzma"; load=<0x8b000000>; entry=<0x8b000000>; hash@1 { algo="sha1"; }; };
 filesystem@1 { data=/incbin/("container-only.squashfs"); type="filesystem"; arch="arm64"; os="linux"; compression="none"; hash@1 { algo="sha1"; }; };
}; configurations { default="conf@1"; conf@1 { kernel="kernel@1"; fdt="fdt@1"; }; }; };'''.replace('ROLE',role)
        (out/(role+'.its')).write_text(its)
        result=run(host/'mkimage','-f',role+'.its',role+'.itb',cwd=out);(out/(role+'-mkimage.log')).write_bytes(result)
        blob=fip((out/(role+'.itb')).read_bytes());assert len(blob)<=0x1000000
        (out/(role+'.fip')).write_bytes(blob)
        profiles[role]={'bytes':len(blob),'SHA256':hashlib.sha256(blob).hexdigest(),'physical_start':0x80000 if role=='normal' else 0x3280000,'maximum_bytes':0x1000000}
    (out/'manifest.json').write_text(json.dumps({'layout':4,'profiles':profiles,'data_bytes':0x19800000,'UBI_rootfs_SHA256':rootsha,'vault_private_input_embedded':False,'calibration_or_MAC_embedded':False,'hardware_tested':False,'sysupgrade_backend_not_yet_qualified':True,'public_release_qualified':False},indent=2)+'\n')
    print('LAYOUT4_THIN_FIPS_AND_SEPARATE_UBI_ROOTFS_STAGED_NO_DEVICE_OPERATION')
if __name__=='__main__':main()
