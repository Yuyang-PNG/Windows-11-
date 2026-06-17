"""
NVIDIA 控制面板游戏低延迟优化模块

通过 Windows 注册表修改 NVIDIA 全局 3D 设置，提供一键竞技/3A 优化与还原功能。
注意：NVIDIA 驱动部分设置 OID 未官方公开，版本间可能存在差异；本模块会
在修改前备份当前值并在失败时给出清晰提示。
"""

import os
import time
import json
import logging
import threading
import winreg
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger('process_priority_manager')


class NvidiaSettingOid(IntEnum):
    """NVIDIA 全局 3D 设置 OID（基于社区/Profile Inspector 公开资料）。"""
    POWER_MANAGEMENT = 0x00783398
    LOW_LATENCY_MODE = 0x00A06946
    VERTICAL_SYNC = 0x10F9DC81
    TRIPLE_BUFFERING = 0x107D639D
    TEXTURE_FILTER_QUALITY = 0x00E08438
    ANISOTROPIC_FILTERING = 0x00E0843C
    TEXTURE_FILTER_OPTIMIZATION = 0x00E0843F


# 值映射：数值 -> 可读文本
_VALUE_LABELS: Dict[NvidiaSettingOid, Dict[int, str]] = {
    NvidiaSettingOid.POWER_MANAGEMENT: {
        0: "自适应",
        1: "最高性能优先",
        2: "一致性能",
    },
    NvidiaSettingOid.LOW_LATENCY_MODE: {
        0: "关",
        1: "开",
        2: "Ultra",
    },
    NvidiaSettingOid.VERTICAL_SYNC: {
        0: "关闭",
        1: "开启",
        2: "自适应",
        3: "自适应（半刷新率）",
        4: "快速",
    },
    NvidiaSettingOid.TRIPLE_BUFFERING: {
        0: "关",
        1: "开",
    },
    NvidiaSettingOid.TEXTURE_FILTER_QUALITY: {
        0: "高性能",
        1: "性能",
        2: "质量",
        3: "高质量",
    },
    NvidiaSettingOid.ANISOTROPIC_FILTERING: {
        0: "关闭",
        1: "应用程序控制",
        2: "2x",
        4: "4x",
        8: "8x",
        16: "16x",
    },
    NvidiaSettingOid.TEXTURE_FILTER_OPTIMIZATION: {
        0: "关",
        1: "开",
    },
}


@dataclass
class OptimizationPreset:
    """优化预设。"""
    name: str
    display_name: str
    description: str
    settings: Dict[NvidiaSettingOid, int] = field(default_factory=dict)


# 竞技游戏：最低延迟 + 最高帧率
LOW_LATENCY_PRESET = OptimizationPreset(
    name="low_latency",
    display_name="竞技低延迟",
    description="适合 CS2、Valorant、LOL、APEX 等竞技游戏，优先降低输入延迟",
    settings={
        NvidiaSettingOid.POWER_MANAGEMENT: 1,
        NvidiaSettingOid.LOW_LATENCY_MODE: 2,
        NvidiaSettingOid.VERTICAL_SYNC: 0,
        NvidiaSettingOid.TRIPLE_BUFFERING: 0,
        NvidiaSettingOid.TEXTURE_FILTER_QUALITY: 0,
        NvidiaSettingOid.ANISOTROPIC_FILTERING: 16,
        NvidiaSettingOid.TEXTURE_FILTER_OPTIMIZATION: 1,
    },
)

# 3A 大作：画质与性能平衡
BALANCED_PRESET = OptimizationPreset(
    name="balanced",
    display_name="3A 画质平衡",
    description="适合赛博朋克2077、艾尔登法环等单机大作，平衡画质与帧率",
    settings={
        NvidiaSettingOid.POWER_MANAGEMENT: 1,
        NvidiaSettingOid.LOW_LATENCY_MODE: 1,
        NvidiaSettingOid.VERTICAL_SYNC: 1,
        NvidiaSettingOid.TRIPLE_BUFFERING: 0,
        NvidiaSettingOid.TEXTURE_FILTER_QUALITY: 2,
        NvidiaSettingOid.ANISOTROPIC_FILTERING: 16,
        NvidiaSettingOid.TEXTURE_FILTER_OPTIMIZATION: 0,
    },
)

