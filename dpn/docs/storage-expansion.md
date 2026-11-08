# DPN-BE7200GR writable storage expansion

Local qualification, 2026-11-08: the 408 MiB layout, normal boot, owner/radio
checks and a complete standard sysupgrade have passed on the recorded unit.
After reclaiming the old stock regions, full stock50/vendor83.5 restoration,
original Web/root login, Web reinstall of compact recovery, and migration back
to the final OpenWrt candidate have also passed. The original bootloader boots
Linux directly; no permanent second U-Boot is installed.

The final candidate is `build/storage-layout/layout4-profiles-v11`, with its
standard package in `build/storage-layout/layout4-sysupgrade-v7`. Its upgrade
backend/kernel/native tools are the same as the v6 payload that completed an
unassisted standard sysupgrade; v7 adds the independently tested recovery-client
loader preflight fix and a revision marker. Actual final-image migration and
normal boot passed. Final physical cold boot after TTL removal, WAN DHCP/Internet/DNS, owner SSH,
dual radios, original LuCI certificate and root login all passed. WAN negotiated
2.5 Gbps on the tested upstream link. This is not a public-release qualification.

| Physical region | Size | Purpose |
| --- | ---: | --- |
| 0–0.5 MiB | 0.5 MiB | Original bootloader, unchanged |
| 0.5–16.5 MiB | 16 MiB | Normal Linux thin FIP |
| 16.5–50.5 MiB | 34 MiB | OpenWrt UBI data extent A |
| 50.5–66.5 MiB | 16 MiB | Independent Linux/SSH recovery |
| 66.5–70.5 MiB | 4 MiB | Device-bound recovery identity and stock-state vault |
| 70.5–444.5 MiB | 374 MiB | OpenWrt UBI data extent B |
| 444.5–448 MiB | 3.5 MiB | ART/calibration/MAC/stock selector |
| 448–512 MiB | 64 MiB | Entire original vendor-reserved/BMT tail, unchanged |

The two data extents form one 408 MiB MTD concat. UBI reserves metadata and
bad-block capacity; its static SquashFS root currently consumes 31 LEBs
(7.5 MiB), leaving a 379 MiB dynamic rootfs_data volume. The mounted UBIFS overlay measures 360520 KiB (352.07 MiB) total and
354644 KiB (346.33 MiB) available after owner configuration restoration.
Those raw/volume sizes differ from final package-install capacity.

The main root is standard UBI/SquashFS plus a UBIFS rootfs_data overlay. Packages
and user changes live in that overlay. The recovery vault is separate from
normal user configuration and contains per-device authentication and the
factory-bound original-state digests. Original calibration/MAC are read through
NVMEM, never embedded in generic firmware. Full owner-specific stock50 and
vendor83.5 return materials are kept encrypted outside the router; they are not
public firmware payloads.

Migration and updates select independent recovery before rebuilding main data,
verify the root and restored standard sysupgrade configuration, commit the main
firmware header last, and only then select normal boot. Boot never implicitly
formats a missing UBI. A missing/invalid normal root enters the vault recovery
branch. The complete local standard sysupgrade and post-reclamation stock-return/Web
roundtrip are now separately recorded. Recovery is a wired SSH environment with
its own device-bound identity; it never depends on mounting the main UBI.

The small stock-Web recovery reinstall used here requires an existing valid
vault. It is not a brand-new-device universal factory installer. Full stock
return currently requires the owner-specific external stock50/vendor83.5 backup;
a generic downloaded vendor update alone is not qualified. Write qualification
remains limited to the tested zero-bad-block/empty-BMT device profile; other
profiles must fail closed. Generic first-install/reset flows and a reproducible
public release/upstream submission remain separate work.


See artifacts/storage-layout/local-expanded-stock-Web-recovery-roundtrip-v1.json
and tools/storage_layout/README.md for receipts and implementation status.
The following section records the earlier 256 MiB layout and is historical.

## Historical layout2/layout3 expansion

Status: complete, 2026-11-06. Bank 2 is active. Raw UBI bank: 256 MiB;
UBI volume: 242.1 MiB; UBIFS df total: 223.63 MiB; available after cleanup:
216.05 MiB. See artifacts/storage-expand/completion.json and final-storage.json.

