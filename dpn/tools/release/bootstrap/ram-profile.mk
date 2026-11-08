define Device/dlink_dpn-be7200gr-ram
  DEVICE_VENDOR := D-Link
  DEVICE_MODEL := DPN-BE7200GR
  DEVICE_VARIANT := experimental RAM only
  DEVICE_DTS := an7581-dlink-dpn-be7200gr-ram
  DEVICE_PACKAGES := ubus ethtool rtl826x-firmware \
	-mtd -uboot-envtools -airoha-en7581-npu-firmware \
	-kmod-leds-gpio -kmod-gpio-button-hotplug
  SOC := an7581
  KERNEL := kernel-bin
  KERNEL_INITRAMFS := kernel-bin
  KERNEL_INITRAMFS_SUFFIX := -kernel.bin
  FILESYSTEMS :=
  IMAGES :=
  ARTIFACTS :=
endef
TARGET_DEVICES += dlink_dpn-be7200gr-ram
