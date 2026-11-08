# Source and dependency licensing

Project-authored DPN implementation, build tools and installation code are
GPL-2.0-only unless a file states otherwise. This includes the original
`tools/generic-ram/overlay/lib/upgrade/dpn-config-commit.sh` helper. The complete
GPL v2 text is included in LICENSES/GPL-2.0-only.txt. Existing upstream and
third-party notices retain their original terms; this does not relicense them.

Native writers use libmd SHA-1/SHA-256 and libfdt, not OpenSSL. Their complete
upstream notices and pinned provenance are under LICENSES/third-party/.
The DPN source export contains no extracted vendor executable, factory FIP
certificate/header, unit calibration dump or private authentication material.
The public FIP wrapper is generated from source with empty DER records.

Airoha firmware comes from the hash-pinned linux-firmware inputs recorded in
artifacts/offload/firmware-source.json and is redistributed unmodified as
separate firmware files under LICENSE.airoha, for Airoha-chipset devices.
MediaTek radio firmware comes from the pinned OpenWrt mt76 package inputs.
Firmware files are not relicensed under the project's GPL. Preserve the actual
firmware/dependency license texts with distributed artifacts and maintain the
corresponding source/build provenance for GPL components.

Source privacy, image generation and a successful hardware test are distinct
checks. A candidate manifest records its exact build and hardware qualification;
it does not claim that OpenWrt maintainers have accepted this device support.
