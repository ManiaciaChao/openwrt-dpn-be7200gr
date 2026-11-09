// SPDX-License-Identifier: GPL-2.0-only
/* Live backport only: production images describe these LEDs in their DT. */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/gpio/driver.h>
#include <linux/leds.h>
#include <linux/of.h>
#include <linux/string.h>

static struct platform_device *led_device;
static struct gpio_device *gpio_device;
static struct gpio_led leds[] = {
 { .name = "net", .active_low = 1, .default_state = LEDS_GPIO_DEFSTATE_OFF },
 { .name = "wlan2g", .active_low = 1, .default_state = LEDS_GPIO_DEFSTATE_OFF },
 { .name = "wlan5g", .active_low = 1, .default_state = LEDS_GPIO_DEFSTATE_OFF },
 { .name = "mesh", .active_low = 1, .default_state = LEDS_GPIO_DEFSTATE_OFF },
};
static const unsigned int offsets[] = { 20, 15, 13, 22 };
static struct gpio_led_platform_data data = { .num_leds = ARRAY_SIZE(leds), .leds = leds };
static int __init dpn_led_init(void)
{
 struct gpio_chip *chip;
 unsigned int i;
 if (!of_machine_is_compatible("dlink,dpn-be7200gr-layout4"))
  return -ENODEV;
 gpio_device = gpio_device_find_by_label("1fbf0200.system-controller:pinctrl");
 if (!gpio_device)
  return -ENODEV;
 chip = gpio_device_get_chip(gpio_device);
 if (!chip || chip->ngpio != 64 || gpio_device_get_base(gpio_device) < 0) {
  gpio_device_put(gpio_device);
  return -ENODEV;
 }
 for (i = 0; i < ARRAY_SIZE(leds); i++)
  leds[i].gpio = gpio_device_get_base(gpio_device) + offsets[i];
 led_device = platform_device_register_data(NULL, "leds-gpio", PLATFORM_DEVID_AUTO,
                                            &data, sizeof(data));
 if (IS_ERR(led_device)) {
  gpio_device_put(gpio_device);
  return PTR_ERR(led_device);
 }
 return 0;
}
static void __exit dpn_led_exit(void)
{
 platform_device_unregister(led_device);
 gpio_device_put(gpio_device);
}
module_init(dpn_led_init);
module_exit(dpn_led_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("DPN-BE7200GR confirmed LEDs live backport");
