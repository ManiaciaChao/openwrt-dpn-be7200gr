#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare an actual OpenWrt Git fork with allowlisted DPN sources under dpn/.

Fetches the pinned upstream commit only. No private workspace history, local
OpenWrt modifications, credentials or backups are copied. No remote is created
on GitHub, no commit author is invented, and nothing is pushed.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

R = Path(__file__).resolve().parents[2]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--git-cache', type=Path, default=R/'openwrt')
    a = p.parse_args()
    out = a.output.resolve()
    if out.exists():
        p.error('Use a new directory')
    lock = json.loads((R/'configs/release-sources.json').read_text())['openwrt']
    def run(*args):
        subprocess.run(list(map(str, args)), check=True)
    out.mkdir(parents=True)
    run('git', 'init', '-q', out)
    run('git', '-C', out, 'remote', 'add', 'upstream', lock['url'])
    cache = a.git_cache.resolve()
    source = str(cache) if (cache/'.git').exists() else lock['url']
    run('git', '-C', out, 'fetch', '--depth=1', source, lock['revision'])
    run('git', '-C', out, 'checkout', '-q', '-b', 'dpn-be7200gr-layout4', 'FETCH_HEAD')
    run('python3', R/'tools/release/stage_source.py', out/'dpn')
    shutil.copy2(R/'tools/release/bootstrap/dpn-build.yml', out/'.github/workflows/dpn-build.yml')
    readme=out/'README.md'
    readme.write_text('''# OpenWrt for D-Link DPN-BE7200GR

This fork carries the DPN-BE7200GR installation and upgrade implementation under
`dpn/`, based on the pinned upstream OpenWrt source. It retains the original
bootloader and compact SSH recovery, with a 408 MiB raw UBI data region.

Download the tested [RC2 installation bundle and both firmware formats](https://github.com/ManiaciaChao/openwrt-dpn-be7200gr/releases/tag/dpn-layout4-rc2).
Read the release qualification notes before installing.

Start with [installation](dpn/docs/generic-first-install.md),
[build instructions](DPN-BE7200GR.md) and [owner backup instructions](dpn/docs/stock-backup.md).
The two firmware formats are factory-Web first install and normal sysupgrade.
Qualification is limited to the documented NAND/stock profile; this is not an
OpenWrt-maintainer-approved device port. Device backups and private keys are not
part of this repository.

---

'''+readme.read_text())
    (out/'DPN-BE7200GR.md').write_text('''# D-Link DPN-BE7200GR

This branch retains the upstream OpenWrt tree and carries the DPN image assembly
and installation implementation in `dpn/`. It uses the original bootloader,
compact SSH recovery and 408 MiB raw UBI data space. Read
[installation](dpn/docs/generic-first-install.md) before using any image.

Build from pinned sources, with Nix installed:

```sh
python3 dpn/tools/release/prepare_clean_base.py dpn/build/release --git-cache . --build --jobs 8
dpn/build/release/tools/with_openwrt_env.sh python3 dpn/build/release/tools/release/build_layout4.py --build-id dpn-layout4-rc2
```

Outputs are `dpn-be7200gr-factory-web.bin` and
`dpn-be7200gr-sysupgrade.bin` under `dpn/build/release/dist/layout4-candidate/`.
The first is an OEM Web RAM installer; the second updates an installed layout4
system. Device-specific backups are never part of the repository or downloads.
This fork is not an upstream-accepted device definition. Candidate qualification
is recorded separately; producing files does not establish hardware acceptance.
''')
    ignore = out/'.gitignore'
    ignore.write_text(ignore.read_text()+'\n# DPN local build and owner sessions\n/dpn/build/\n/dpn/dist/\n/dpn/openwrt/\n/dpn/firmware/\n/dpn/backups/\n/dpn/owner-session*/\n')
    (out/'dpn/FORK-STATUS.json').write_text(json.dumps({'upstream_revision': lock['revision'],
        'source_only': True, 'private_inputs_copied': False, 'remote_published': False,
        'new_factory_installer_hardware_qualified': False}, indent=2)+'\n')
    print('OPENWRT_FORK_PREPARED_WITH_REVIEWED_LAYOUT4_SOURCES_NO_PUSH', out)

if __name__ == '__main__':
    main()
