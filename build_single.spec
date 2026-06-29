# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置文件 - 智优进程管理器 v1.3.0 单文件版
# 使用方法: pyinstaller build_single.spec

import os
import sys

block_cipher = None

# 获取项目根目录
project_root = os.path.dirname(SPEC)

a = Analysis(
    ['process_priority_manager.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        # 配置文件
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
        'psutil',
        'yaml',
        'json',
        'threading',
        'queue',
        'concurrent.futures',
        'win32gui',
        'win32process',
        'win32api',
        'win32con',
        'win32service',
        'win32serviceutil',
        'winreg',
        'wmi',
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'fastapi',
        'uvicorn',
        'pydantic',
        'flask',
        'sklearn',
        'sklearn.ensemble',
        'sklearn.preprocessing',
        'sklearn.model_selection',
        'sklearn.metrics',
        'sklearn.impute',
        'numpy',
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
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'unittest',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 单文件exe - 所有依赖都打包进一个exe文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='智优进程管理器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台，不显示黑色窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)