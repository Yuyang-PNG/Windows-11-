# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置文件 - 智优进程管理器 v1.2.0

import os
import sys

block_cipher = None

# 获取项目根目录
project_root = os.path.dirname(SPEC)

# 分析主程序
a = Analysis(
    ['process_priority_manager.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        # 配置文件 - 只包含实际存在的yaml文件
        ('config/app_categories.yaml', 'config'),
        ('config/scoring_rules.yaml', 'config'),
        ('config/cross_factors.yaml', 'config'),
        # Dashboard
        ('dashboard/index.html', 'dashboard'),
        # ML模型文件
        ('ml/models/classifier_pipeline.pkl', 'ml/models'),
        ('ml/models/imputer.pkl', 'ml/models'),
        ('ml/models/label_encoder.pkl', 'ml/models'),
        ('ml/models/scaler.pkl', 'ml/models'),
        ('ml/models/scoring_model.pkl', 'ml/models'),
    ],
    hiddenimports=[
        # 核心依赖
        'psutil',
        'yaml',
        'json',
        'threading',
        'queue',
        'concurrent.futures',
        # Windows API
        'win32gui',
        'win32process',
        'win32api',
        'win32con',
        'win32service',
        'win32serviceutil',
        'winreg',
        'wmi',
        # 可选依赖
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'fastapi',
        'uvicorn',
        'pydantic',
        'flask',
        # ML依赖
        'sklearn',
        'sklearn.ensemble',
        'sklearn.preprocessing',
        'sklearn.model_selection',
        'sklearn.metrics',
        'sklearn.impute',
        'numpy',
        # 项目模块
        'core.constants',
        'core.classifier',
        'core.scorer',
        'core.singleton',
        'core.cache',
        'core.di_container',
        'core.logger',
        'core.gpu_manager',
        'core.alerting',
        'config.config_manager',
        'config.config_validator',
        'monitoring.history_manager',
        'monitoring.performance_counter',
        'monitoring.network_monitor',
        'ml.scoring_model',
        'ml.smart_classifier',
        'api.app',
        'api.async_app',
        'core.nvidia_optimizer',
        'core.gui_manager',
        # tkinter 相关
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块
        'matplotlib',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        # 'tkinter',  # 保留 tkinter，用于 GUI 显示
        'unittest',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 过滤不需要的文件
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='智优进程管理器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台模式，双击直接进入托盘
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 添加版本信息
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='智优进程管理器',
)