# SPDX-License-Identifier: GPL-2.0-only
PYTHON ?= python3
FACTORY ?= build/layout4-factory
SYSUPGRADE ?= build/layout4-sysupgrade
OUTPUT ?= dist/packages
FORMAT ?= both
BUILD_ID ?= dpn-layout4-rc1
.PHONY: images packages help
help:
	@echo 'make images BUILD_ID=dpn-layout4-rc1 (after completed pinned clean base build)'
	@echo 'make packages FORMAT=both FACTORY=... SYSUPGRADE=... OUTPUT=dist/packages'
	@echo 'Build/package only; no upload or device write.'
images:
	tools/with_openwrt_env.sh $(PYTHON) tools/release/build_layout4.py --build-id "$(BUILD_ID)"
packages:
	$(PYTHON) tools/release/package_layout4_set.py --factory "$(FACTORY)" --sysupgrade "$(SYSUPGRADE)" --output "$(OUTPUT)" --format "$(FORMAT)"