# 默认/恢复：让游戏或应用程序控制
DEFAULT_PRESET = OptimizationPreset(
    name="default",
    display_name="默认设置",
    description="恢复为 NVIDIA 默认/应用程序控制状态",
    settings={
        NvidiaSettingOid.POWER_MANAGEMENT: 0,
        NvidiaSettingOid.LOW_LATENCY_MODE: 0,
        NvidiaSettingOid.VERTICAL_SYNC: 1,
        NvidiaSettingOid.TRIPLE_BUFFERING: 0,
        NvidiaSettingOid.TEXTURE_FILTER_QUALITY: 2,
        NvidiaSettingOid.ANISOTROPIC_FILTERING: 1,
        NvidiaSettingOid.TEXTURE_FILTER_OPTIMIZATION: 1,
    },
)

PRESETS: Dict[str, OptimizationPreset] = {
    LOW_LATENCY_PRESET.name: LOW_LATENCY_PRESET,
    BALANCED_PRESET.name: BALANCED_PRESET,
    DEFAULT_PRESET.name: DEFAULT_PRESET,
}


def _format_oid(oid: NvidiaSettingOid) -> str:
    return f"0x{oid.value:08X}"


def _label_for(oid: NvidiaSettingOid, value: int) -> str:
    return _VALUE_LABELS.get(oid, {}).get(value, f"未知({value})")


def _get_backup_path() -> Path:
    """获取备份文件路径。"""
    base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    app_dir = base_dir / '智优进程管理器'
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / 'nvidia_settings_backup.json'


def _open_nvidia_key(access: int = winreg.KEY_READ):
    """尝试打开 NVIDIA 全局设置注册表键。优先当前用户配置，其次机器配置。"""
    paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\NVIDIA Corporation\Global\NVTweak"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\NVIDIA Corporation\Global\NVTweak"),
    ]
    for hkey, subkey in paths:
        try:
            key = winreg.OpenKey(hkey, subkey, 0, access)
            return key, hkey, subkey
        except OSError:
            continue
    return None, None, None


def is_nvidia_driver_installed() -> bool:
    """检测是否安装 NVIDIA 显卡驱动。"""
    try:
        key, _, _ = _open_nvidia_key(winreg.KEY_READ)
        if key:
            winreg.CloseKey(key)
            return True
    except Exception:
        pass

    # 通过常见文件/服务二次确认
    nvidia_paths = [
        Path(os.environ.get('SystemRoot', r"C:\Windows")) / "System32" / "nvoglv32.dll",
        Path(os.environ.get('SystemRoot', r"C:\Windows")) / "System32" / "nvoglv64.dll",
        Path(os.environ.get('SystemRoot', r"C:\Windows")) / "System32" / "nvlddmkm.sys",
    ]
    return any(p.exists() for p in nvidia_paths)


def is_nvidia_gpu_present() -> bool:
    """检测系统是否存在 NVIDIA GPU。"""
    try:
        import wmi
        c = wmi.WMI()
        for gpu in c.Win32_VideoController():
            name = gpu.Name or ""
            if "NVIDIA" in name.upper() or "GEFORCE" in name.upper():
                return True
    except Exception:
        pass

    # 如果 wmi 不可用，尝试 nvidia-smi
    try:
        import shutil
        import subprocess
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
    except Exception:
        pass

    return False


