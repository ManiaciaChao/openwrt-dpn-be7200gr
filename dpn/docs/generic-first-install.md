# DPN-BE7200GR 安装与升级（layout4）

本分支的目标是原厂 Web 首刷和标准 OpenWrt 升级。保留原厂 bootloader、
16 MiB 独立 SSH 恢复、4 MiB 每机恢复资料、ART 与末尾 64 MiB 原厂保留区；
408 MiB 原始空间提供给 UBI。软件和配置位于标准 SquashFS/UBIFS overlay。

当前单机已验证扩容、标准升级、SSH 恢复、完整回原厂、原厂 Web 重装恢复和再次迁移，
包括移除 TTL 后的物理冷启动。新的通用 RAM 首装包已经实现并打包，
其独立全流程硬件验收尚未完成；不得把旧版 Web 测试当作新包的测试。
支持范围仅为已记录的原厂 260317_1135 / AN7581 配置及 FORESEE F35SQB004G
CD:53:53、512 MiB、4096+256 页/OOB、256 KiB 擦除块、空 BMT/RAWB、零坏块。
其他状态拒绝现代 NAND 写入；当前没有为其他配置提供兼容承诺。

## 两个固件文件

| 文件 | 用途 |
| --- | --- |
| dpn-be7200gr-factory-web.bin | 在原厂正常 Web 升级页上传，启动 RAM 首装环境 |
| dpn-be7200gr-sysupgrade.bin | 已安装 layout4 的 OpenWrt 后续升级，保留配置 |

两者正常系统载荷必须一致，打包器会比对内核 FIP 与基础根文件系统 SHA256。
不向原厂 Web 上传 sysupgrade，不向 layout3 旧实验系统上传 layout4 升级包。
设备的原厂备份、MAC、校准、密码、所有者公钥和 SSH 私钥不包含在公开包中。

## 首次安装

1. 先导出所有者自己的原厂备份，参考 [原厂备份](stock-backup.md)。
   准备电脑上的 Python 3、OpenSSH、age 与 age-keygen，并保管自己的 SSH 私钥。
2. 电脑直连路由器 LAN1，断开路由器 WAN 与其他上联。不要接共享交换机进行默认
   DHCP 首装；安装期间保持供电。
3. 用正常原厂网页账户登录固件升级页，上传 factory-web 一次，等待重启。
   原厂系统决定写另一槽，包中不强制选槽；不要因 HTTP 连接关闭重复上传。
4. 打开 http://192.168.1.1/ 的 LuCI，设置 root 密码，在“系统 → 管理权”加入自己的
   SSH 公钥。WAN、无线保持关闭。此时系统和设置都在 RAM，尚未进行布局迁移；
   重启会丢失本次设置。
5. 在这条物理隔离链路上核对并记录设备的 Ed25519 SSH 主机指纹，写入自己的
   known_hosts 文件。安装工具使用严格主机身份检查，不关闭 host-key 校验。
6. 运行仓库提供的首装工具。以下参数在每个阶段重复，具体地址、文件由所有者填写：

```sh
python3 tools/first-install/layout4_install.py prepare \
  --host 192.168.1.1 --identity OWNER_SSH_PRIVATE_KEY --known-hosts OWNER_KNOWN_HOSTS \
  --session OWNER_PRIVATE_SESSION --age-recipient OWNER_AGE_RECIPIENT \
  --age-identity OWNER_AGE_IDENTITY_FILE
```

prepare 会读取每台设备自己的原厂完整槽、vendor 状态、bootloader、ART 和
保留尾部，导出加密备份并实际解密逐字节比对。恢复资料在目标设备外私有生成，
使用该设备的校准指纹和独立 SSH 身份。此阶段不写 Flash。
会话目录内也有原始私有文件，应保存在受保护的本地磁盘，不能提交仓库。

备份验证通过后，使用相同 host/identity/known-hosts/session 参数运行
`install --execute`。它会自动完成恢复安装、重启到恢复、迁移、正常重启与验收；
不会重试失败的写入。

下面是诊断时使用的分阶段等价操作，普通安装不需要逐个执行：

```text
provision --execute
boot-recovery --execute
migrate --execute
boot-normal --execute
verify
```

每次 boot 后等待原地址的 SSH 恢复再执行下一阶段。provision 只写紧凑恢复和
设备专属资料，完整回读后选择恢复启动。migrate 必须在真正从 NAND 启动、
同一 SSH 身份可达的独立恢复环境里运行，随后才格式化 408 MiB 数据区、安装
基础系统和设置，并以 header-last 写入主内核。verify 核对正常 overlay、
基础系统、所有者身份和保护区。

阶段开始采用排他事务记录。出错或连接中断后不要删记录、自动重试、重复上传包；
先查看该会话的私有日志与设备上已有作业。恢复材料保留在电脑上，不能只存在路由器中。

## 后续升级与恢复

通过 LuCI 或 sysupgrade 使用 layout4 sysupgrade 包。升级保存设置，要求配置中
保有自己的 SSH 公钥和有效主机密钥。当前不支持 sysupgrade -n、清空配置后的
自动重新认领或任意旧布局迁移。

独立恢复使用 LAN 静态 192.168.1.1、密钥 SSH，不提供 DHCP、无线或 Web。
恢复不依赖主 overlay。正常系统可通过 dpn-enter-recovery 与兼容升级包进入它。
回原厂使用每台设备自己的外部原厂完整槽和 vendor 备份，不发布本机原厂 dump，
也不能把普通 OEM 下载升级包视为完整原厂备份。

原厂 bootloader、ART/BMT 损坏或任意写入中断都不属于已保证的恢复范围。
当前要求安装和升级持续供电，未做故意物理断电测试。
