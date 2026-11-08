#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
cd "$(dirname "$0")/../.."
kind=${1:-target}
libfdt=openwrt/build_dir/host/u-boot-v2026.10/scripts/dtc/libfdt
src=("$libfdt"/*.c)
flags=(-O2 -Wall -Wextra -Werror -Wno-misleading-indentation -I"$libfdt")
if [ "$kind" = host ]; then
 tools/with_openwrt_env.sh bash -c 'exec cc "$@" $(pkg-config --cflags --libs libmd)' _ "${flags[@]}" -O1 -g -fsanitize=address,undefined -DDPN_UPGRADE_HOST_TEST tools/first-install/writer.c "${src[@]}" -o build/generic-ram/writer-host-test
else
 tools/with_openwrt_env.sh openwrt/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc -static "${flags[@]}" -Iopenwrt/staging_dir/target-aarch64_cortex-a53_musl/usr/include tools/first-install/writer.c "${src[@]}" openwrt/staging_dir/target-aarch64_cortex-a53_musl/usr/lib/libmd.a -o build/generic-ram/output/dpn-install
fi
