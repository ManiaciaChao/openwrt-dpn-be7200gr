#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Optional live backport, built against an already prepared matching kernel.
# Usage: build.sh KERNEL_TREE CROSS_COMPILE OUTPUT_DIRECTORY
set -eu
[ "$#" = 3 ]
kernel=$(realpath "$1")
cross="$2"
out="$3"
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$kernel/.config" ] && [ -f "$kernel/Module.symvers" ]
[ ! -e "$out" ]
mkdir -p "$out"
out=$(realpath "$out")
cp "$kernel/drivers/leds/leds-gpio.c" "$out/leds-gpio.c"
cp "$source_dir/dpn_led_board.c" "$out/dpn_led_board.c"
printf 'obj-m += leds-gpio.o dpn_led_board.o\n' > "$out/Makefile"
make -C "$kernel" M="$out" ARCH=arm64 CROSS_COMPILE="$cross" modules
