# Wi-Fi、Mesh 和 Reset 按键

按键支持是 RC2 之后的改动；不要将已发布的 RC2 视为支持这些按键。

三个实体键已在本机读取电平验证：Reset GPIO 0、Wi-Fi GPIO 5、Mesh GPIO 16，
均 active-low。设备树采用标准 gpio-keys-polled 和 OpenWrt
gpio-button-hotplug，20 ms 轮询、60 ms 防抖。
以下是系统运行期间的行为；没有改变原厂 bootloader 对上电时按住 Reset 的处理。

| 实体按钮 | OpenWrt 事件 | 行为 |
| --- | --- | --- |
| Wi-Fi | rfkill | 松开时用上游脚本切换全部无线电，保存 disabled 设置 |
| Mesh | wps | 标准 WPS 按键事件；没有启用 WPS 的 AP 不开启配对 |
| Reset | reset | 按下不足 1 秒后松开重启；1–4 秒无操作；至少 5 秒后松开清配置并重启 |

## Mesh 键与 WPS

无线包使用完整 wpad-mbedtls，提供 WPS。WPS 默认关闭；在 LuCI 对应无线网络的
“无线安全”页中启用 WPS Pushbutton，或为目标 wifi-iface 设置 `option wps_pushbutton '1'`。
例如将下面的 WIFI_IFACE 替换为自己的无线接口配置节名：

```sh
uci set wireless.WIFI_IFACE.wps_pushbutton='1'
uci commit wireless
wifi reload
```

随后短按 Mesh 键启动标准 WPS PBC 配对窗口。AP 必须采用支持 WPS 的个人加密模式；
纯 WPA3-SAE 不能据此获得 WPS。关闭该选项即可停用。按键不会自动配置 802.11s、
EasyMesh 或原厂 Mesh；没有第二台 Mesh 设备，不声称 Mesh 互联已验证。

## Reset 的布局兼容处理

长按重置清除用户网络、Wi-Fi、额外软件包和其他 overlay 自定义。
它恢复有线 LAN 192.168.1.1/24、LAN DHCP，关闭 WAN 和无线；初始 LuCI 密码为空，
应直连 LAN 重新配置。WAN 不会运行 DHCP 服务器。

为保留独立恢复通道，当前所有者 authorized_keys 和 Ed25519 SSH 主机密钥保留，
密码 SSH 仍关闭。这一点不同于会重新生成 SSH 身份的普通 OpenWrt 全清重置。
原厂 bootloader、校准、恢复环境和每机恢复资料不变，不是“刷回原厂”。

实现先在现有 UBIFS 内准备新 upper 和事务标记，下一次早期启动完成目录切换，
不擦除 UBI 卷、不改启动槽和固件。恢复环境与 RAM 首装环境不执行运行态 Reset。
清配置后的默认 LAN/DHCP 应在隔离直连链路验收，不能把普通按键电平测试称为
真实清配置或 WPS 客户端配对通过。

## 当前验证记录

新正常系统已通过保留配置的实际 sysupgrade，GPIO 驱动已绑定。上游 rfkill
处理脚本的软件事件实际关闭并恢复了两个频段；标准 WPS 脚本能打开 PBC 窗口。
电脑作为 WPS 客户端完成注册器协议交换，AP 记录 WPS-SUCCESS，但电脑没有完成
后续连接和 DHCP，因此不将它记为完整客户端联网验证。

三个实体键的 GPIO 按压/松开电平已在升级前确认；升级后的第二轮实体触发测试尚未完成。
Reset 的时长/失败保护、目标机 RAM 默认配置生成与身份保留、早期目录切换中断重试
已通过测试；没有实际按键清空当前所有者配置。测试后原 AP、管理凭据与无线文件恢复，
WPS 关闭。准确镜像与覆盖范围见 artifacts/storage-layout/button-support-v1.json。