The bridge, migration to bank 2, and a subsequent layout-2 to layout-2 normal
sysupgrade were performed over SSH. A 32 MiB incompressible file was written,
SHA256 verified, preserved through a clean software restart, verified again and
removed. This is not a new physical cold-boot test. AP configuration, passwords,
SSH host keys and authorized_keys hashes match the pre-expansion baseline.
LuCI HTTPS and static assets pass with the existing pinned device certificate;
the login form's HTTP 403 is LuCI's expected unauthenticated response.

Current canonical image: firmware/private/openwrt-dpn-be7200gr-sysupgrade.bin
SHA256: 1cfb92645f687e82fd989829980a6d78aa82562d7677b9b5b597fd3e9c2f6352
FIP SHA256: 1fd44b4d5750c946827a1f65050e47ad35eeef3b125f36545c07eef4dd93d9ee
Prefix SHA256: c646496e07f1632820e434f05e18ebbe7e187a3cac93185901c18d7258f728a4

The old 32 MiB bank SHA256 remains
fe7e92bd0e0115995e95cac78613bd2fca469c907b8b68a07b0c77892fb5ab8d.
It is a retained configuration snapshot, not an automatic A/B firmware rollback.
The final image materializes APK package alternatives in the ROM and explicitly
copies GNU tar into the upgrade RAM filesystem, so config restore does not rely
on an overlay-only /bin/tar symlink.

The vendor bootloader still boots a factory-header FIP containing FIT, kernel and
SquashFS. The firmware write window remains 18 MiB at [0x80000,0x1280000).
No bootloader/environment, factory backup, ART, vendor data or BMT relocation is
needed. A new 256 MiB UBI bank occupies [0x0b800000,0x1b800000), wholly inside the
previously unused area. The old 32 MiB bank remains at [0x1280000,0x3280000).

The selected region was read in full from the current device and compared with
the original physical ECC NAND snapshot: both were entirely FF. The exact
receipt is artifacts/storage-expand/unused-region-readonly.json.

Migration uses a layout-1 bridge kernel with bounded support for the new bank.
A temporary MTD view exposes only the new 256 MiB, only while bank 1 is active.
A page-program/ECC-readback/erase test precedes UBI formatting. The old overlay is
remounted read-only, then all upper files, numeric ownership, modes, hardlinks,
symlinks, whiteouts and extended attributes are copied and compared. A ready
marker is written only after successful comparison. The layout-2 upgrade checks
that marker before any firmware erase, and preserves the cloned upper. It never
formats the old bank. Layout-2 native validation rejects layout-1 downgrade.

GNU tar --acls must not be used for extraction to this UBIFS: it attempts to set
minimal ACLs even when the archive has no ACL records, and UBIFS rejects them.
The bridge's first restore stopped safely in the RAM SSH fallback for this reason.
No stored ACL records existed. Recovery re-extracted with --xattrs-include='*',
compared the full archive, then committed the usual configuration transaction;
no firmware rewrite was necessary. New upgrade hooks omit --acls.

LuCI and GNU tar are included in the new SquashFS, rather than depending solely
on packages in the upper. Existing AP configuration, passwords and both SSH
public keys are preserved from the current device; no credential defaults are
reapplied.

The /tmp tmpfs limit remains the default half of Linux-visible RAM. It is a cap,
not a reservation. Shrinking it does not release unused memory. Volatile logs,
package downloads and upgrade staging remain in RAM, avoiding routine Flash
writes. The wired early recovery initramfs omits duplicate radio firmware and
LuCI web assets; normal boot loads these from SquashFS.

Raw NAND OpenWrt commonly stores rootfs and rootfs_data in UBI, with UBIFS as the
writable overlay. This device retains the vendor's raw FIP boot arrangement and
uses a dedicated UBI bank for rootfs_data, while keeping the usual SquashFS plus
overlayfs runtime model. References:

- https://github.com/openwrt/openwrt/blob/main/package/base-files/files/lib/upgrade/nand.sh
- https://docs.kernel.org/filesystems/tmpfs.html

Private backups, raw transcripts and device-specific images are kept under
firmware/private and sealed with age in backups/. Public receipts contain no
passwords or private keys. Power-loss atomicity of the single firmware slot is
not claimed; preserving the bootloader does not make an interrupted firmware
write automatically recover over the network.
