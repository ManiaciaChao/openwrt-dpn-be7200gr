# 原厂 Web 升级：UMMtk、校验及槽位离线分析

日期：2026-11-07，Asia/Singapore。本报告主体记录当时仅离线分析的结论；后续已开展实机认证 Web 主槽重刷。最新实机条件、选槽限制、两种制品和恢复边界见 [原厂 Web 重刷与恢复](factory-web-and-recovery.md)。不要把下文离线范围声明当作项目此刻的设备状态。

结论：本版原厂 Web 接收的是 UMMtk 多段容器。固件校验使用总载荷和每段的原始 16 字节 MD5，以及长度/类型检查；追踪到的固件路径没有厂商公钥数字签名或型号匹配检查。原厂 AArch64 校验函数在 QEMU 中接受合成文本载荷，说明格式校验不保证载荷能够启动。正常 Web 后处理根据 `/tmp/imageActive` 的相反值选择槽位，再尝试修改物理 bootflag 并写 imageCommit，最后请求重启。因此适合作为“原厂 Web 首次安装包”的研究基础，但不能直接上传 OpenWrt sysupgrade tar，也不能据此次离线结果宣布硬件刷写成功。

## 固定分析对象与复现证据

原厂 profile：`lan_10G_4port_7581_config_dlink_singtel`，构建标识 `260317_1135`。分析对象来自原厂逻辑备份的 SquashFS，不含当前设备运行状态推断。

| 文件 | SHA-256 |
|---|---|
| lib/libumlib_devctl.so | 72de151857ae1a36b3d1aa2f6ec2109a47bbae7fd308cd75ee083e5877c468dc |
| usr/sbin/httpd | 35b979c2762d5f929ce6a7c1b955388ea498c4d06719cfa44961fef18d41e708 |

工具为 `tools/audit_stock_web_upgrade.py` 和 `tools/stock_web_offline_harness.c`；结果为 `artifacts/stock-web-upgrade/offline-validation.json`。30 项检查全部通过。

验证方法：静态 AArch64 C harness 手工加载上述 ELF，完成数据重定位，在 QEMU user-mode 下调用原厂函数。原厂 `.init` 不执行；未知导入终止运行；system/cmsUtl_doSystem、文件打开、重启和目标写入都是无副作用桩。libumlib_devctl 的真实 MTD helper（0xbf20）被记录桩替换；内存查询及日志也被替换。调用 HTTP do_upload_post 时，当前槽与写入函数均为桩；单独调用底层 glue_writeImageBuf 时执行真实分派代码。没有执行真实 Flash ioctl/pwrite，没有验证实际 NAND/ECC/BMT、掉电恢复或首次启动。

合成测试内容是显式标注 NOT ROUTER FIRMWARE 的文本，暂存在 /dev/shm，测试结束自动删除。没有把本机 FIP、校准或凭据封装成可刷 Web 文件。私有反汇编在 `firmware/private/network-shell-audit/`，可从上述固定文件重新生成。

## 页面和 HTTP 链路

- `/webs/ctuploadfw.html`：multipart/form-data POST，目标 `ctuploadfw.cgi`，文件字段 `filename`。
- `/webs/ctuploadfwslave.html`：表单也 POST 到同一个 `ctuploadfw.cgi`。页面名不等同于强制写备用槽。
- `/webs/ctuploadbackupfw.html` 虽有单独表单，但本次 httpd 路由字符串未证实注册它的后端，不能据静态 HTML 假定可用。
- httpd 的请求处理会从 Referer 识别普通升级/“slave”升级类型。正常上传预处理分别设置后处理格式 3/8。读取当前槽成功时，实际选槽优先于这两个格式值。
- 固件路径：`upLoadImage`（0x4134e8）解析 multipart、分配 RAM、读入载荷 → `do_upload_pre`（0x41402c）识别配置文件或固件 → `devCtl_validateImageBuf` → 可选版本比较 → 返回状态 → `do_upload_post`（0x4145c4）写入及请求重启。
- `cmsImg_validateImage` 在此用于识别/验证配置文件；返回未识别后才进入 UMMtk 固件校验。配置解码/AES 分支属于配置上传，不是已识别 UMMtk 的必经解密步骤。
- Nginx 原配置是 443 → localhost:8080，`client_max_body_size 80M`。上传解析还依赖可分配 RAM、正确 multipart boundary、正常认证会话等；此次未做整条 HTTP 请求实测。

## UMMtk 二进制布局

下列数字均为字节偏移。多字节整数字段按网络字节序（大端）解释。名称为根据使用方式起的描述，不声称取得原厂 C 结构定义。

总结构：`200 字节主头 + N × 204 字节分段描述 + 载荷区`。

