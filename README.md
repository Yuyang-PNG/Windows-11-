# Windows-11-WinOpt

> **Windows 原生深度优化工具箱**
> 
> 全部调用 Windows 内置 API / 命令，零第三方依赖，一行命令远程执行，不落硬盘。

这不是网上抄来抄去的"清理垃圾/加速球"套路。这里收集的是 **只有老系统管理员才知道的冷门调参**——从 NTFS 内核缓存、TCP 拥塞控制算法、多媒体调度器到进程优先级绑定，全部走微软原生接口。

---

## 仓库脚本

| 脚本 | 定位 | 交互方式 |
|------|------|----------|
| `Windows 11.ps1` | 深度优化工具 v2.4 | 一次性问卷（21 项优化 + 10 款软件下载） |
| `WinTune.ps1` | 系统管理套件 v2.1.0 | 循环主菜单（17 个功能模块） |

---

## 一行命令执行（内存执行，不下载）

管理员 PowerShell 终端粘贴：

```powershell
$ProgressPreference='SilentlyContinue'; irm https://www.yulaoshi.xyz/tools/Windows%2011.ps1 | iex
```

> `irm ... | iex` = 下载到内存直接解释执行，**不保存本地文件**，不污染系统。

---

## `Windows 11.ps1` — 深度优化工具 v2.4

### 三层优化架构

| 层级 | 说明 | 项目数 |
|------|------|--------|
| **基础优化层** | v2.2 核心，建议全选 | 7 项 |
| **冷门增强层** | v2.3 新增，按需选择 | 8 项 |
| **极限冷门层** | v2.4 新增，谨慎选择 | 5 项 |

### 优化项目详解

| 编号 | 名称 | 原理 |
|------|------|------|
| 01 | 文件系统层优化 (NTFS) | `disablelastaccess` / `disable8dot3` / `memoryusage 2` / `mftzone 2` / `disabledeletenotify 0` |
| 02 | 网络传输层优化 (TCP/IP) | `autotuninglevel=experimental` / `rss=enabled` / `congestionprovider=ctcp` / 禁用 chimney/timestamps/ECN |
| 03 | 内存管理层优化 (MMAgent) | 禁用内存压缩 / 页面合并 / 预启动，启用应用启动预取 |
| 04 | 调度器层优化 | `Win32PrioritySeparation=0x18`，前台程序获得更多时间片 |
| 05 | 多媒体调度层优化 | `SystemResponsiveness=10`，仅保留 10% CPU 给多媒体 |
| 06 | 启动/时钟层优化 (BCD) | `disabledynamictick` / `useplatformtick` / `tscsyncpolicy=enhanced` |
| 07 | 电源层优化 | 解锁并激活"卓越性能"电源计划，禁用核心停车 |
| 08 | I/O 与磁盘调度层优化 | 禁用 SysMain(Superfetch) / 优化 IRQ 优先级 |
| 09 | 内核与中断层优化 | `LargeSystemCache=1` / `DisablePagingExecutive=1` |
| 10 | 网络深层优化 (DNS/缓存) | DNS 缓存 TTL / 负缓存清零 / TCP 重传次数 / SACK |
| 11 | 服务精简 | 禁用诊断跟踪服务 `DiagTrack` / `dmwappushservice` |
| 12 | 图形与显示层优化 | 禁用 GameDVR / 全屏独占优化 |
| 13 | 资源管理器响应优化 | 缩略图缓存 / 文件夹类型 / 托盘自动隐藏 |
| 14 | CPU 调度深层优化 | 电源计划核心停车 / USB 挂起 / 性能提升模式 |
| 15 | Windows Update 优化 | 禁用 Delivery Optimization P2P 更新 |
| 16 | 系统维护任务 | `lodctr /R` 重建性能计数器 / `ProcessIdleTasks` |
| 17 | 进程与句柄限制提升 | `MaxFreeTcbs` / `MaxHashTableSize` 扩大到 65536 |
| 18 | 文件系统与预读优化 | 禁用 Prefetcher / Superfetch / 自动布局 |
| 19 | 系统响应与延迟优化 | 启动延迟归零 / DPC Watchdog 关闭 / 游戏调度类别=High |
| 20 | 后台与隐私精简 | 禁用遥测 / 同步通知 / 远程协助 / 终端服务 |
| 21 | 高级网络微调 | TCP 窗口 64240 / 每服务器最大连接 16 / LanmanServer 优化 |

### 智能下载引擎

运行时可选择下载 10 款常用工具，支持**多镜像源自动测速选源**：

- Google Chrome / EdgeBlocker / 7-Zip / Everything
- VLC / Notepad++ / TranslucentTB / HWiNFO
- Process Hacker 2 / WinRAR

下载前自动测试源可用性，5 分钟超时保护，文件大小异常检测。

---

## `WinTune.ps1` — 系统管理套件 v2.1.0

交互式主菜单，17 个独立模块：

