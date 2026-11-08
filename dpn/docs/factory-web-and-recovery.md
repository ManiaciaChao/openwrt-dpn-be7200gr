# Factory Web and recovery validation

The default source factory packager now produces the hardware-untested
`automatic` installer described in [automatic first installation](automatic-first-install.md).
All RC2 receipts below concern the legacy host-assisted mode, including its
external backup and recovery reboot checkpoint; they do not qualify the new flow.

Current public format: a layout4 factory RAM first installer, plus a matching
standard sysupgrade image. See [installation](generic-first-install.md).

The original bootloader, compact recovery and private vault are retained in the
expanded layout. The complete local stock return → original Web recovery
reinstall → 408 MiB remigration loop and final physical cold boot passed.
Relevant de-identified records are:

- artifacts/storage-layout/local-standard-sysupgrade-v3.json
- artifacts/storage-layout/local-expanded-roundtrip-v2.json
- artifacts/storage-layout/local-final-coldboot-v1.json

The standard v3 receipt belongs to profiles-v10/sysupgrade-v6. Later v11/v7 fixed
the recovery-entry loader preflight with the same kernel/upgrade backend; migration
and final cold boot were verified separately. Do not relabel those receipts as
an exact-byte test of a new candidate.

The RC2 factory RAM installer has now booted from the original Web path, generated
an independent SSH identity and initialized the device-bound recovery/vault after
an externally decrypt-verified backup. Actual NAND recovery boot, 408 MiB
migration, normal boot, exact matching standard sysupgrade and final physical
cold boot/WAN/LuCI verification passed. The exact de-identified receipt is
artifacts/storage-layout/generic-factory-Web-and-sysupgrade-RC2.json.

This first install imported the existing owner's AP/settings/keys explicitly in
RAM after verifying fresh target key generation. Its host wrapper stopped on the
TCP timeout after a successful recovery reboot; the remaining public stages were
continued from that verified checkpoint. The timeout handling is fixed and unit
regression tested. Do not describe this first run as a completely unassisted
one-command install. The matching standard sysupgrade did complete without a
manual checkpoint. Qualification remains one recorded zero-bad-block/empty-BMT
unit/profile, not every unit/revision or power-loss scenario.

Public images must never include the private REC/vault candidate used on the
laboratory router. Each new unit exports its own original system/vendor state
and creates its own vault and identities. Backups stay external and private.