| 主头偏移 | 大小 | 已确认用途 |
|---|---:|---|
| 0x00 | 64 | magic 字符串区域；校验只比较开头五字节 `UMMtk` |
| 0x40 | 64 | 本校验函数未检查的区域，真实字段名未知 |
| 0x80 | 64 | 摘要区域；仅前 16 字节用于与总载荷 MD5 原始二进制比较，其余 48 字节未检查 |
| 0xc0 | 4 | 声明总长度 L，包含主头和分段表 |
| 0xc4 | 4 | 分段数 N |

第 i 项分段描述起点 D = 0xc8 + i × 0xcc：

| 相对 D 偏移 | 大小 | 用途 |
|---|---:|---|
| 0x00 | 64 | Name，仅用于打印；未发现将其与设备型号匹配 |
| 0x40 | 64 | Magic/类型，用于允许列表及写入分派 |
| 0x80 | 64 | 摘要区域；仅前 16 字节用于本段 MD5 原始二进制比较 |
| 0xc0 | 4 | 本段开始偏移 S，相对整个 UMMtk 文件起点 |
| 0xc4 | 4 | 本段结束偏移 E，包含此字节 |
| 0xc8 | 4 | 本段长度 B |

日志将摘要称作 Ecc，但代码实际调用 MD5Init/MD5Update/MD5Final；它不是 NAND ECC，也不是 hex 文本摘要。bintostr 只用于打印摘要，不参与编码比较。

## 校验规则与未检查内容

`devCtl_validateImageBuf`：0x590c..0x5f94；`glue_validateImageBuf`：0xc9cc..0xcaec。非零失败码通常为 9851，成功为 0。

对于正常有界输入，函数行为为：

1. 检查非空、输入长度超过 200 字节、声明长度不大于输入，以及分段表规模。
2. magic 前五字节必须精确为 `UMMtk`。
3. 每项检查 S < E、范围在输入内、E − S + 1 = B，以及 S + B 不超过输入。有效段至少两字节。
4. 令 P = 200 + 204N，要求 P + 所有 B 的和等于 L。
5. 总摘要为 MD5(file[P:L])；每段摘要为 MD5(file[S:S+B])。摘要均为 16 字节原始值。
6. 每段 Magic 不区分大小写，必须属于 `oneimage`、`verinfo`、`tcboot`、`tclinux`、`um_ext`。writer 虽有 osgi/reservearea/romfile 分支，这些类型在本版前置校验中被拒绝。

QEMU 用真实函数验证：正常合成文本通过；修改 magic、载荷、总 MD5、段 MD5 或破坏 end/length 关系均拒绝；Name、主头 0x40 区及摘要后部保留区变化仍接受；TCLINUX 大写接受；osgi/未知类型拒绝。输入尾部附加不计入 L 的字节也接受。

这些规则不构成可信签名：摘要由上传文件自己携带，可随内容重新计算；描述表不在总 MD5 覆盖内。代码也未强制每段按表顺序紧密排列、互不重叠。校验函数没有核验 tclinux 内部的 FIP/HDR2/FIT、设备树、校准或 Flash 布局。小于/畸形边界、整数溢出和不终止字符串不是本轮内存安全审计范围；主机 inspector 对输入施加了明确边界，不应把它当成逐条复现所有异常行为的模拟器。

## 版本限制（修正早期仅凭字符串的判断）

`versioncompresstest`（0x413e48）遍历 Magic 为 verinfo 的段，最多读取 63 字节作为新版本字符串，与 MDMOID_IGD_DEVICE_INFO 中的当前软件版本比较。比较器为 0x413be8：跳过前缀至数字，按 `%d.%d%9s` 解析主/次版本及后缀数字。

- 比较结果为负才返回 9849；相同版本返回 0。日志中的 `==` 字样不等于拒绝相同版本。
- 没有 verinfo 段时，循环结束返回 0；verinfo 不是该函数的必需字段。
- do_upload_pre 检查本地 `/tmp/lowversion`：文件存在时跳过版本比较。本轮没有创建该文件，也不需要依赖它。
- 已用原厂版本函数在 QEMU 验证新 1.1/当前 1.2 拒绝，新 1.2/当前 1.2 接受，新 1.3/当前 1.2 接受，以及不含 verinfo 接受。这不代表已验证所有厂商版本命名格式。

## 实际选择哪个槽

`do_upload_post` 0x414624..0x414708 调用 `devCtl_getCurrentBootPartition`；该函数并非直接查询 rootfs，而是调用 `glue_getCurrentBootPartition`（0xc518），读取 `/tmp/imageActive` 中的一字节 ASCII 0/1。

