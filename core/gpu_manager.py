import threading
import time
from typing import Dict, List, Optional, Any
from core.di_container import ServiceProvider
from core.logger import get_logger
from core.cache import TTLCache
from core.subprocess_utils import run_nvidia_smi, run_powershell, run_typeperf


class GPUInfo:
    def __init__(self, name: str, gpu_type: str, brand: str, memory_total: int = 0) -> None:
        self.name = name
        self.type = gpu_type
        self.brand = brand
        self.memory_total = memory_total
        self.memory_used = 0
        self.utilization = 0
        self.index = -1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type,
            'brand': self.brand,
            'memory_total': self.memory_total,
            'memory_used': self.memory_used,
            'utilization': self.utilization,
            'index': self.index
        }


class GPUDetector:
    def detect(self) -> List[Dict[str, Any]]:
        raise NotImplementedError


class NvidiaGPUDetector(GPUDetector):
    def __init__(self, timeout: int = 5) -> None:
        self._timeout = timeout

    def detect(self) -> List[Dict[str, Any]]:
        gpus: List[Dict[str, Any]] = []
        try:
            success, output = run_nvidia_smi(
                'name,memory.total,memory.used,utilization.gpu',
                'csv,noheader,nounits',
                timeout=self._timeout
            )
            if success and output:
                for line in output.strip().split('\n'):
                    parts = line.split(',')
                    if len(parts) >= 4:
                        gpus.append({
                            'name': parts[0].strip(),
                            'memory_total': int(parts[1].strip()),
                            'memory_used': int(parts[2].strip()),
                            'utilization': int(parts[3].strip()),
                            'type': 'discrete',
                            'brand': 'NVIDIA'
                        })
        except Exception:
            pass
        return gpus


class AMDGPUDetector(GPUDetector):
    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def detect(self) -> List[Dict[str, Any]]:
        gpus: List[Dict[str, Any]] = []
        try:
            success, output = run_powershell(
                'Get-CimInstance -ClassName Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json',
                timeout=self._timeout
            )
            if success and output:
                import json
                try:
                    data = json.loads(output)
                    if isinstance(data, dict):
                        data = [data]
                    for adapter in data:
                        gpu_name = adapter.get('Name', 'Unknown GPU')
                        if 'AMD' in gpu_name.upper() or 'RADEON' in gpu_name.upper():
                            vram = int(adapter.get('AdapterRAM', 0)) // (1024 ** 2) if adapter.get('AdapterRAM') else 0
                            gpus.append({
                                'name': gpu_name,
                                'memory_total': vram,
                                'memory_used': 0,
                                'utilization': 0,
                                'type': 'discrete',
                                'brand': 'AMD'
                            })
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        return gpus


class WMIGPUDetector(GPUDetector):
    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def detect(self) -> List[Dict[str, Any]]:
        gpus: List[Dict[str, Any]] = []
        try:
            success, output = run_powershell(
                'Get-CimInstance -ClassName Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json',
                timeout=self._timeout
            )
            if success and output:
                import json
                try:
                    data = json.loads(output)
                    if isinstance(data, dict):
                        data = [data]
                    for adapter in data:
                        gpu_name = adapter.get('Name', 'Unknown GPU')
                        vram = int(adapter.get('AdapterRAM', 0)) // (1024 ** 2) if adapter.get('AdapterRAM') else 0

                        if 'NVIDIA' in gpu_name.upper() or 'GEFORCE' in gpu_name.upper():
                            brand = 'NVIDIA'
                            gpu_type = 'discrete'
                        elif 'AMD' in gpu_name.upper() or 'RADEON' in gpu_name.upper():
                            brand = 'AMD'
                            gpu_type = 'discrete'
                        elif 'Intel Arc' in gpu_name:
                            brand = 'Intel Arc'
                            gpu_type = 'discrete'
                        elif 'Intel' in gpu_name or 'UHD' in gpu_name or 'HD Graphics' in gpu_name:
                            brand = 'Intel'
                            gpu_type = 'integrated'
                        else:
                            brand = 'Unknown'
                            gpu_type = 'discrete' if vram > 1024 else 'integrated'

                        gpus.append({
                            'name': gpu_name,
                            'memory_total': vram,
                            'memory_used': 0,
                            'utilization': 0,
                            'type': gpu_type,
                            'brand': brand
                        })
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        return gpus