| 编号 | 模块 | 功能 |
|------|------|------|
| 1 | 一键游戏与开发环境优化 | 自动绑定 30+ 常见进程（Steam、VS Code、Node、浏览器、编译器等） |
| 2 | 自定义进程优先级绑定 | 通过 `Image File Execution Options` 永久指定 CPU/IO/电源节流优先级 |
| 3 | 查看已绑定的优先级 | 列表展示所有已绑定进程及其优先级 |
| 4 | 移除优先级绑定 | 删除指定进程的 `PerfOptions` 注册表项 |
| 5 | 设置进程 CPU 亲和性 | 限定进程运行在指定物理核心 |
| 6 | 启用游戏专注模式 | 关 GameDVR、停非必要进程、切高性能电源、全屏优化 |
| 7 | 深度系统清理 | 停后台进程、禁用服务、清 Temp/Prefetch/INetCache/WinSxS |
| 8 | 存储优化与健康检查 | SSD TRIM、大文件扫描（>500MB）、物理磁盘健康状态 |
| 9 | 管理启动项 | 注册表 Run 项 + 计划任务启动项查看与禁用 |
| 10 | 高级系统性能调优 | NTFS / TCP / 多媒体 / 内存 / 电源 / 休眠 综合调优 |
| 11 | 网络优化与 DNS | 切换 DNS（Cloudflare/Google/Quad9/阿里/自定义）、刷新 DNS、重置网络栈 |
| 12 | Windows Update 管理 | 检查/安装/暂停 7 天/恢复/设置活跃时段 |
| 13 | 隐私安全加固 | 遥测/Cortana/活动历史/广告ID/位置/Defender 全面禁用 |
| 14 | 右键菜单管理 | 添加/移除"用 VS Code 打开"/"在此处打开 PowerShell"/"复制为路径" |
| 15 | 实时硬件监控 | 类 Linux `top` 实时刷新，支持 OpenHardwareMonitor 温度传感器 |
| 16 | 系统信息报告 | OS/CPU/内存/显卡/存储/网络/运行时间完整输出 |
| 17 | 查看操作日志 | 查看 `%TEMP%\WinTune-Pro.log` 最近 50 条 |

### 安全机制

- **自动创建系统还原点**：每项关键修改前调用 `Checkpoint-Computer`
- **注册表自动备份**：修改前导出 `.reg` 到 `%TEMP%\WinTune-Backups`
- **完整日志记录**：所有操作写入 `%TEMP%\WinTune-Pro.log`

---

## 核心技术原理

### 进程优先级绑定（Image File Execution Options）

Windows 从 NT 3.1 就支持的机制，但 99% 的用户不知道。在注册表：

```
HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\程序名\PerfOptions
```

写入 `CpuPriorityClass` 和 `IoPriority`，**系统调度器在创建进程时自动应用**，不需要后台常驻工具。

- `CpuPriorityClass`: 1(Idle) ~ 10(Realtime)
- `IoPriority`: 0(Low) ~ 3(Critical)

### NTFS 文件系统层优化

| 命令 | 作用 |
|------|------|
| `fsutil behavior set disablelastaccess 1` | 禁用"最后访问时间"更新，遍历大目录时减少磁盘 IO |
| `fsutil behavior set disable8dot3 1` | 禁用 DOS 短文件名生成，大目录响应更快 |
| `fsutil behavior set memoryusage 2` | 扩大 NTFS 内核缓存池，频繁文件操作减少内核态等待 |
| `fsutil behavior set mftzone 2` | 预留 400MB MFT 区域，减少主文件表碎片化 |

### TCP/IP 网络栈优化

| 命令 | 作用 |
|------|------|
| `netsh int tcp set global congestionprovider=ctcp` | 切换为 Compound TCP，高带宽延迟网络更激进 |
| `netsh int tcp set global autotuninglevel=experimental` | 窗口缩放开到最大 |
| `TcpNoDelay = 1` | 禁用 Nagle 算法，降低交互延迟 |
| `TcpAckFrequency = 1` | 立即 ACK，不再延迟 200ms 凑批量 |

### 多媒体调度器

`SystemResponsiveness` 默认保留 20% CPU 给多媒体播放，改为 10%，让更多 CPU 给前台游戏/程序。

### 卓越性能电源计划

微软隐藏的电源方案，比"高性能"更激进：禁用核心停车（Core Parking）、最小化 C-State、睿频零延迟响应。

---

## 仓库结构

```
Windows-11-WinOpt/
├── Windows 11.ps1          # 深度优化工具 v2.4（交互式问卷）
├── WinTune.ps1             # 系统管理套件 v2.1.0（循环菜单）
├── README.md
└── .github/
    └── workflows/            # （可选）CI 自动发布
```

---

## 安全与还原

### 执行前自动备份

`Windows 11.ps1`：
- BCD 启动配置 → `Desktop\WinOpt_Backup_时间\bcd_backup.bcd`
- 注册表 PriorityControl → `PriorityControl.reg`
- 注册表 Tcpip\Parameters → `TcpipParameters.reg`

`WinTune.ps1`：
- 系统还原点：`WinTune Pro Auto-Backup`
- 注册表备份：`%TEMP%\WinTune-Backups\*.reg`

### 手动还原

BCD 还原：
```powershell
bcdedit /import "$env:USERPROFILE\Desktop\WinOpt_Backup_xxx\bcd_backup.bcd"
```

注册表还原：
```powershell
reg import "$env:USERPROFILE\Desktop\WinOpt_Backup_xxx\PriorityControl.reg"
```

---

## 系统要求

- Windows 10 1607+ / Windows 11
- PowerShell 5.1 或 PowerShell 7.x
- 管理员权限（脚本头部 `#Requires -RunAsAdministrator`）

---

## 免责声明

本仓库脚本仅用于学习 Windows 系统底层机制与 API 调用。

修改系统配置存在风险，请自行承担。建议先在虚拟机测试。

作者不对任何因使用本脚本导致的系统问题负责。

---

## 相关阅读

- [Microsoft Docs: Image File Execution Options](https://learn.microsoft.com/windows-hardware/drivers/debugger/gflags-overview)
- [Microsoft Docs: TCP/IP Performance Tuning](https://learn.microsoft.com/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning)
- [Microsoft Docs: Powercfg Command-Line Options](https://learn.microsoft.com/windows-hardware/design/device-experiences/powercfg-command-line-options)
