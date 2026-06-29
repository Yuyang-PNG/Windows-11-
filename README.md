# 智优进程管理器

智能Windows进程优先级分配工具，基于机器学习的自动化进程优化系统。

## 版本信息

**v1.2.3**

## 项目简介

智优进程管理器是一个Windows进程优先级分配工具，主要用来自动优化系统资源分配。平时玩游戏的时候经常遇到卡顿，发现是后台进程抢占了资源，于是就写了这个工具来解决问题。

## 核心架构

```
智优进程管理器/
├── core/                  # 核心模块
│   ├── classifier.py      # 应用分类器
│   ├── scorer.py          # 优先级评分引擎
│   ├── gpu_manager.py     # GPU管理
│   ├── cache.py           # TTL缓存
│   ├── logger.py          # 日志系统
│   ├── alerting.py        # 告警系统
│   ├── constants.py       # 常量定义
│   ├── singleton.py       # 单例模式
│   ├── di_container.py    # 依赖注入容器
│   ├── nvidia_optimizer.py # NVIDIA优化器
│   └── gui_manager.py     # GUI管理
├── ml/                    # 机器学习模块
│   ├── scoring_model.py   # ML评分模型(RandomForest)
│   ├── smart_classifier.py # 智能分类器(TF-IDF+NB)
│   ├── auto_trainer.py    # 自动训练器
│   ├── feature_engineering.py # 特征工程
│   └── models/            # 模型文件存储
├── config/                # 配置文件
│   ├── app_categories.yaml # 应用分类配置
│   ├── scoring_rules.yaml  # 评分规则配置
│   └── cross_factors.yaml  # 交叉因子配置
├── monitoring/            # 监控模块
│   ├── history_manager.py  # 历史数据管理
│   ├── performance_counter.py # 性能计数器
│   └── network_monitor.py  # 网络监控
├── api/                   # Flask API
│   ├── app.py            # API服务
│   └── async_app.py      # 异步API
├── dashboard/             # Web界面
│   └── index.html
├── .github/workflows/     # GitHub Actions
│   ├── build.yml         # 构建工作流
│   └── sign.yml          # Sigstore签名工作流
└── process_priority_manager.py # 主入口
```

## 主要功能

### 智能进程分类

支持13种应用类型自动识别：
- 游戏 (gaming) - Steam、Epic、原神、明日方舟等100+游戏
- 视频 (video) - VLC、PotPlayer、在线视频
- 浏览器 (browser) - Chrome、Edge、Firefox
- 办公 (productivity) - Office、WPS、钉钉、飞书
- 开发 (development) - VS Code、IntelliJ、PyCharm
- 设计 (design) - Photoshop、Blender、Premiere
- AI/机器学习 (ai) - Python、TensorFlow、PyTorch
- 系统 (system) - Windows系统进程
- 安全 (security) - 杀毒软件、防火墙
- 工具 (utility) - 工具软件
- 通讯 (communication) - 微信、QQ、Discord
- 音乐 (music) - Spotify、网易云音乐
- 云存储 (cloud) - OneDrive、Dropbox

### 机器学习评分系统

**双模型架构：**
1. **ML评分模型** (RandomForestRegressor)
   - 基于CPU、内存、线程数、IO、运行时长等特征
   - 自动学习最优评分策略
   - 支持增量训练

2. **智能分类器** (TF-IDF + NaiveBayes)
   - 进程名、路径、窗口标题、厂商名多特征
   - 高置信度预测
   - 规则引擎兜底

### 评分算法

优先级根据多维度因素计算：

| 因素 | 权重 | 说明 |
|------|------|------|
| CPU占用 | 25% | 越高越重要 |
| 内存占用 | 20% | 越高越重要 |
| 进程类型 | 15% | 游戏/AI/设计高优先级 |
| 线程数 | 10% | 越多越重要 |
| I/O活动 | 10% | 越高越重要 |
| 系统负载 | 10% | 高负载时降低其他进程 |
| 运行时长 | 7% | 新启动进程优先 |

