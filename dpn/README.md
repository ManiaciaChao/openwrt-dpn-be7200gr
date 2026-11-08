# D-Link DPN-BE7200GR OpenWrt fork support

This source implements original-Web installation and standard OpenWrt upgrades
with the original bootloader, compact Linux/SSH recovery and a 408 MiB raw UBI
region. The mounted writable overlay is approximately 352 MiB. Calibration and
MAC come from each device; SSH identities are generated on the target. No owner
credentials, calibration dumps or original firmware backups belong in this repo.

The intended public downloads are:

- **dpn-be7200gr-factory-web.bin**: OEM Web upload; boots a RAM first installer,
  exports/decrypt-verifies the owner's backup before compact-recovery provisioning
  and layout migration.
- **dpn-be7200gr-sysupgrade.bin**: normal updates of an installed layout4 system,
  preserving settings and SSH identity.

Read [installation](docs/generic-first-install.md), [stock backups](docs/stock-backup.md)
and [storage layout](docs/storage-expansion.md). A complete local expanded-layout
stock return/Web recovery reinstall/remigration and final physical cold boot have
passed. The new generic factory RAM installer requires its own hardware acceptance;
older layout3 Web receipts are not evidence for this new package. Current write
qualification covers one documented zero-bad-block/empty-BMT NAND profile.

Build from a pinned clean base using [the build instructions](docs/clean-build.md).
Prepare a real upstream-based Git checkout for GitHub review with:

```sh
python3 tools/release/prepare_fork.py release-stage/openwrt-fork
```

This fetches the pinned upstream commit and adds only reviewed DPN sources under
`dpn/`. It never copies private workspace history or pushes a remote. The parent
research workspace is not the repository to publish. See
[release/upstream status](docs/release-and-upstream.md) and LICENSE-STATUS.md.
