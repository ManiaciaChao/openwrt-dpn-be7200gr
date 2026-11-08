# D-Link DPN-BE7200GR

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