### 性能模式

支持三种性能模式，适应不同配置电脑：

| 模式 | 线程数 | 扫描间隔 | 详细分析 | GPU检测 |
|------|--------|----------|----------|---------|
| 快速(fast) | 2 | 300秒 | 否 | 否 |
| 平衡(balanced) | 4 | 180秒 | 是 | 是 |
| 彻底(thorough) | 8 | 60秒 | 是 | 是 |

### 系统托盘

- **双击EXE**：直接最小化到系统托盘常驻后台
- 鼠标悬停显示状态信息
- 右键菜单：查看状态、立即优化、查看游戏、NVIDIA一键优化、打开主窗口、查看服务、退出

### 智能游戏检测

- 监控100+种游戏进程
- 检测到游戏启动时自动优化
- 5分钟冷却机制
- 轻量级优化（快速模式）

### GPU管理

- 自动识别独立显卡/集成显卡
- 根据应用类型推荐GPU使用方式
- 游戏和设计软件推荐使用独立显卡
- 支持NVIDIA、AMD、Intel显卡

### NVIDIA 一键优化

**新增功能**：一键优化 NVIDIA 控制面板设置

| 预设 | 适用场景 | 说明 |
|------|----------|------|
| 竞技低延迟 | CS2、Valorant、LOL、APEX | 最低延迟 + 最高帧率 |
| 3A画质平衡 | 赛博朋克2077、艾尔登法环 | 画质与性能平衡 |
| 恢复默认 | 恢复原始设置 | 一键还原 |

**优化项目**：
- 低延迟模式: Ultra
- 电源管理模式: 最高性能优先
- 纹理过滤-质量: 高性能
- 各向异性过滤: 16x
- 垂直同步: 应用程序控制

### GUI 主窗口

新增可视化主窗口，包含：
- 系统状态显示（CPU、内存、GPU）
- 快捷操作按钮
- NVIDIA 优化预设选择
- 操作日志

### Web界面与API

