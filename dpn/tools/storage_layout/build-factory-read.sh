#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p build/storage-layout
libfdt=openwrt/build_dir/host/u-boot-v2026.10/scripts/dtc/libfdt
sources=("$libfdt"/*.c)
flags=(-O2 -Wall -Wextra -Werror -Wno-misleading-indentation -I"$libfdt")
if [[ ${1:-target} == host ]]; then
 tools/with_openwrt_env.sh bash -c 'exec cc "$@" $(pkg-config --cflags --libs libmd)' _ "${flags[@]}" -O1 -g -fsanitize=address,undefined -DDPN_FACTORY_READ_HOST_TEST tools/storage_layout/factory_read.c "${sources[@]}" -o build/storage-layout/factory-read-host
else
 tools/with_openwrt_env.sh openwrt/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc -static "${flags[@]}" -Iopenwrt/staging_dir/target-aarch64_cortex-a53_musl/usr/include tools/storage_layout/factory_read.c "${sources[@]}" openwrt/staging_dir/target-aarch64_cortex-a53_musl/usr/lib/libmd.a -o build/storage-layout/dpn-factory-read
fi
