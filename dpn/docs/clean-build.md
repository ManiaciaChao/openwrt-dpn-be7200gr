# Pinned clean layout4 build

Requires Nix, network access to the pinned public sources, and sufficient build
space. From this source tree:

```sh
python3 tools/release/prepare_clean_base.py build/release --build --jobs 8
build/release/tools/with_openwrt_env.sh python3 build/release/tools/release/build_layout4.py --build-id dpn-layout4-rc1
```

The base step checks out the exact OpenWrt and feed commits, builds the toolchain,
kernel and selected packages from source. The second builds the guarded native
helpers, minimal early kernel, normal/recovery profiles, RAM factory installer
and standard sysupgrade package. It does not contact or write to a router.

The two files and checksum/provenance manifests are placed under
build/release/dist/layout4-candidate/. A new output directory is required;
existing release artifacts are never silently overwritten. Original firmware,
per-device vaults and owner keys are not build inputs.

Optional --git-cache and --download-cache on prepare_clean_base reuse only Git
objects and hash-checked public source archives, not compiled artifacts. Iterative
candidate assembly against an existing base is not an independent clean rebuild.

To prepare a GitHub OpenWrt fork, run tools/release/prepare_fork.py with a new
output directory. Follow DPN-BE7200GR.md in that checkout; DPN source/build logic
lives in dpn/, while the repository root remains the pinned upstream OpenWrt tree.

Hardware acceptance, reproducibility comparisons and source/license manifests
are separate release evidence. Merely producing two files does not qualify them.

## Historical layout3 clean build

# Clean base build (development)

The isolated base build pins the OpenWrt commit, every feed revision and the Nix
host environment. It uses the public calibration-free DTS. It starts with an
empty build/staging directory and builds LuCI, GNU tar, wireless and NAND tools
from those source recipes instead of installing cached snapshot APK files.

Run from the source tree with Nix installed:

```sh
python3 tools/release/prepare_clean_base.py build/clean-base --build --jobs 8
```

The output directory must not already exist. `--git-cache openwrt` optionally
fetches pinned Git objects from an existing local checkout; it never copies that
checkout's working files, build directory or toolchain. The recorded upstream
origin and exact commit IDs remain the same. A fresh source export is privacy
checked before any checkout is added. Feed commits are checked again after index
creation. `--download-cache openwrt/dl` optionally uses cached public source
archives through OpenWrt's local mirror mechanism, with recipe hash validation;
it never reuses compiled objects or target binaries. Required package selections must survive `make defconfig`.

This is the base root/kernel/toolchain phase, not yet a single-command finished
firmware release pipeline. `CLEAN-BASE-STATUS.json` records whether the base
build actually completed. The next development phase is:

```sh
cd build/clean-base
python3 tools/release/assemble_clean.py --build-id clean-candidate-v8
```

This connects public helper sources, guarded kernel/module assembly, pinned
firmware inputs, nested image audits and both container formats. The complete
path has completed once from the isolated pinned base: helpers, kernel/root,
nested image audits and both package formats. The resulting normal V8.1 image
passed an actual stock-Web install with an erased configuration bank; V8.1b
passed the subsequent standard sysupgrade and full firmware-prefix readback.
An independent rebuild and reproducibility comparison remain outstanding.
Do not equate one successful clean build with release qualification.
No upload or flash operation is performed by this command.

The source and Nix locks are in `configs/release-sources.json` and
`configs/build-host.json`; package selections are `configs/release-base.config`.
Source archives are obtained by OpenWrt's hash-checked download recipes. A source
mirror and independent rebuild remain release work. The files under
`tools/release/bootstrap` are a development base profile and a host portability
patch, not an upstream submission.
