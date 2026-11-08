# Release and upstream integration

The deliverable is an upstream-based OpenWrt fork carrying the DPN sources under
`dpn/`, with two download formats: factory-Web first installation and standard
layout4 sysupgrade. Private OEM backups stay with their owners and are never
included in Git or downloadable images.

## Current implementation

The original bootloader is retained. Normal Linux uses 16 MiB, compact Linux/SSH
recovery uses 16 MiB, and each device has a 4 MiB identity/state vault. Two data
extents form 408 MiB raw UBI: static SquashFS root and dynamic UBIFS rootfs_data.
ART and the entire 64 MiB vendor-reserved tail remain protected.

The factory-Web package boots a wired RAM installer. It contains generic normal
and recovery payloads, not an experimental unit's vault or calibration. Owners
configure their own root password/public key, export a decrypt-verified external
backup and provision recovery. An actual independent NAND recovery boot must be
verified before reclaiming the old filesystem/vendor/configuration area.
The normal first-install payload is identical to the matching sysupgrade payload.

The original boot profile accepts the public-input FIP wrapper with empty DER
certificate records. This is not a signature implementation or a compatibility
claim for other secure-boot profiles. The larger factory RAM installer fits the
OEM 50 MiB slot; the final normal and recovery images each remain bounded by
16 MiB. Existing small recovery Web reinstall packages are not generic first
installers and are not the public factory download.

## Validation boundary

The local layout4 migration, unassisted standard sysupgrade, independent SSH
recovery, full original stock/vendor restoration, original Web recovery reinstall,
remigration, owner identity preservation and final physical cold boot have passed.
Public de-identified receipts are separate from owner backup/log files.

The newly assembled generic RAM factory installer needs its own complete hardware
acceptance, including pristine LuCI password/key setup and the matching final
sysupgrade. Older layout3 Web tests cannot qualify this new implementation.
Writes currently require the recorded FORESEE geometry, zero bad blocks and
empty BMT/RAWB. Unsupported NAND states fail closed, rather than guessing a mapping.

Installation/upgrades require uninterrupted power. Deliberate physical power-cut
qualification is deferred; no power-loss-safe guarantee is made. The recovery
path does not cover damaged bootloader/ART/BMT, corrupt recovery identity or every
possible kernel/network failure. Full OEM restoration needs the owner's exported
stock and vendor-state backup, not an arbitrary downloaded OEM update container.

## Build and publication

Use the pinned OpenWrt/feed/Nix/source inputs and the clean assembly command in
[clean-build.md](clean-build.md). Keep complete license notices, source provenance,
SHA256 manifests and hardware qualification status alongside the outputs.
Check actual unpacked kernel/initramfs/DTB/SquashFS, including nested installer
payloads; a source-only secret scan is not a firmware content audit.

`tools/release/prepare_fork.py` creates an actual upstream Git checkout plus the
allowlisted DPN implementation. It does not copy the research Git/workspace
history, owner dumps or keys; it makes no commit or remote push. Assign the
intended GitHub repository and contributor identity separately. Do not invent
DCO sign-offs or claim OpenWrt maintainer acceptance.

## Upstream follow-up

The fork currently assembles guarded chip/controller changes, board data,
modules and image/upgrade hooks through its DPN build extension. Consolidating
these into native OpenWrt packages/device recipes and reviewable generic patches
remains upstream work. GPIO/PCI reset sequencing, reserved memory and firmware
package integration still require review. Wireless offload and actual 10 Gbit/s
throughput are separate from installation qualification.