| 获取结果 | 当前槽值 | HTTP 选择函数 | tclinux 段实际目标 | 随后尝试设置 bootflag |
|---|---:|---|---|---:|
| 成功 | 0 | devCtl_writeImageBufSlave | tclinux_slave | 1 |
| 成功 | 1 | devCtl_writeImageBuf | tclinux | 0 |
| 失败 | 无 | 通常 devCtl_writeImageBuf | tclinux | 0 |
| 失败，后处理格式为 8 | 无 | devCtl_writeImageBufSlave | tclinux_slave | 1 |

以上四个 HTTP 分支已在 QEMU 执行原厂 do_upload_post 验证。成功路径与格式 3/8 无关；读取当前槽失败才使用格式 8 作为备用槽分支。

um_core 的 init_imageState（0x40657c..0x4065b0）调用 glue_getBootflag，再调用 glue_setCurrentBootPartition 初始化 `/tmp/imageActive`。前者经 `ecnt_sys get bootflag` 读取标志，后者写临时文件。不能在“手动指定另一槽启动/临时改 bootargs”的实验环境中，仅凭实际 root 分区推断该文件或 Web 写入目标；本轮没有读取设备当前值，也没有断言主会话此刻会被写入哪个槽。

## 底层写入和副作用

`devCtl_writeImageBuf`（0x58e4）调用 glue_writeImageBuf(buf,len,0,1)；Slave（0x58f8）调用 glue_writeImageBuf(buf,len,1,1)。第三参数选目标槽，第四参数允许更新启动标志。

`glue_writeImageBuf`（0xcaf0..0xd484）遍历 Magic，按段处理：

- tclinux：取 file[S:S+B]，目标参数 0 → `tclinux`，1 → `tclinux_slave`。写入的是段载荷，不包括 UMMtk 外壳。
- 然后调用 glue_setBootflag(target)；经临时 `/tmp/image_boot_flag` 执行 `ecnt_sys set bootflag ...`。这是尝试修改持久 bootflag，不只是临时启动变量。
- 随后 glue_setImageCommit(target) 写 scratchpad 的 imageCommit（本版路径为 `/extcfg/config/scratchpad/imageCommit`），内容为 ASCII 0/1。
- verinfo：更新所选槽的 imageVersion0/1 元数据，不写 tclinux 内容。
- um_ext：另行写 `um_ext`，不随主/备槽切换。
- tcboot：会进入独立的 bootloader 擦写分支。这是升级包可触及的敏感目标，首次安装包没有理由包含它。
- oneimage：前置校验接受，但本版 writer 没有对应的实际写入分支；QEMU 验证为成功返回但零目标写入。因此不能把“oneimage 校验通过”当成能够安装。

tclinux/um_ext 使用内部 helper 0xbf20：按分区名枚举 MTD，检查可写标志及长度，O_RDWR|O_SYNC 打开字符设备，以擦除块逐块 MEMERASE 后 pwrite，最后 fsync。无整槽备份/回读哈希，也没有 header-last 提交策略；首块先擦写。擦除 EIO/SPI-NAND 分支会移动目标及源偏移跳过对应块，这与项目自建的受保护 writer 语义不同；本轮未验证非空坏块情况下的兼容性。

重要限制：helper 发生 open/erase/pwrite 等错误会打印并返回，但上层 tclinux 分支没有检查其结果，仍继续 bootflag/imageCommit。QEMU 将 helper 替换为返回 -1 的桩后，原厂分派代码仍设置标志并返回成功。glue_setBootflag 对 shell 命令返回值也不作成功验证。因此 Web 返回成功或请求重启不能证明写入完整。

do_upload_post 在 writer 返回 0 后调用 cmsUtil_sendRequestRebootMsg；不是通过页面轮询才触发写入。不得把“只上传看看报错”视为只读预检。

## 对首次安装方案的含义

UMMtk 外壳已经有明确可复现的字段与校验依据，不需要假设取得未知的 Web 签名私钥。候选包应只包含必要的 tclinux/版本元数据，并使用已经独立验收的本机启动镜像；OpenWrt sysupgrade tar 是另一种格式。UMMtk 的 MD5 校验不能替代内部 FIP/HDR2/FIT 校验和板型/布局检查。

仍未完成的工作是把“首次安装的布局、按机校准、配置迁移、槽位策略与恢复”整合成可交付方案，并证明厂商写入器能按预期保存本机现有保护区。特别是从现有主槽 OpenWrt 临时启动备用原厂后上传，可能覆盖另一槽的当前 OpenWrt；是否如此取决于原厂 `/tmp/imageActive`，不能直接套用“备用槽安全测试”的说法。

本报告证明格式/用户态控制流，不是实际 Web 安装验收，也不改变主会话的刷写授权或当前设备状态。