class GPUManager:
    def __init__(self) -> None:
        self._logger = get_logger(__name__)
        self._cache = TTLCache(ttl_seconds=300)
        self._detectors: List[GPUDetector] = [
            NvidiaGPUDetector(timeout=5),
            AMDGPUDetector(timeout=10),
            WMIGPUDetector(timeout=10)
        ]

    def get_gpu_info(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        if not force_refresh:
            cached = self._cache.get('gpu_info')
            if cached is not None:
                self._logger.debug("使用缓存的GPU信息")
                return cached

        gpus = self._detect_concurrent()

        for i, gpu in enumerate(gpus):
            gpu['index'] = i

        self._cache.set('gpu_info', gpus)
        self._logger.info(f"GPU检测完成，共找到 {len(gpus)} 个GPU")
        return gpus

    def _detect_concurrent(self) -> List[Dict[str, Any]]:
        gpus: List[Dict[str, Any]] = []
        detected_names: set = set()
        results: List[Dict[str, Any]] = []
        threads: List[threading.Thread] = []

        def detect_with_timeout(detector: GPUDetector, results_list: List[Dict[str, Any]]) -> None:
            try:
                result = detector.detect()
                results_list.extend(result)
            except Exception as e:
                self._logger.debug(f"检测器 {detector.__class__.__name__} 执行失败: {e}")

        for detector in self._detectors:
            thread = threading.Thread(
                target=detect_with_timeout,
                args=(detector, results),
                daemon=True
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=15)

        for gpu in results:
            if gpu['name'] not in detected_names:
                detected_names.add(gpu['name'])
                gpus.append(gpu)

        return gpus

    def get_gpu_recommendation(self, process_name: str) -> Dict[str, Any]:
        from core.classifier import AppClassifier
        
        classifier = ServiceProvider.try_get(AppClassifier)
        if classifier:
            category, info = classifier.classify(process_name)
        else:
            category, info = 'unknown', {'description': '未知应用', 'suggested_gpu': 'auto'}

        suggested_gpu = info.get('suggested_gpu', 'auto')
        gpus = self.get_gpu_info()

        has_integrated = any(g.get('type') == 'integrated' for g in gpus)
        has_discrete = any(g.get('type') == 'discrete' for g in gpus)

        nvidia_gpus = [g for g in gpus if g.get('brand') == 'NVIDIA']
        amd_gpus = [g for g in gpus if g.get('brand') == 'AMD']

        recommendation: Dict[str, Any] = {
            'app_name': process_name,
            'category': category,
            'category_desc': info.get('description', '未知'),
            'suggested_gpu_type': suggested_gpu,
            'reason': '',
            'best_gpu': None
        }

        if category == 'gaming' or category == 'design' or category == 'ai':
            if nvidia_gpus:
                recommendation['best_gpu'] = nvidia_gpus[0]
                recommendation['reason'] = f"{info.get('description', '')}，推荐使用NVIDIA显卡"
            elif amd_gpus:
                recommendation['best_gpu'] = amd_gpus[0]
                recommendation['reason'] = f"{info.get('description', '')}，使用AMD显卡"
            elif gpus:
                recommendation['best_gpu'] = gpus[0]
                recommendation['reason'] = f"{info.get('description', '')}"

        elif category in ['browser', 'productivity', 'security', 'utility']:
            if has_integrated:
                integrated = [g for g in gpus if g.get('type') == 'integrated'][0]
                recommendation['best_gpu'] = integrated
                recommendation['reason'] = f"{info.get('description', '')}，使用集成显卡"
            elif gpus:
                recommendation['best_gpu'] = gpus[0]

        else:
            if suggested_gpu == 'discrete' and has_discrete:
                discrete = [g for g in gpus if g.get('type') == 'discrete'][0]
                recommendation['best_gpu'] = discrete
            elif suggested_gpu == 'integrated' and has_integrated:
                integrated = [g for g in gpus if g.get('type') == 'integrated'][0]
                recommendation['best_gpu'] = integrated
            elif gpus:
                recommendation['best_gpu'] = gpus[0]

        return recommendation

    def set_gpu_preference(self, exe_path: str, preference: str) -> bool:
        if not self._is_admin():
            self._logger.warning("需要管理员权限才能修改GPU设置")
            return False

        try:
            import winreg

            gpu_codes: Dict[str, str] = {
                'auto': '',
                'integrated': 'DXGK_DEVICE preference=0x1',
                'discrete': 'DXGK_DEVICE preference=0x2'
            }

            reg_path = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'

            if preference == 'auto':
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_ALL_ACCESS) as key:
                        winreg.DeleteValue(key, exe_path)
                    return True
                except FileNotFoundError:
                    return True

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_ALL_ACCESS) as key:
                winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, gpu_codes[preference])
            return True
        except Exception as e:
            self._logger.error(f"修改GPU设置失败: {e}")
            return False

    def _is_admin(self) -> bool:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def clear_cache(self) -> None:
        self._cache.invalidate()