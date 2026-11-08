#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec nix develop --impure --file "$root_dir/tools/openwrt-shell.nix" --command "$@"
