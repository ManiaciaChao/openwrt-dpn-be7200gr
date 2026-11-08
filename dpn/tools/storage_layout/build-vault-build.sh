#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p build/storage-layout
flags=(-Os -Wall -Wextra -Werror)
if [[ ${1:-target} == host ]]; then
 tools/with_openwrt_env.sh bash -c 'exec cc "$@" $(pkg-config --cflags --libs libmd) -lz' _ "${flags[@]}" -g -fsanitize=address,undefined -DDPN_VAULT_BUILD_HOST_TEST tools/storage_layout/vault_build.c -o build/storage-layout/vault-build-host
else
 stage=openwrt/staging_dir/target-aarch64_cortex-a53_musl/usr
 tools/with_openwrt_env.sh openwrt/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc -static "${flags[@]}" -I"$stage/include" tools/storage_layout/vault_build.c "$stage/lib/libmd.a" "$stage/lib/libz.a" -o build/storage-layout/dpn-vault-build
fi
