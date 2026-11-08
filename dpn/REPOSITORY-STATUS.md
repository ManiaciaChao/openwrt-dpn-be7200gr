# Reviewed DPN source export

This allowlisted source tree excludes owner credentials, calibration dumps,
factory firmware/header copies, private vaults and research workspace history.
The layout4 implementation retains the original bootloader, compact SSH recovery
and per-device identity while allocating 408 MiB raw UBI space to OpenWrt.

Hardware qualification belongs to exact artifact hashes and de-identified
receipts; source privacy checks alone do not qualify binaries. Build from pinned
sources using docs/clean-build.md and read docs/generic-first-install.md before
installation. Private OEM backups stay external to this repository.
