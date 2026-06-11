from typing import Dict, Tuple

PRIORITY_LEVELS: Dict[str, int] = {
    'idle': 64,
    'below_normal': 16384,
    'normal': 32,
    'above_normal': 32768,
    'high': 128,
    'realtime': 256
}

PRIORITY_DISPLAY: Dict[str, str] = {
    'idle': '空闲(I)',
    'below_normal': '低于正常(B)',
    'normal': '正常(N)',
    'above_normal': '高于正常(A)',
    'high': '高(H)',
    'realtime': '实时(R)'
}

PRIORITY_THRESHOLDS: Tuple[float, float, float, float] = (85.0, 70.0, 45.0, 25.0)

SYSTEM_PROCESSES: set = {
    'system', 'system idle process', 'smss.exe', 'csrss.exe',
    'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe',
    'fontdrvhost.exe', 'dwm.exe', 'taskhostw.exe', 'explorer.exe'
}

USER_APP_PROCESSES: set = {
    'chrome.exe', 'msedge.exe', 'firefox.exe', 'notepad.exe',
    'code.exe', 'visualstudio.exe', 'idea64.exe', 'pycharm.exe',
    'teams.exe', 'discord.exe', 'steam.exe', 'spotify.exe',
    'word.exe', 'excel.exe', 'powerpnt.exe', 'outlook.exe'
}

NEED_ADMIN_PROCESSES: set = {
    'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe',
    'lsass.exe', 'system', 'system idle process'
}

PROTECTED_PROCESSES: set = {
    'dwm.exe', 'explorer.exe', 'csrss.exe', 'smss.exe',
    'lsass.exe', 'system', 'system idle process'
}

KNOWN_LIMITED_PROCESSES: set = NEED_ADMIN_PROCESSES | {
    'fontdrvhost.exe', 'wuifhost.exe', 'winlogon.exe'
}

THREAD_COUNT: int = 8
LOG_FILE: str = 'process_priority_log.txt'
CONFIG_FILE: str = 'gpu_config.json'

GPU_PREFERENCES: Dict[str, str] = {
    'auto': '让 Windows 决定',
    'integrated': '节能 (集成显卡)',
    'discrete': '高性能 (独立显卡)'
}

DEFAULT_WEIGHTS: Dict[str, int] = {
    'cpu_weight': 25,
    'memory_weight': 20,
    'threads_weight': 10,
    'io_weight': 8,
    'uptime_weight': 7,
    'status_weight': 5,
    'type_weight': 15
}

CATEGORY_BASE_SCORES: Dict[str, int] = {
    'gaming': 75,
    'video': 55,
    'browser': 45,
    'productivity': 45,
    'development': 55,
    'design': 65,
    'ai': 65,
    'system': 50,
    'security': 40,
    'utility': 40,
    'communication': 42,
    'music': 42,
    'cloud': 40,
    'unknown': 45
}

PROCESS_TYPE_BONUS: Dict[str, int] = {
    'user_app': 8,
    'system': 5,
    'service': 2,
    'background': -5,
    'unknown': 0
}

STATUS_SCORES: Dict[str, int] = {
    'running': 5,
    'sleeping': -3,
    'waiting': -2,
    'stopped': -10,
    'zombie': -15
}