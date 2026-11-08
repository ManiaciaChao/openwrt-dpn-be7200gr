# 导出并保管每台设备自己的原厂备份

原厂 dump 属于设备所有者，包含配置与设备身份；本项目不提交、不公开分发。
正常的官网下载升级包不等于全分区备份。

完整原厂备份是 automatic 镜像刷机前的可选操作，不是安装前提。
automatic 安装器不导出或保存完整原厂备份；需要完整回原厂能力的用户应提前自行备份。
镜像自动保留的校准/必要恢复资料不能替代完整原厂槽和 vendor 备份。

## 优先使用已验证的原厂 Dropbear

在已测试的原厂版本上，管理员认证后的 x_myset1.html 有独立 Dropbear Enable
和 Port 设置。仓库 tools/first-install/stock-web.py 提供 inspect/enable/restore，
只修改这个对象并回读核对，不提交整个隐藏页面。运行 --help 查看参数。
必须先独立核对 TLS 证书指纹，使用自己的网页凭据。

Dropbear 登录需要已核实的原厂 root 凭据；它与网页 admin 密码可能不同。
本项目不发布凭据，也不猜密码。Telnet 开关的存在不代表它能提供 root shell；
部分厂商终端是受限管理 CLI。因此当前指引采用已验证的 Dropbear，
不将 Telnet 当作已验收的备份通道。

通过 LAN 登录 SSH，核对 id 的 UID 为 0，并读取 cat /proc/mtd。
根据当前输出中的分区名称和大小识别完整 tclinux、tclinux_slave、bootloader、
ART 与 vendor 配置分区，不能套用其他版本的 mtd 编号。
对确定的分区只读导出，例如将下面的 X、SSH_PORT 和 ROUTER 替换为实测值：

```sh
ssh -p SSH_PORT root@ROUTER 'cat /dev/mtdX' > OWNER_PARTITION.bin
sha256sum OWNER_PARTITION.bin
```

检查文件长度等于 /proc/mtd 的十六进制分区大小，并再次独立读取计算 SHA256，
两次一致后保管在至少另一份离线副本中。不要执行 mtd write、erase、nandwrite
或回写导出文件。备份结束将 Dropbear 开关恢复原值。

这些是厂商驱动提供的逻辑分区备份，不自动包含未暴露的物理保留尾部或 OOB。
不要据此声称已经得到了完整物理 NAND 镜像。

## RAM 首装器的迁移前备份

本节仅适用于旧 RC2 / `host` 模式，不是新 automatic 镜像的必需步骤。

新 factory-web 包的 RAM 首装流程另有 prepare 阶段，读取现代只读物理视图中的：
完整另一原厂槽 50 MiB、vendor 状态 83.5 MiB、ART 3.5 MiB、bootloader 0.5 MiB、
原厂保留尾部 64 MiB，以及本次设置和设备恢复资料。
它生成 age 加密归档，并使用所有者提供的 identity 实际解密、逐字节核对，
成功后才允许 provision。该备份是 ECC main-data，不是 raw/OOB 镜像。

参考 [旧版首装步骤](host-first-install.md)。每台设备使用自己的备份与密钥；
不要使用本项目实验机的备份，也不要把会话目录、age identity 或任何私钥上传 GitHub。

## 从独立 SSH 恢复环境回原厂

这里使用 RAM 首装器 prepare 生成的同一会话中的 stock-slot.bin 和
vendor-state.bin。它们的 SHA256 已写进该设备自己的恢复资料；普通下载包、
另一台设备的备份或不匹配的旧快照会被原生写入器拒绝。

先从正常 OpenWrt 使用兼容 sysupgrade 包执行 dpn-enter-recovery，确认
/etc/dpn-vault-source 为 NAND_DEVICE_BOUND_VAULT、/tmp/dpn-vault-recovery.ready
存在，主 UBI 未挂载。电脑直连 LAN，断开上联，使用已保存的所有者密钥。
将上述两个文件上传到恢复环境的 /tmp，核对长度分别为 52428800 和 87556096。
该操作会替换正常系统及原厂 vendor 状态，因此先另行保存当前 OpenWrt 配置。

下面在已确认的恢复 root shell 执行。snapshot 不擦写，--write 是实际写入：

```sh
. /lib/upgrade/dpn-layout4-upgrade.sh
dpn_l4_reload stock_return=1
REC_SHA=$(sha256sum /dev/mtd2ro); REC_SHA=${REC_SHA%% *}
/usr/libexec/dpn-expanded-stock-return --snapshot /tmp/stock-slot.bin /tmp/vendor-state.bin "$REC_SHA" /tmp/return-stock.guard
/usr/libexec/dpn-expanded-stock-return --write /tmp/stock-slot.bin /tmp/vendor-state.bin "$REC_SHA" /tmp/return-stock.guard
```

只有最后明确打印 EXPANDED_STOCK50_AND_VENDOR83_5_COMMITTED_HEADER_LAST_RECOVERY_VAULT_ART_BMT_PROTECTED
且进程返回 0，才能选择原厂槽。先生成规范化 ART 校验值，再调用受限选槽工具：

```sh
dd if=/dev/mtd0 of=/tmp/return-stock.ART bs=262144 skip=1778 count=14
printf 0 | dd of=/tmp/return-stock.ART bs=1 seek=3407872 conv=notrunc
DPN_L4_ART_SHA=$(sha256sum /tmp/return-stock.ART); DPN_L4_ART_SHA=${DPN_L4_ART_SHA%% *}
dpn_l4_select 0
sync
reboot
```

保持隔离直连，待原厂 DHCP/网页恢复。任何命令失败都不要继续下一条，也不要重复
写入；独立恢复保持被选中。此路径保留紧凑恢复，并非将整颗 NAND 清零或恢复为
逐字节出厂镜像。已有恢复资料时可重装紧凑恢复，但再次使用完整 factory-web
首装包会重新开始首装流程，需要先保存当前所有者资料。
