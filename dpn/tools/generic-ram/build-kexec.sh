#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$project_dir/build/generic-kexec/kexec-tools-2.0.32"
compiler_prefix="$project_dir/openwrt/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-"
export CC="${compiler_prefix}gcc" AR="${compiler_prefix}ar" LD="${compiler_prefix}ld" RANLIB="${compiler_prefix}ranlib"
export CFLAGS='-Os' LDFLAGS='-static'
./configure --host=aarch64-openwrt-linux-musl --target=aarch64-openwrt-linux-musl --without-zlib --without-lzma --without-zstd --without-libelf --without-xen
make -j8 STRIP="${compiler_prefix}strip"
"${compiler_prefix}strip" build/sbin/kexec
cp build/sbin/kexec "$project_dir/build/generic-ram/output/kexec-aarch64"
