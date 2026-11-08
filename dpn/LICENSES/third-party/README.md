# Native writer dependency notices

The writer is GPL-2.0-only. Its development build uses libmd SHA-1/SHA-256 and
libfdt instead of OpenSSL. Preserve original source copyright notices as well
as these complete license files when distributing the corresponding source or
binaries. This inventory does not approve the entire firmware image.

- libmd 1.2.0: https://archive.hadrons.org/software/libmd/libmd-1.2.0.tar.xz
  SHA256 ac15ffb8430502fbaccdec66c5a82ee0eab0b0f36220df56710feadfeb13d0a0.
  Complete upstream COPYING is included. The selected SHA-1 source is public
  domain and SHA-2 carries Aaron Gifford's BSD-3-Clause notice; other library
  files have additional terms documented in the full COPYING.
- libfdt from U-Boot 2026.10, scripts/dtc/libfdt:
  https://git.u-boot-project.org/u-boot/u-boot/-/releases/v2026.10/downloads
  Archive u-boot-2026.10.tar.bz2 SHA256
  3f856da3cbbc93af51ff95fde18588a348b4a26723b01d9841e999d988481015.
  Selected files offer GPL-2.0-or-later OR BSD-2-Clause; use the BSD option for
  this dependency and retain the per-file copyright notices.

Digest vectors were checked against Python hashlib on host and ARM QEMU.
This records dependency provenance and functional checks, not legal clearance.