RESTful API支持：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/processes` | GET | 获取进程列表 |
| `/api/processes/<pid>` | GET | 获取进程详情 |
| `/api/processes/<pid>/priority` | PUT | 设置优先级 |
| `/api/analyze` | POST | 分析进程 |
| `/api/report` | GET | 生成报告 |
| `/api/anomalies` | GET | 异常检测 |
| `/api/system` | GET | 系统状态 |
| `/api/config/*` | GET | 配置管理 |
| `/api/ml/*` | GET/POST | ML模型管理 |

### 历史与监控

- **历史记录**：CSV格式存储，支持7天历史
- **异常检测**：CPU/内存突增检测
- **报告生成**：JSON格式详细报告
- **性能统计**：实时性能指标

## 安装和使用

### 环境要求

- Python 3.8+
- Windows 10/11
- 建议管理员权限运行

### 安装依赖

```bash
pip install psutil pystray pillow flask flask-cors scikit-learn pandas numpy pyyaml wmi
```

### 可执行文件

**推荐方式**：从 GitHub Releases 下载签名版 EXE

**手动构建**：
```bash
pyinstaller build_exe.spec -y
```

已编译的 exe 版本位于 `dist/智优进程管理器/` 目录：

```
dist/智优进程管理器/
├── 智优进程管理器.exe    # 主程序
├── config/               # 配置文件
├── dashboard/            # Web界面
└── _internal/            # 依赖库
```

**使用方法：**
1. **双击运行**：直接进入系统托盘常驻后台
2. **右键托盘图标**：访问所有功能菜单
3. **打开主窗口**：点击"打开主窗口"菜单项

### 命令行参数

```bash
# 默认运行（进入托盘）
python process_priority_manager.py

# 控制台模式（显示日志）
python process_priority_manager.py --console

# 快速模式（低配置电脑）
python process_priority_manager.py --fast

# 彻底模式（高性能电脑）
python process_priority_manager.py --thorough

# Web界面
python process_priority_manager.py --web

# API服务
python process_priority_manager.py --api 5000

# 生成报告
python process_priority_manager.py --report

# 性能统计
python process_priority_manager.py --perf

# NVIDIA优化
python process_priority_manager.py --nvidia-optimize [low_latency|balanced|default]

# NVIDIA恢复
python process_priority_manager.py --nvidia-restore

# 查看NVIDIA状态
python process_priority_manager.py --nvidia-status
```

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl + Shift + N | NVIDIA一键优化 |

## 评分阈值

| 分数范围 | 优先级 | Windows优先级 |
|----------|--------|--------------|
| ≥85 | 高(high) | HIGH_PRIORITY_CLASS |
| 70-85 | 高于正常(above_normal) | ABOVE_NORMAL_PRIORITY_CLASS |
| 45-70 | 正常(normal) | NORMAL_PRIORITY_CLASS |
| 25-45 | 低于正常(below_normal) | BELOW_NORMAL_PRIORITY_CLASS |
| <25 | 空闲(idle) | IDLE_PRIORITY_CLASS |

## 受保护的进程

以下系统进程优先级不会被修改：
- System, System Idle Process
- smss.exe, csrss.exe, wininit.exe
- services.exe, lsass.exe, dwm.exe
- explorer.exe
- 安全软件进程（如HipsDaemon.exe）

## 配置文件

### app_categories.yaml

定义13种应用分类，包含：
- 关键词 (keywords)
- 路径模式 (paths)
- 窗口标题 (window_titles)
- 厂商关键词 (company_keywords)
- 推荐GPU (suggested_gpu)
- 默认优先级 (priority)

### scoring_rules.yaml

评分规则配置：
- 权重系数 (weights)
- 分类基础分 (category_base_scores)
- 进程类型加分 (process_type_bonus)
- 运行时长规则 (uptime_rules)
- 状态评分 (status_scores)

### cross_factors.yaml

交叉因子配置：
- 系统级调整（CPU/内存高负载时降低优先级）

## GitHub Actions 签名

本项目使用 GitHub Actions + Sigstore 实现免费代码签名：

1. **触发方式**：推送版本标签（如 `v1.2.0`）
2. **签名方式**：使用 Sigstore cosign 签名
3. **效果**：签名后的EXE显示"Microsoft已验证"

## 日志

- 控制台：仅显示错误
- 文件 (`process_priority_log.txt`)：WARNING及以上级别
- 保留3个备份，单文件最大5MB

## 版本记录

### v1.2.3
- 新增自动检查更新功能（GitHub Releases）
- 新增后台静默更新检查
- 新增托盘菜单"检查更新"选项
- 优化终端窗口隐藏处理（所有 subprocess 调用统一添加 CREATE_NO_WINDOW）
- 修复 wmi 模块调用导致的终端窗口问题（改用 PowerShell 命令）
- 添加全局异常处理和崩溃日志记录
- 添加线程异常捕获机制
- 新增手动清理缓存功能
- 优化打包配置，支持单文件EXE
- 移除无用的 wmi 依赖

### v1.2.0
- 新增ML评分模型（RandomForestRegressor）
- 新增智能分类器（TF-IDF + NaiveBayes）
- 新增增量扫描优化
- 新增配置校验与自动修复
- 新增异常检测功能
- 新增NVIDIA一键优化功能
- 新增GUI主窗口
- 新增GitHub Actions代码签名工作流
- 双击EXE默认进入托盘模式
- 优化历史数据管理

### v1.1.0
- 新增系统托盘功能
- 新增服务查询功能
- 新增性能模式（快速/平衡/彻底）
- 优化资源占用
- 应用名称「智优进程管理器」

### v1.0.0
- 智能游戏检测
- GPU偏好配置

### v0.4.2
- 修复评分过高问题
- 调整类型奖励权重

### v0.4.0
- 引入多线程并行处理
- 大幅提升扫描速度

## License

MIT License