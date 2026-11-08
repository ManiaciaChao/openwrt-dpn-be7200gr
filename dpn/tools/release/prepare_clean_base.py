#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare an isolated, pinned OpenWrt base build from a reviewed source export.
This builds the base root/toolchain only; it does not qualify release artifacts.
An optional local Git cache supplies commit objects, never its working files.
"""
import argparse, json, shutil, subprocess
from pathlib import Path
R = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
p.add_argument('--git-cache', type=Path)
p.add_argument('--download-cache', type=Path, help='Optional public source archive cache; OpenWrt verifies recipe hashes')
p.add_argument('--build', action='store_true')
p.add_argument('--jobs', type=int, default=8)
a = p.parse_args()
if a.output.exists() or a.output.is_symlink(): p.error('Output must not exist')
if not 1 <= a.jobs <= 64: p.error('jobs outside 1..64')
out = a.output.resolve()
if a.git_cache: a.git_cache = a.git_cache.resolve()
if a.download_cache:
    a.download_cache = a.download_cache.resolve()
    if not a.download_cache.is_dir(): p.error('Download cache must be a directory')
def run(argv, cwd=None): subprocess.run(list(map(str, argv)), cwd=cwd, check=True)
run(['python3', R/'tools/release/stage_source.py', out])
lock = json.loads((out/'configs/release-sources.json').read_text())
def checkout(spec, dest, cache=None):
    dest.mkdir(parents=True)
    run(['git', 'init', '-q', dest])
    run(['git', '-C', dest, 'remote', 'add', 'origin', spec['url']])
    source = cache if cache is not None and (cache/'.git').exists() else spec['url']
    run(['git', '-C', dest, 'fetch', '--depth=1', source, spec['revision']])
    run(['git', '-C', dest, 'checkout', '--detach', '-q', 'FETCH_HEAD'])
    actual = subprocess.check_output(['git', '-C', dest, 'rev-parse', 'HEAD'], text=True).strip()
    if actual != spec['revision']: raise RuntimeError('Git revision mismatch')
ow = out/'openwrt'
checkout(lock['openwrt'], ow, a.git_cache)
if a.download_cache:
    (ow/'scripts/localmirrors').write_text(a.download_cache.as_uri()+'\n')
for feed in lock['feeds']:
    cache = a.git_cache/'feeds'/feed['name'] if a.git_cache else None
    checkout(feed, ow/'feeds'/feed['name'], cache)
# Keep feeds deterministic: subsequent update uses the same pinned revisions.
(ow/'feeds.conf').write_text(''.join(f"src-git {x['name']} {x['url']}^{x['revision']}\n" for x in lock['feeds']))
profile = out/'tools/release/bootstrap/ram-profile.mk'
image = ow/'target/linux/airoha/image/an7581.mk'
image.write_text(image.read_text()+'\n'+profile.read_text())
shutil.copyfile(out/'tools/generic-ram/board.dts', ow/'target/linux/airoha/dts/an7581-dlink-dpn-be7200gr-ram.dts')
net = ow/'target/linux/airoha/an7581/base-files/etc/board.d/02_network'
s = net.read_text(); marker = '\tcase "$board" in\n'
if s.count(marker) != 1: raise RuntimeError('Unexpected board network source')
net.write_text(s.replace(marker, marker+'\tdlink,dpn-be7200gr-ram)\n\t\t# Keep the first RAM experiment isolated until ports are verified.\n\t\t;;\n', 1))
patchdir = ow/'package/utils/util-linux/patches';patchdir.mkdir(exist_ok=True)
shutil.copyfile(out/'tools/release/bootstrap/001-tools-use-env-bash.patch', patchdir/'001-tools-use-env-bash.patch')
shutil.copyfile(out/'configs/release-base.config', ow/'.config')
receipt = {'source_revisions': lock, 'base_prepared': True, 'base_build_passed': False,
           'public_release_qualified': False, 'private_inputs_copied': False, 'hash_checked_public_archive_cache': bool(a.download_cache)}
record = out/'CLEAN-BASE-STATUS.json'
record.write_text(json.dumps(receipt, indent=2)+'\n')
if a.build:
    wrapper = out/'tools/with_openwrt_env.sh'
    run([wrapper, './scripts/feeds', 'update', '-a'], ow)
    # Require the pinned revision even after feeds update.
    for feed in lock['feeds']:
        rev = subprocess.check_output(['git','-C',ow/'feeds'/feed['name'],'rev-parse','HEAD'],text=True).strip()
        if rev != feed['revision']: raise RuntimeError('Feed revision changed')
    run([wrapper, './scripts/feeds', 'install', 'luci-ssl', 'tar'], ow)
    run([wrapper, 'make', 'defconfig'], ow)
    cfg = (ow/'.config').read_text()
    for line in (out/'configs/release-base.config').read_text().splitlines():
        if line and not line.startswith('#') and line not in cfg.splitlines():
            raise RuntimeError('Required config not selected: '+line)
    run([wrapper, 'make', f'-j{a.jobs}', 'V=s'], ow)
    receipt['base_build_passed'] = True
    record.write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt, indent=2))
