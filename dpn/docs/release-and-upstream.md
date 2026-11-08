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

The default factory-Web package boots a wired RAM installer and installs on the
device automatically. It contains generic normal and recovery payloads, not an
experimental unit's vault or calibration. Per-device identities and the vault
are generated on the target. Full stock backup is an optional operation performed
separately before flashing; there is no host-tool or intermediate Web setup step.
Recovery/vault NAND readback precedes migration, which uses the standard RAM
upgrade backend without an intermediate recovery reboot. See
[automatic first installation](automatic-first-install.md) for that changed
validation boundary. Published RC2 remains the legacy host-assisted installer
with an external backup and independent recovery boot before migration.
The normal first-install payload is identical to the matching sysupgrade payload.

The original boot profile accepts the public-input FIP wrapper with empty DER
certificate records. This is not a signature implementation or a compatibility
claim for other secure-boot profiles. The larger factory RAM installer fits the
OEM 50 MiB slot; the final normal and recovery images each remain bounded by
16 MiB. Existing small recovery Web reinstall packages are not generic first
installers and are not the public factory download.

## Validation boundary

The automatic installer is a new candidate pending hardware tests. None of the
RC2 or earlier hardware receipts below qualifies its new installation sequence.

The local layout4 migration, unassisted standard sysupgrade, independent SSH
recovery, full original stock/vendor restoration, original Web recovery reinstall,
remigration, owner identity preservation and final physical cold boot have passed.
Public de-identified receipts are separate from owner backup/log files.

The RC2 generic RAM factory Web boot, public-key setup API, independent NAND
recovery provisioning, expanded migration and matching standard sysupgrade have
passed with final physical cold boot/WAN/LuCI checks. Existing owner settings
were explicitly imported after fresh key generation. The first-install host
reboot-timeout checkpoint and its fix are documented in the exact RC2 receipt;
that run is not labeled fully unassisted. The standard upgrade required no
manual checkpoint. Independent GitHub clean-build evidence is tracked separately.
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
