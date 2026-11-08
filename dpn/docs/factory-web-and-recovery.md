# Factory Web and recovery validation

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

The new factory RAM installer was assembled from public source after those
experiments. Its 50 MiB-slot packaging, read-only filesystem extractor, per-device
vault preparation and journaled install orchestration need a new end-to-end
hardware receipt. Host sanitizer/synthetic tests are not substitutes for that.
Small existing-vault Web reinstall and older layout3 pristine-Web tests are
historical evidence, not qualification of this new first-install file.

Public images must never include the private REC/vault candidate used on the
laboratory router. Each new unit exports its own original system/vendor state
and creates its own vault and identities. Backups stay external and private.