def get_nvidia_control_panel_path() -> Optional[Path]:
    """查找 NVIDIA 控制面板可执行文件路径。"""
    candidates = [
        Path(os.environ.get('SystemRoot', r"C:\Windows")) / "System32" / "nvcplui.exe",
        Path(os.environ.get('ProgramFiles', r"C:\Program Files")) / "NVIDIA Corporation" / "Control Panel Client" / "nvcplui.exe",
        Path(os.environ.get('ProgramFiles(x86)', r"C:\Program Files (x86)")) / "NVIDIA Corporation" / "Control Panel Client" / "nvcplui.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def read_current_settings() -> Dict[NvidiaSettingOid, Optional[int]]:
    """读取当前 NVIDIA 全局设置。"""
    result: Dict[NvidiaSettingOid, Optional[int]] = {oid: None for oid in NvidiaSettingOid}
    key, _, _ = _open_nvidia_key(winreg.KEY_READ)
    if not key:
        return result

    try:
        for oid in NvidiaSettingOid:
            try:
                value, _ = winreg.QueryValueEx(key, _format_oid(oid))
                if isinstance(value, int):
                    result[oid] = value
            except OSError:
                result[oid] = None
    finally:
        winreg.CloseKey(key)
    return result


def _write_setting(oid: NvidiaSettingOid, value: int) -> bool:
    """写入单个 NVIDIA 设置。"""
    key, hkey, subkey = _open_nvidia_key(winreg.KEY_READ | winreg.KEY_SET_VALUE)
    if not key:
        # 如果键不存在，尝试创建
        try:
            key, _ = winreg.CreateKeyEx(hkey or winreg.HKEY_CURRENT_USER, subkey or
                                        r"Software\NVIDIA Corporation\Global\NVTweak",
                                        0, winreg.KEY_WRITE)
        except Exception as e:
            logger.warning(f"无法创建/打开 NVIDIA 注册表键: {e}")
            return False

    try:
        winreg.SetValueEx(key, _format_oid(oid), 0, winreg.REG_DWORD, value)
        return True
    except Exception as e:
        logger.warning(f"写入 NVIDIA 设置 {_format_oid(oid)} 失败: {e}")
        return False
    finally:
        winreg.CloseKey(key)


def save_backup(settings: Dict[NvidiaSettingOid, Optional[int]]) -> bool:
    """保存当前设置到本地备份文件。"""
    try:
        data = {
            "timestamp": time.time(),
            "settings": {_format_oid(oid): value for oid, value in settings.items()},
        }
        backup_path = _get_backup_path()
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.warning(f"保存 NVIDIA 设置备份失败: {e}")
        return False


def load_backup() -> Optional[Dict[NvidiaSettingOid, Optional[int]]]:
    """从备份文件加载设置。"""
    backup_path = _get_backup_path()
    if not backup_path.exists():
        return None
    try:
        with open(backup_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        settings: Dict[NvidiaSettingOid, Optional[int]] = {oid: None for oid in NvidiaSettingOid}
        for oid in NvidiaSettingOid:
            value = data.get("settings", {}).get(_format_oid(oid))
            if value is not None:
                settings[oid] = int(value)
        return settings
    except Exception as e:
        logger.warning(f"加载 NVIDIA 设置备份失败: {e}")
        return None


def _delete_setting(oid: NvidiaSettingOid) -> bool:
    """删除单个 NVIDIA 设置（恢复为驱动默认值）。"""
    key, _, _ = _open_nvidia_key(winreg.KEY_READ | winreg.KEY_SET_VALUE)
    if not key:
        return False
    try:
        winreg.DeleteValue(key, _format_oid(oid))
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        logger.warning(f"删除 NVIDIA 设置 {_format_oid(oid)} 失败: {e}")
        return False
    finally:
        winreg.CloseKey(key)


def apply_settings(settings: Dict[NvidiaSettingOid, Optional[int]]) -> Dict[NvidiaSettingOid, bool]:
    """应用一组设置，返回每个 OID 的成功状态。"""
    results: Dict[NvidiaSettingOid, bool] = {}
    for oid, value in settings.items():
        if value is None:
            results[oid] = False
            continue
        results[oid] = _write_setting(oid, value)
    return results


def apply_preset(preset: OptimizationPreset, backup: bool = True) -> Tuple[bool, Dict[str, Any]]:
    """应用优化预设。"""
    if not is_nvidia_gpu_present() and not is_nvidia_driver_installed():
        return False, {"error": "未检测到 NVIDIA 显卡或驱动", "details": None}

    current = read_current_settings()
    if backup:
        save_backup(current)

    results = apply_settings(preset.settings)
    success_count = sum(1 for ok in results.values() if ok)
    total_count = len(results)

    details = {
        "preset": preset.name,
        "display_name": preset.display_name,
        "total": total_count,
        "success": success_count,
        "failed": total_count - success_count,
        "items": [
            {
                "name": oid.name,
                "oid": _format_oid(oid),
                "value": preset.settings[oid],
                "label": _label_for(oid, preset.settings[oid]),
                "success": results[oid],
            }
            for oid in NvidiaSettingOid
        ],
    }
    return success_count > 0, details


def restore_from_backup() -> Tuple[bool, Dict[str, Any]]:
    """从备份恢复设置。"""
    backup = load_backup()
    if not backup:
        return False, {"error": "找不到备份文件或备份已损坏"}

    results: Dict[NvidiaSettingOid, bool] = {}
    for oid, value in backup.items():
        if value is None:
            results[oid] = _delete_setting(oid)
        else:
            results[oid] = _write_setting(oid, value)

    success_count = sum(1 for ok in results.values() if ok)
    total_count = len(results)

    details = {
        "total": total_count,
        "success": success_count,
        "failed": total_count - success_count,
        "items": [
            {"name": oid.name, "oid": _format_oid(oid), "value": backup[oid], "success": results[oid]}
            for oid in NvidiaSettingOid
        ],
    }
    return success_count > 0, details


def launch_nvidia_control_panel() -> bool:
    """打开 NVIDIA 控制面板。"""
    import subprocess
    path = get_nvidia_control_panel_path()
    if path:
        try:
            subprocess.Popen([str(path)], shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception as e:
            logger.warning(f"打开 NVIDIA 控制面板失败: {e}")

    # 回退：使用控制面板命令
    try:
        subprocess.Popen(
            ["rundll32.exe", "shell32.dll,Control_RunDLL", "nvcpl.cpl"],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return True
    except Exception as e:
        logger.warning(f"通过 rundll32 打开 NVIDIA 控制面板失败: {e}")
    return False


class NvidiaOptimizer:
    """NVIDIA 一键优化器（线程安全单例语义，但内部无状态）。"""

    _instance_lock = threading.Lock()
    _instance: Optional["NvidiaOptimizer"] = None

    def __new__(cls) -> "NvidiaOptimizer":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._last_result: Optional[Dict[str, Any]] = None

    def is_available(self) -> bool:
        return is_nvidia_gpu_present() or is_nvidia_driver_installed()

    def get_status(self) -> Dict[str, Any]:
        return {
            "available": self.is_available(),
            "gpu_present": is_nvidia_gpu_present(),
            "driver_installed": is_nvidia_driver_installed(),
            "control_panel": str(get_nvidia_control_panel_path()) if get_nvidia_control_panel_path() else None,
            "current_settings": {
                oid.name: {
                    "value": value,
                    "label": _label_for(oid, value) if value is not None else "未设置",
                }
                for oid, value in read_current_settings().items()
            },
        }

    def apply(self, preset_name: str = "low_latency", backup: bool = True) -> Tuple[bool, Dict[str, Any]]:
        preset = PRESETS.get(preset_name, LOW_LATENCY_PRESET)
        ok, details = apply_preset(preset, backup=backup)
        self._last_result = details
        return ok, details

    def restore(self) -> Tuple[bool, Dict[str, Any]]:
        ok, details = restore_from_backup()
        self._last_result = details
        return ok, details

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        return self._last_result


def get_optimizer() -> NvidiaOptimizer:
    """获取默认优化器实例。"""
    return NvidiaOptimizer()
