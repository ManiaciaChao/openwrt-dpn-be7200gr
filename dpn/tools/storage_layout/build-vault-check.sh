#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p build/storage-layout
flags=(-O2 -Wall -Wextra -Werror -Wno-misleading-indentation)
if [[ ${1:-target} == host ]]; then
 tools/with_openwrt_env.sh bash -c 'exec cc "$@" $(pkg-config --cflags --libs libmd)' _ "${flags[@]}" -O1 -g -fsanitize=address,undefined tools/storage_layout/vault_check.c -o build/storage-layout/vault-check-host
else
 tools/with_openwrt_env.sh openwrt/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc -static "${flags[@]}" -Iopenwrt/staging_dir/target-aarch64_cortex-a53_musl/usr/include tools/storage_layout/vault_check.c openwrt/staging_dir/target-aarch64_cortex-a53_musl/usr/lib/libmd.a -o build/storage-layout/dpn-vault-check
fi
