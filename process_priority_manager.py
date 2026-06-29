import psutil
import sys
import os
import time
import threading
from queue import Queue
import glob
from datetime import datetime, timedelta
import json
import yaml
import logging
from logging.handlers import RotatingFileHandler
from core.log_rotator import LogRotator
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from functools import lru_cache, wraps
from typing import Dict, Tuple, List, Optional, Any

# ==================== 性能优化配置 ====================
# 针对低性能用户的优化配置
PERFORMANCE_MODE = os.environ.get('PRIORITY_MANAGER_PERF_MODE', 'balanced')  # 'fast', 'balanced', 'thorough'

# 线程池配置 - 根据性能模式调整
THREAD_POOL_SIZE = {
    'fast': 2,
    'balanced': 4,
    'thorough': min(os.cpu_count() or 4, 8)
}

# 扫描间隔配置（秒）
SCAN_INTERVAL = {
    'fast': 300,
    'balanced': 180,
    'thorough': 60
}

# 是否启用详细分析（影响CPU/内存）
ENABLE_DETAILED_ANALYSIS = {
    'fast': False,
    'balanced': True,
    'thorough': True
}

# 是否检测GPU（GPU检测可能耗时较长）
ENABLE_GPU_DETECTION = {
    'fast': False,
    'balanced': True,
    'thorough': True
}

def get_performance_mode():
    """获取当前性能模式"""
    return PERFORMANCE_MODE

def get_thread_pool_size():
    """根据性能模式获取线程池大小"""
    return THREAD_POOL_SIZE.get(PERFORMANCE_MODE, 4)

def should_enable_detailed_analysis():
    """是否启用详细分析"""
    return ENABLE_DETAILED_ANALYSIS.get(PERFORMANCE_MODE, True)

def should_detect_gpu():
    """是否检测GPU"""
    return ENABLE_GPU_DETECTION.get(PERFORMANCE_MODE, True)

# 系统托盘相关导入
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

from core.constants import (
    PRIORITY_LEVELS, PRIORITY_DISPLAY, SYSTEM_PROCESSES, USER_APP_PROCESSES,
    NEED_ADMIN_PROCESSES, PROTECTED_PROCESSES, KNOWN_LIMITED_PROCESSES,
    RESTORE_PROTECTED_PROCESSES, THREAD_COUNT, LOG_FILE, CONFIG_FILE, GPU_PREFERENCES, DEFAULT_WEIGHTS,
    CATEGORY_BASE_SCORES, PROCESS_TYPE_BONUS, STATUS_SCORES
)
from core.classifier import AppClassifier
from core.scorer import PriorityScorer
from core.singleton import Singleton
from core.cache import TTLCache
from core.config_watcher import ConfigWatcher
from core.priority_restore import PriorityRestoreManager
from core.preference_learner import PreferenceLearner
from core.notification import NotificationManager, get_notification_manager
from core.shortcut import GlobalShortcutManager
from core.nvidia_optimizer import (
    PRESETS, get_optimizer, launch_nvidia_control_panel
)
from core.gui_manager import (
    safe_print, show_quick_message, get_main_window, MainWindow, HAS_CONSOLE
)

# 全局快捷键管理器
shortcut_manager = GlobalShortcutManager()

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

GPU_CACHE = TTLCache(ttl_seconds=300)
CLASSIFICATION_CACHE = TTLCache(ttl_seconds=600)
priority_restore_manager = PriorityRestoreManager()
preference_learner = PreferenceLearner()
notification_manager = get_notification_manager()
nvidia_optimizer = get_optimizer()

def ttl_cache(ttl_seconds=300):
    def decorator(func):
        cache = TTLCache(ttl_seconds)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, frozenset(kwargs.items()))
            result = cache.get(key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result
        return wrapper
    return decorator

class LogRotatorHandler(logging.Handler):
    """基于 LogRotator 的日志处理器"""
    
    def __init__(self, log_rotator):
        super().__init__()
        self.log_rotator = log_rotator
        self.file_handler = None
    
    def emit(self, record):
        """日志记录时检查并执行轮转"""
        if self.log_rotator.should_rotate():
            self.log_rotator.rotate()


def setup_logging(verbose=False):
    """设置日志记录 - 用户模式下减少输出"""
    logger = logging.getLogger('process_priority_manager')
    
    # 用户模式下只显示重要信息
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.ERROR)  # 用户模式：只显示错误
    
    # 清空已有的handler
    if logger.handlers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
    
    formatter = logging.Formatter(LOG_FORMAT)
    
    console_handler = logging.StreamHandler()
    if verbose:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.ERROR)  # 用户模式：控制台只显示错误
    console_handler.setFormatter(formatter)
    
    # 使用 LogRotator 替换 RotatingFileHandler
    log_rotator = LogRotator(LOG_FILE)
    rotator_handler = LogRotatorHandler(log_rotator)
    rotator_handler.setLevel(logging.WARNING)  # 文件记录警告和错误
    rotator_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(rotator_handler)
    
    return logger

logger = setup_logging()

class ProcessSnapshot:
    def __init__(self, pid, name, create_time, cpu_percent, memory_percent):
        self.pid = pid
        self.name = name
        self.create_time = create_time
        self.cpu_percent = cpu_percent
        self.memory_percent = memory_percent
    
    def __hash__(self):
        return hash(self.pid)
    
    def __eq__(self, other):
        if isinstance(other, ProcessSnapshot):
            return self.pid == other.pid
        return False
    
    def to_dict(self):
        return {
            'pid': self.pid,
            'name': self.name,
            'create_time': self.create_time,
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent
        }

class IncrementalScanner:
    def __init__(self):
        self.last_scan_time = 0
        self.last_process_snapshots = set()
        self.scan_interval = 5
        self._lock = threading.RLock()
    
    def _get_process_snapshot(self, proc):
        try:
            create_time = proc.create_time()
            cpu_percent = proc.cpu_percent(interval=None)
            memory_percent = proc.memory_percent()
            return ProcessSnapshot(
                pid=proc.pid,
                name=proc.name(),
                create_time=create_time,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
    
    def scan(self, force_full=False):
        current_time = time.time()
        
        with self._lock:
            if not force_full and current_time - self.last_scan_time < self.scan_interval:
                logger.debug(f"跳过扫描，距离上次扫描仅 {current_time - self.last_scan_time:.1f}秒")
                return [], [], []
            
            current_snapshots = set()
            for proc in psutil.process_iter(['pid', 'name']):
                snapshot = self._get_process_snapshot(proc)
                if snapshot:
                    current_snapshots.add(snapshot)
            
            new_processes = current_snapshots - self.last_process_snapshots
            terminated_processes = self.last_process_snapshots - current_snapshots
            
            changed_processes = []
            for current in current_snapshots:
                for last in self.last_process_snapshots:
                    if current.pid == last.pid:
                        cpu_changed = abs(current.cpu_percent - last.cpu_percent) > 5
                        mem_changed = abs(current.memory_percent - last.memory_percent) > 2
                        if cpu_changed or mem_changed:
                            changed_processes.append(current)
                        break
            
            self.last_process_snapshots = current_snapshots
            self.last_scan_time = current_time
            
            logger.info(f"增量扫描完成: 新增 {len(new_processes)} 个, 终止 {len(terminated_processes)} 个, 变化 {len(changed_processes)} 个")
            
            return list(new_processes), list(terminated_processes), list(changed_processes)
    
    def get_all_processes(self):
        with self._lock:
            return list(self.last_process_snapshots)
    
    def reset(self):
        with self._lock:
            self.last_scan_time = 0
            self.last_process_snapshots = set()

class Application(metaclass=Singleton):
    def __init__(self):
        self._initialized = False
    
    def initialize(self):
        if self._initialized:
            return
        
        self.config_manager = None
        self.history_manager = None
        self.perf_counter = None
        self.network_monitor = None
        self.ml_model = None
        self.smart_classifier = None
        self.api_server = None
        self.incremental_scanner = IncrementalScanner()
        self.scheduler = None
        
        try:
            from config.config_manager import ConfigManager
            self.config_manager = ConfigManager()
            # 初始化配置监视器
            self.config_watcher = ConfigWatcher(self.config_manager)
            self.config_manager._config_watcher = self.config_watcher
            self.config_watcher.start()
            logger.info("配置模块加载成功")
        except ImportError as e:
            logger.warning(f"配置模块不可用: {e}")
        
        try:
            from monitoring.history_manager import HistoryManager
            self.history_manager = HistoryManager()
            logger.info("历史记录模块加载成功")
        except ImportError as e:
            logger.warning(f"历史记录模块不可用: {e}")
        
        try:
            from monitoring.performance_counter import PerformanceCounter
            self.perf_counter = PerformanceCounter()
            logger.info("性能计数器模块加载成功")
        except ImportError as e:
            logger.warning(f"性能计数器模块不可用: {e}")
        
        try:
            from monitoring.network_monitor import NetworkMonitor
            self.network_monitor = NetworkMonitor()
            logger.info("网络监控模块加载成功")
        except ImportError as e:
            logger.warning(f"网络监控模块不可用: {e}")
        
        try:
            from ml.scoring_model import MLScoringModel
            self.ml_model = MLScoringModel()
            logger.info("ML评分模型加载成功")
        except ImportError as e:
            logger.warning(f"ML评分模型不可用，使用规则引擎评分: {e}")
        
        try:
            from ml.smart_classifier import SmartAppClassifier
            self.smart_classifier = SmartAppClassifier()
            if self.config_manager:
                categories = self.config_manager.get_app_categories().get('categories', APP_CATEGORIES)
                result = self.smart_classifier.train(categories)
                if result['status'] == 'success':
                    logger.info(f"智能分类器训练成功，样本数: {result['samples']}")
                else:
                    logger.warning(f"智能分类器训练失败: {result.get('message', '未知错误')}")
            logger.info("智能分类器模块加载成功")
        except ImportError as e:
            logger.warning(f"智能分类器模块不可用: {e}")
        
        self._initialized = True
        
        global CONFIG_MANAGER, ML_MODEL, HISTORY_MANAGER, PERF_COUNTER, NETWORK_MONITOR
        CONFIG_MANAGER = self.config_manager
        ML_MODEL = self.ml_model
        HISTORY_MANAGER = self.history_manager
        PERF_COUNTER = self.perf_counter
        NETWORK_MONITOR = self.network_monitor
        
        # 初始化游戏检测状态
        self.game_detection_enabled = True  # 游戏检测开关
        self.last_game_optimization = 0    # 上次游戏优化时间
        self.game_cooldown = 300           # 游戏优化冷却时间（秒）- 默认5分钟
        self.last_detected_games = set()  # 上次检测到的游戏
        self.game_optimization_count = 0   # 游戏优化次数统计
    
    def detect_games(self):
        """
        检测当前运行的游戏进程
        返回: (是否有游戏运行, 游戏列表)
        """
        if not self.game_detection_enabled:
            return False, []
        
        try:
            current_games = set()
            gaming_category = APP_CATEGORIES.get('gaming', {})
            game_keywords = gaming_category.get('keywords', [])
            
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_name = proc.name().lower()
                    proc_exe = ''
                    try:
                        proc_exe = proc.exe().lower() if proc.exe() else ''
                    except:
                        pass
                    
                    # 检查进程名和路径是否包含游戏关键词
                    for keyword in game_keywords:
                        if keyword in proc_name or keyword in proc_exe:
                            current_games.add(proc_name)
                            break
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # 检查是否有新游戏启动
            new_games = current_games - self.last_detected_games
            
            if new_games and self.last_detected_games:
                logger.info(f"检测到新游戏启动: {', '.join(new_games)}")
                notification_manager.game_detected(', '.join(new_games))
            
            self.last_detected_games = current_games
            return len(current_games) > 0, list(current_games)
            
        except Exception as e:
            logger.debug(f"游戏检测失败: {e}")
            return False, []
    
    def should_optimize_for_games(self):
        """
        判断是否应该执行游戏优化
        基于冷却时间和游戏状态
        """
        current_time = time.time()
        
        # 检查冷却时间
        if current_time - self.last_game_optimization < self.game_cooldown:
            logger.debug(f"游戏优化冷却中，还需 {int(self.game_cooldown - (current_time - self.last_game_optimization))} 秒")
            return False
        
        # 检查是否有游戏在运行
        has_games, game_list = self.detect_games()
        return has_games
    
    def optimize_for_games(self):
        """
        针对游戏进行进程优化
        使用轻量级快速模式
        """
        current_time = time.time()
        
        # 检查是否应该优化
        if not self.should_optimize_for_games():
            return None
        
        logger.info("开始游戏优化...")
        self.game_optimization_count += 1
        
        try:
            # 使用快速模式进行分析（减少资源占用）
            global PERFORMANCE_MODE
            original_mode = PERFORMANCE_MODE
            PERFORMANCE_MODE = 'fast'  # 使用快速模式避免影响游戏
            
            # 临时修改全局函数使用快速模式
            results = analyze_all_processes()
            
            PERFORMANCE_MODE = original_mode  # 恢复原模式
            
            success_count = sum(1 for r in results if r.get('status') == 'success')
            
            # 统计优化结果
            optimized_games = [r for r in results if r.get('proc_type') == 'game']
            optimized_others = [r for r in results if r.get('proc_type') != 'game']
            
            self.last_game_optimization = current_time
            
            logger.info(f"游戏优化完成: 优化 {success_count} 个进程, "
                       f"其中游戏进程 {len(optimized_games)} 个, "
                       f"其他进程 {len(optimized_others)} 个, "
                       f"本次为第 {self.game_optimization_count} 次优化")
            
            notification_manager.optimization_complete(success_count)
            
            return {
                'success': success_count,
                'games': len(optimized_games),
                'others': len(optimized_others),
                'total': len(results)
            }
            
        except Exception as e:
            logger.error(f"游戏优化失败: {e}")
            return None
    
    def start_scheduler(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            
            self.scheduler = BackgroundScheduler()
            
            # 游戏检测和优化任务 - 每30秒检测一次
            self.scheduler.add_job(
                self._smart_optimization,
                trigger=IntervalTrigger(seconds=30),
                id='smart_optimization',
                name='智能游戏优化',
                replace_existing=True
            )
            
            # 定期快照任务 - 每5分钟
            self.scheduler.add_job(
                self._scheduled_snapshot,
                trigger=IntervalTrigger(minutes=5),
                id='periodic_snapshot',
                name='定期进程快照',
                replace_existing=True
            )
            
            # 每日清理任务
            self.scheduler.add_job(
                self._cleanup_old_data,
                trigger=IntervalTrigger(hours=24),
                id='daily_cleanup',
                name='每日清理',
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("定时任务调度器启动成功 - 智能游戏检测已启用")
        except ImportError as e:
            logger.warning(f"APScheduler不可用，定时任务功能已禁用: {e}")
    
    def _smart_optimization(self):
        """
        智能优化任务
        检测到游戏时自动优化，不频繁打扰
        """
        try:
            # 检测游戏
            has_games, game_list = self.detect_games()
            
            if has_games:
                logger.debug(f"检测到游戏运行: {', '.join(game_list)}")
                
                # 如果有游戏，尝试优化
                result = self.optimize_for_games()
                if result:
                    logger.info(f"游戏 '{game_list[0]}' 优化完成")
            else:
                logger.debug("当前无游戏运行")
                
        except Exception as e:
            logger.debug(f"智能优化任务执行失败: {e}")
    
    def _scheduled_optimization(self):
        logger.info("执行定时自动优化任务")
        try:
            results = analyze_all_processes()
            success_count = sum(1 for r in results if r.get('status') == 'success')
            logger.info(f"定时优化完成: 成功 {success_count} 个进程")
        except Exception as e:
            logger.error(f"定时优化任务失败: {e}")
    
    def _scheduled_snapshot(self):
        try:
            if self.history_manager:
                processes = get_process_list_for_snapshot()
                self.history_manager.record_process_snapshot(processes)
                logger.debug("定期快照已记录")
        except Exception as e:
            logger.error(f"定期快照任务失败: {e}")
    
    def _cleanup_old_data(self):
        try:
            if self.history_manager:
                self.history_manager.clean_old_data()
                logger.info("旧数据清理完成")
        except Exception as e:
            logger.error(f"数据清理任务失败: {e}")
    
    def shutdown(self):
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            logger.info("定时任务调度器已停止")

APP = Application()

CONFIG_MANAGER = None
ML_MODEL = None
HISTORY_MANAGER = None
PERF_COUNTER = None
NETWORK_MONITOR = None

try:
    from api.app import ProcessPriorityAPI
    API_AVAILABLE = True
    logger.info("API模块加载成功")
except ImportError as e:
    API_AVAILABLE = False
    logger.warning(f"API模块不可用: {e}")

try:
    from flask import Flask, render_template_string, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

APP_CATEGORIES = {
    'gaming': {
        'keywords': ['game', 'gaming', 'steam', 'epic', 'battle.net', 'blizzard', 
                     'league of legends', 'csgo', 'dota', 'valorant', 'pubg',
                     'fortnite', 'apex', 'minecraft', 'roblox', 'gta', 'elden ring',
                     'cyberpunk', 'starfield', 'wow', 'world of warcraft', 'lol',
                     'arknights', '明日方舟', 'honkai', 'genshin', '原神', '崩坏',
                     'touhou', '东方', 'fgo', 'fate', 'blue archive', 'bluearchive',
                     'azur lane', 'azurlane', 'warship girls', '战舰少女',
                     'counter-strike', 'overwatch', 'destiny', 'warframe',
                     'eldenring', 'dark souls', 'sekiro', 'bloodborne',
                     'resident evil', 'cyberpunk2077', 'red dead', 'elden',
                     'apex legends', 'call of duty', 'cod', 'fifa', 'pes',
                     'nba2k', 'madden', 'forza', 'gran turismo', 'need for speed',
                     'assassin', 'creed', 'witcher', 'skyrim', 'fallout',
                     'borderlands', 'mass effect', 'dragon age', 'final fantasy',
                     'kingdom hearts', 'zelda', 'mario', 'pokemon', 'animal crossing',
                     'gameviewer', 'platformprocess', 'pcgameplatform', 'gameservice',
                     '七日世界', 'sevenworld',
                     'fevergames', 'security_protection', 'game_security', 'gamelauncher',
                     'unity', 'unreal', 'ue4', 'ue5', 'cryengine', 'source'],
        'paths': ['steam\\steamapps', 'epic games', 'battle.net', 'origin games',
                  'ubisoft\\ubisoft game', 'rockstar games', 'gog galaxy',
                  'riot games', 'blizzard entertainment', 'ea games',
                  'tencent\\games', 'netease\\games', 'mihoyo', 'miHoYo'],
        'window_titles': ['- Steam', 'Epic Games Launcher', 'Battle.net',
                         '- Minecraft', '- Roblox', '明日方舟', '原神'],
        'description': '游戏应用',
        'suggested_gpu': 'discrete',
        'priority': 'high'
    },
    'video': {
        'keywords': ['video', 'player', 'vlc', 'potplayer', 'mpc', 'media',
                     'netflix', 'youtube', 'prime video', 'disney', 'hulu',
                     'bilibili', 'youku', 'iqiyi', 'tencent video'],
        'paths': ['videos', 'media player', 'video player'],
        'window_titles': ['VLC media player', 'PotPlayer', '- MPC-HC'],
        'description': '视频播放',
        'suggested_gpu': 'auto',
        'priority': 'medium'
    },
    'browser': {
        'keywords': ['browser', 'chrome', 'edge', 'msedge', 'firefox', 'brave', 'opera', 'safari',
                     'cent', 'maxthon', 'chromium', 'vivaldi', 'yandex', 'torbrowser'],
        'paths': ['google\\chrome', 'microsoft\\edge', 'mozilla\\firefox',
                  'brave software', 'opera software', 'vivaldi'],
        'window_titles': ['- Google Chrome', '- Microsoft Edge', '- Mozilla Firefox',
                         '- Brave', '- Opera', '- Vivaldi'],
        'description': '浏览器',
        'suggested_gpu': 'integrated',
        'priority': 'low'
    },
    'productivity': {
        'keywords': ['office', 'word', 'excel', 'powerpoint', 'outlook', 'teams',
                     'slack', 'zoom', 'webex', 'notion', 'evernote', 'onenote',
                     'wps', 'kingsoft', '钉钉', '飞书', '企业微信'],
        'paths': ['microsoft office', 'wps office', 'kingsoft office'],
        'window_titles': ['Microsoft Word', 'Microsoft Excel', 'Microsoft PowerPoint',
                         '- Slack', '- Zoom', '- Teams'],
        'description': '办公软件',
        'suggested_gpu': 'integrated',
        'priority': 'low'
    },
    'development': {
        'keywords': ['code', 'visual studio', 'idea', 'pycharm', 'vscode',
                     'android studio', 'xcode', 'jetbrains', 'eclipse', 'netbeans'],
        'paths': ['visual studio', 'jetbrains', 'eclipse', 'android studio'],
        'window_titles': ['- Visual Studio', '- IntelliJ IDEA', '- PyCharm',
                         '- Visual Studio Code'],
        'description': '开发工具',
        'suggested_gpu': 'auto',
        'priority': 'medium'
    },
    'design': {
        'keywords': ['photoshop', 'illustrator', 'premiere', 'after effects',
                     'blender', 'cinema 4d', '3ds max', 'maya', 'substance',
                     'lightroom', 'in design', 'coreldraw', 'affinity'],
        'paths': ['adobe', 'autodesk', 'blender foundation', 'maxon'],
        'window_titles': ['Adobe Photoshop', 'Adobe Illustrator', 'Blender',
                         'Cinema 4D', '- After Effects'],
        'description': '设计软件',
        'suggested_gpu': 'discrete',
        'priority': 'high'
    },
    'ai': {
        'keywords': ['python', 'tensorflow', 'pytorch', 'cuda', 'nvidia',
                     'stable diffusion', 'midjourney', 'dall-e', 'chatgpt',
                     'llama', 'claude', 'bard', 'copilot'],
        'paths': ['python', 'anaconda', 'miniconda', 'tensorflow', 'pytorch'],
        'window_titles': [],
        'description': 'AI/机器学习',
        'suggested_gpu': 'discrete',
        'priority': 'high'
    },
    'system': {
        'keywords': ['svchost', 'explorer', 'taskmgr', 'dwm', 'services', 'lsass',
                     'smss', 'csrss', 'wininit', 'winlogon', 'rundll32', 'cmd', 'powershell',
                     'system', 'conhost', 'wuahost', 'wudfhost', 'fontdrvhost', 'armsvc',
                     'mssense', 'mpsvc', 'msmpeng', 'searchindexer', 'searchfilterhost',
                     'searchprotocolhost', 'wmiprvse', 'wmiapsrv', 'unsecapp', 'spoolsv',
                     'nvcontainer', 'nvidia', 'intel', 'amd', 'realtek', 'asus', 'armourycrate',
                     'rogliveservice', 'esrv', 'crashpad_handler', 'msedgeupdate',
                     'textinputhost', 'applicationframehost', 'aggregatorhost', 'shellhost',
                     'wlanext', 'chsime', 'sursvc', 'ipfsvc', 'dsaservice', 'asusswitch',
                     'asusoptimization', 'asusappservice', 'asussoftwaremanager', 'asusptpservice',
                     'asussystemdiagnosis', 'asussystemanalysis', 'hipsdaemon', 'dax3api',
                     'mpdefendercoreservice', 'rtkauduservice', 'intelaudioservice', 'intelgraphicsoftware',
                     'intel_pie_service', 'presentmonservice', 'wmiregistrationservice', 'dsaupdateservice',
                     'wsctrlsvc', 'gameviewerserver', 'gameviewerservice', 'trae', 'python',
                     'memcompression', 'nvdisplay.container', 'esrv_svc', 'jhi_service',
                     'asus_framework', 'asussoftwaresourcemanageragent', 'asuscertservice',
                     'intelcphdcpsvc', 'nvidia overlay', 'runtimebroker', 'dataexchangehost',
                     'shellexperiencehost', 'useroobebroker', 'sihost', 'startmenuexperiencehost',
                     'crossdeviceresume', 'searchhost', 'taskhostw', 'acpowernotification',
                     'armourysocketserver', 'ctfmon', 'tabtip', '360desktoplite', 'audiodg',
                     'smartscreen', 'armourycrate.usersessionhelper'],
        'paths': ['windows\\system32', 'windows\\syswow64', 'program files\\nvidia',
                  'program files\\intel', 'program files\\amd', 'program files\\asus'],
        'window_titles': ['任务管理器', 'File Explorer', 'Command Prompt', 'PowerShell'],
        'description': '系统进程',
        'suggested_gpu': 'integrated',
        'priority': 'system'
    },
    'security': {
        'keywords': ['antivirus', 'defender', '360', 'security', 'firewall', 'malware',
                     'norton', 'mcafee', 'kaspersky', 'eset', 'avg'],
        'paths': ['windows defender', '360 security', 'norton', 'mcafee'],
        'window_titles': [],
        'description': '安全软件',
        'suggested_gpu': 'integrated',
        'priority': 'low'
    },
    'utility': {
        'keywords': ['utility', 'tool', 'helper', 'manager', 'optimizer', 'cleaner',
                     'ccleaner', 'advanced systemcare', 'driver', 'update'],
        'paths': ['ccleaner', 'advanced systemcare', 'driver booster'],
        'window_titles': [],
        'description': '工具软件',
        'suggested_gpu': 'integrated',
        'priority': 'low'
    },
    'communication': {
        'keywords': ['wechat', 'qq', 'telegram', 'discord', 'whatsapp', 'signal',
                     'line', 'kakao', 'skype', 'messenger'],
        'paths': ['tencent\\wechat', 'tencent\\qq', 'telegram', 'discord'],
        'window_titles': ['微信', 'QQ', '- Discord', '- Telegram'],
        'description': '通讯软件',
        'suggested_gpu': 'integrated',
        'priority': 'low'
    },
    'music': {
        'keywords': ['music', 'player', 'spotify', 'netease', 'kuwo', 'kugou',
                     'qqmusic', 'itunes', 'winamp'],
        'paths': ['netease cloud music', 'qq music', 'spotify'],
        'window_titles': ['Spotify', '- QQ音乐', '- 网易云音乐'],
        'description': '音乐软件',
        'suggested_gpu': 'integrated',
        'priority': 'low'
    },
    'cloud': {
        'keywords': ['dropbox', 'onedrive', 'google drive', 'baidu', 'aliyun',
                     'weiyun', 'icloud'],
        'paths': ['microsoft onedrive', 'dropbox', 'google drive'],
        'window_titles': [],
        'description': '云存储',
        'suggested_gpu': 'integrated',
        'priority': 'low'
    }
}

def get_process_window_title(pid):
    try:
        import win32gui
        import win32process
        
        def callback(hwnd, extra):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid and win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    extra.append(title)
            return True
        
        titles = []
        win32gui.EnumWindows(callback, titles)
        return titles[0] if titles else None
    except:
        return None

def get_process_company_name(exe_path):
    try:
        import win32api
        import win32con
        info = win32api.GetFileVersionInfo(exe_path, "\\")
        company = info.get('CompanyName', '')
        return company
    except:
        return None

_classifier = None

def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = AppClassifier()
    return _classifier

def classify_app(process_name: str, exe_path: Optional[str] = None, window_title: Optional[str] = None, 
                 company_name: Optional[str] = None, use_smart: bool = True) -> Tuple[str, Dict]:
    return get_classifier().classify(process_name, exe_path, window_title, company_name, use_smart)

def classify_process(process_name_lower: str) -> str:
    return classify_app(process_name_lower)[0]

def ai_gpu_recommendation(process_name, gpus):
    category, info = classify_app(process_name)
    suggested_gpu = info['suggested_gpu']
    
    has_integrated = any(g.get('type') == 'integrated' for g in gpus)
    has_discrete = any(g.get('type') == 'discrete' for g in gpus)
    
    nvidia_gpus = [g for g in gpus if g.get('brand') == 'NVIDIA']
    amd_gpus = [g for g in gpus if g.get('brand') == 'AMD']
    intel_gpus = [g for g in gpus if g.get('brand') == 'Intel']
    
    recommendation = {
        'app_name': process_name,
        'category': category,
        'category_desc': info['description'],
        'suggested_gpu_type': suggested_gpu,
        'reason': '',
        'best_gpu': None
    }
    
    if category == 'gaming':
        if nvidia_gpus:
            recommendation['best_gpu'] = nvidia_gpus[0]
            recommendation['reason'] = f"游戏应用，推荐使用NVIDIA显卡获得最佳性能"
        elif amd_gpus:
            recommendation['best_gpu'] = amd_gpus[0]
            recommendation['reason'] = f"游戏应用，推荐使用AMD显卡"
        else:
            recommendation['best_gpu'] = gpus[0] if gpus else None
            recommendation['reason'] = f"游戏应用，使用可用的显卡"
    
    elif category == 'design' or category == 'ai':
        if nvidia_gpus:
            recommendation['best_gpu'] = nvidia_gpus[0]
            recommendation['reason'] = f"{info['description']}，NVIDIA显卡在CUDA加速方面表现更佳"
        elif amd_gpus:
            recommendation['best_gpu'] = amd_gpus[0]
            recommendation['reason'] = f"{info['description']}，使用AMD显卡"
        else:
            recommendation['best_gpu'] = gpus[0] if gpus else None
            recommendation['reason'] = f"{info['description']}"
    
    elif category == 'browser' or category == 'productivity' or category == 'security' or category == 'utility':
        if has_integrated:
            integrated = [g for g in gpus if g.get('type') == 'integrated'][0]
            recommendation['best_gpu'] = integrated
            recommendation['reason'] = f"{info['description']}，使用集成显卡足够，节省独立显卡资源"
        else:
            recommendation['best_gpu'] = gpus[0] if gpus else None
            recommendation['reason'] = f"{info['description']}"
    
    elif category == 'video':
        if has_discrete:
            discrete = [g for g in gpus if g.get('type') == 'discrete'][0]
            recommendation['best_gpu'] = discrete
            recommendation['reason'] = f"{info['description']}，独立显卡解码性能更好"
        else:
            recommendation['best_gpu'] = gpus[0] if gpus else None
            recommendation['reason'] = f"{info['description']}"
    
    else:
        if suggested_gpu == 'discrete' and has_discrete:
            discrete = [g for g in gpus if g.get('type') == 'discrete'][0]
            recommendation['best_gpu'] = discrete
            recommendation['reason'] = f"{info['description']}，推荐使用独立显卡"
        elif suggested_gpu == 'integrated' and has_integrated:
            integrated = [g for g in gpus if g.get('type') == 'integrated'][0]
            recommendation['best_gpu'] = integrated
            recommendation['reason'] = f"{info['description']}，推荐使用集成显卡"
        else:
            recommendation['best_gpu'] = gpus[0] if gpus else None
            recommendation['reason'] = f"{info['description']}，自动选择"
    
    return recommendation

def is_admin():
    try:
        if sys.platform.startswith('win'):
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.getuid() == 0
    except:
        return False

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'gpu_settings': {}, 'priority_rules': {}}

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"配置保存失败: {e}")
        return False

def get_gpu_info(force_refresh=False):
    """
    获取GPU信息（使用GPUManager服务）
    
    Args:
        force_refresh: 是否强制刷新缓存
        
    Returns:
        List[Dict]: GPU信息列表
    """
    try:
        from core.di_container import ServiceProvider
        from core.gpu_manager import GPUManager
        
        gpu_manager = ServiceProvider.try_get(GPUManager)
        if gpu_manager is None:
            gpu_manager = GPUManager()
            logger.warning("GPUManager未在DI容器中注册，使用临时实例")
        
        gpus = gpu_manager.get_gpu_info(force_refresh=force_refresh)
        logger.info(f"GPU检测完成，共找到 {len(gpus)} 个GPU")
        return gpus
        
    except Exception as e:
        logger.error(f"GPU检测失败: {e}")
        return []

def get_gpu_settings_from_registry():
    settings = {}
    try:
        import winreg
        reg_path = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    if 'DXGK_DEVICE' in value:
                        exe_name = os.path.basename(name).lower()
                        if exe_name not in settings:
                            settings[exe_name] = {'path': name, 'gpu_preference': 'custom'}
                    i += 1
                except OSError:
                    break
    except:
        pass
    return settings

def set_gpu_preference(exe_path, preference):
    if not is_admin():
        print("需要管理员权限才能修改GPU设置")
        return False
    
    try:
        import winreg
        
        gpu_codes = {
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
        print(f"修改GPU设置失败: {e}")
        return False

def get_system_metrics(skip_gpu=False):
    """获取系统指标，支持跳过GPU检测以提高性能"""
    # 快速获取CPU百分比（非阻塞模式）
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # 根据性能模式决定是否检测GPU
    gpus = []
    if not skip_gpu and should_detect_gpu():
        try:
            gpus = get_gpu_info()
        except Exception as e:
            logger.debug(f"GPU检测失败（性能优化跳过）: {e}")
            gpus = []
    
    # 磁盘分区信息（简化获取，减少IO操作）
    disk_partitions = []
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_partitions.append({
                    'device': part.device,
                    'mountpoint': part.mountpoint,
                    'percent': usage.percent,
                    'free': usage.free / (1024 ** 3)
                })
            except Exception:
                pass
    except Exception:
        pass
    
    return {
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'disk_percent': disk.percent,
        'memory_total': memory.total / (1024 ** 3),
        'memory_available': memory.available / (1024 ** 3),
        'cpu_count': psutil.cpu_count(),
        'gpus': gpus,
        'disk_partitions': disk_partitions
    }

def need_admin(process_name_lower):
    return process_name_lower in NEED_ADMIN_PROCESSES

def is_protected(process_name_lower):
    return process_name_lower in PROTECTED_PROCESSES

_scorer = None

def get_scorer():
    global _scorer
    if _scorer is None:
        _scorer = PriorityScorer()
    return _scorer

def score_to_priority(score: float) -> Tuple[str, str]:
    return get_scorer().score_to_priority(score)

def get_priority_key(priority_value: int) -> str:
    return get_scorer().get_priority_key(priority_value)

def calculate_priority_score(process, system_metrics, config):
    """计算进程优先级分数，支持性能优化模式"""
    try:
        # 基础指标获取（这些是必须的）
        cpu_percent = process.cpu_percent(interval=None)
        if cpu_percent > 100:
            cpu_percent = 50
        
        memory_percent = process.memory_percent()
        process_name = process.name().lower()
        
        # 根据性能模式决定是否获取详细信息
        enable_detailed = should_enable_detailed_analysis()
        
        # 内存信息（快速模式下跳过详细内存信息）
        memory_rss = 0
        memory_vms = 0
        if enable_detailed:
            try:
                memory_info = process.memory_info()
                memory_rss = memory_info.rss / (1024 ** 2)
                memory_vms = memory_info.vms / (1024 ** 2)
            except:
                pass
        
        # IO计数器（快速模式下跳过，IO操作相对耗时）
        io_read = 0
        io_write = 0
        if enable_detailed:
            try:
                io_counters = process.io_counters()
                io_read = io_counters.read_bytes / (1024 ** 2)
                io_write = io_counters.write_bytes / (1024 ** 2)
            except:
                pass
        
        # 线程数
        try:
            num_threads = process.num_threads()
        except:
            num_threads = 1
        
        # 进程运行时间（快速模式下跳过）
        uptime = 3600  # 默认值
        if enable_detailed:
            try:
                create_time = process.create_time()
                uptime = time.time() - create_time
            except:
                pass
        
        # 进程状态（快速模式下跳过）
        status = 'running'
        if enable_detailed:
            try:
                status = process.status()
            except:
                pass
        
        # 进程类型分类（使用缓存）
        proc_type = classify_process(process_name)
        
        # 可执行文件路径
        exe_path = ""
        try:
            exe_path = process.exe()
        except:
            pass
        
        # 窗口标题和公司名称（快速模式下跳过）
        window_title = None
        company_name = None
        if enable_detailed:
            window_title = get_process_window_title(process.pid)
            company_name = get_process_company_name(exe_path) if exe_path else None
        
        # 应用分类（使用缓存）
        category, cat_info = classify_app(process.name(), exe_path, window_title, company_name)
        
        metrics = {
            'cpu': min(100, cpu_percent),
            'memory': min(100, memory_percent),
            'threads': num_threads,
            'io': min(100, (io_read + io_write) / 50),
            'uptime': uptime,
            'status': status,
            'category': category,
            'proc_type': proc_type,
            'exe_path': exe_path,
            'window_title': window_title,
            'company_name': company_name
        }
        
        score, details = cross_analysis_scoring(metrics, system_metrics, config)
        
        return min(100, max(0, score)), cpu_percent, memory_percent, proc_type, {
            'memory_rss': memory_rss,
            'memory_vms': memory_vms,
            'io_read': io_read,
            'io_write': io_write,
            'num_threads': num_threads,** details
        }
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return None, None, None, None, None

def evaluate_condition(condition, metrics):
    field = condition.get('field')
    operator = condition.get('operator')
    value = condition.get('value')
    
    field_value = metrics.get(field, 0)
    
    if operator == '>':
        return field_value > value
    elif operator == '<':
        return field_value < value
    elif operator == '>=':
        return field_value >= value
    elif operator == '<=':
        return field_value <= value
    elif operator == '==':
        return field_value == value
    elif operator == '!=':
        return field_value != value
    
    return False

def cross_analysis_scoring(metrics, system_metrics, config, use_ml=False):
    scores = {}
    details = {}
    
    if use_ml and ML_MODEL:
        ml_score = ML_MODEL.predict_score(metrics)
        details['scoring_method'] = 'ml'
        return ml_score, details
    
    weights = {
        'cpu_weight': 25,
        'memory_weight': 20,
        'threads_weight': 10,
        'io_weight': 8,
        'uptime_weight': 7,
        'status_weight': 5,
        'type_weight': 15
    }
    
    category_base_scores = {
        'gaming': 75, 'video': 55, 'browser': 45, 'productivity': 45,
        'development': 55, 'design': 65, 'ai': 65, 'system': 50,
        'security': 40, 'utility': 40, 'communication': 42,
        'music': 42, 'cloud': 40, 'unknown': 45
    }
    
    type_bonus_map = {
        'user_app': 8, 'system': 5, 'service': 2, 'background': -5, 'unknown': 0
    }
    
    status_scores = {
        'running': 5, 'sleeping': -3, 'waiting': -2, 'stopped': -10, 'zombie': -15
    }
    
    if CONFIG_MANAGER:
        try:
            rules = CONFIG_MANAGER.get_scoring_rules()
            weights = rules.get('weights', weights)
            category_base_scores = rules.get('category_base_scores', category_base_scores)
            type_bonus_map = rules.get('process_type_bonus', type_bonus_map)
            status_scores = rules.get('status_scores', status_scores)
        except Exception as e:
            print(f"加载评分规则失败: {e}")
    
    scores['category_base'] = category_base_scores.get(metrics['category'], 45)
    
    cpu_weight = weights.get('cpu_weight', 25)
    scores['cpu'] = min(cpu_weight, metrics['cpu'] * (cpu_weight / 20))
    
    memory_weight = weights.get('memory_weight', 20)
    scores['memory'] = min(memory_weight, metrics['memory'] * (memory_weight / 25))
    
    threads_weight = weights.get('threads_weight', 10)
    scores['threads'] = min(threads_weight, min(metrics['threads'], 50) * (threads_weight / 50))
    
    io_weight = weights.get('io_weight', 8)
    scores['io'] = min(io_weight, metrics['io'])
    
    uptime_weight = weights.get('uptime_weight', 7)
    uptime_score = CONFIG_MANAGER.calculate_uptime_score(metrics['uptime']) if CONFIG_MANAGER else 0
    scores['uptime'] = uptime_score
    
    status_weight = weights.get('status_weight', 5)
    status_score = status_scores.get(metrics['status'], 0) * (status_weight / 5)
    scores['status'] = status_score
    
    type_weight = weights.get('type_weight', 15)
    type_bonus = type_bonus_map.get(metrics['proc_type'], 0) * (type_weight / 8)
    scores['type'] = type_bonus
    
    base_score = sum(scores.values())
    
    cross_factors = []
    
    if CONFIG_MANAGER:
        try:
            cross_config = CONFIG_MANAGER.get_cross_factors()
            for factor in cross_config.get('factors', []):
                category = factor.get('category')
                conditions = factor.get('conditions', [])
                logic = factor.get('logic', 'AND')
                score_bonus = factor.get('score_bonus', 0)
                
                category_match = False
                if category == '*':
                    category_match = True
                elif isinstance(category, list):
                    category_match = metrics['category'] in category
                else:
                    category_match = metrics['category'] == category
                
                if not category_match:
                    continue
                
                condition_results = []
                for cond in conditions:
                    condition_results.append(evaluate_condition(cond, metrics))
                
                if logic == 'AND':
                    all_true = all(condition_results)
                else:
                    all_true = any(condition_results)
                
                if all_true:
                    cross_factors.append((factor.get('id', 'unknown'), score_bonus))
        except Exception as e:
            print(f"加载跨因素规则失败: {e}")
    
    if not cross_factors:
        if metrics['category'] == 'gaming':
            if metrics['cpu'] > 30 or metrics['memory'] > 15:
                cross_factors.append(('gaming_active', 10))
            if metrics['threads'] > 30:
                cross_factors.append(('gaming_threads', 5))
        elif metrics['category'] == 'design' or metrics['category'] == 'ai':
            if metrics['memory'] > 20:
                cross_factors.append(('heavy_memory', 8))
            if metrics['cpu'] > 40:
                cross_factors.append(('heavy_cpu', 5))
        elif metrics['category'] == 'browser':
            if metrics['memory'] > 30:
                cross_factors.append(('browser_memory', -5))
            if metrics['cpu'] > 50:
                cross_factors.append(('browser_cpu', 5))
        
        if metrics['proc_type'] == 'user_app' and metrics['status'] == 'running':
            cross_factors.append(('active_user_app', 5))
        
        if metrics['threads'] > 50 and metrics['cpu'] > 20:
            cross_factors.append(('heavy_compute', 8))
        
        if metrics['cpu'] < 2 and metrics['memory'] < 2 and metrics['status'] == 'sleeping':
            cross_factors.append(('idle_process', -10))
    
    cross_bonus = sum(f[1] for f in cross_factors)
    details['cross_factors'] = [f[0] for f in cross_factors]
    
    system_adjustment = 0
    if CONFIG_MANAGER:
        try:
            cross_config = CONFIG_MANAGER.get_cross_factors()
            for adj in cross_config.get('system_adjustments', []):
                condition = adj.get('condition', {})
                adjustment = adj.get('adjustment', 0)
                
                sys_metrics = {
                    'system_cpu': system_metrics.get('cpu_percent', 0),
                    'system_memory': system_metrics.get('memory_percent', 0)
                }
                
                if evaluate_condition(condition, sys_metrics):
                    system_adjustment += adjustment
        except Exception as e:
            print(f"加载系统调整规则失败: {e}")
    
    if system_adjustment == 0:
        if system_metrics['cpu_percent'] > 80:
            system_adjustment = -8
        elif system_metrics['cpu_percent'] < 20:
            system_adjustment = 5
        
        if system_metrics['memory_percent'] > 85:
            system_adjustment -= 5
        elif system_metrics['memory_percent'] < 40:
            system_adjustment += 3
    
    scores['system'] = system_adjustment
    
    rule_adjustment = 0
    if 'priority_rules' in config:
        process_name = config.get('current_process_name', '')
        for rule_name, rule in config['priority_rules'].items():
            if 'process_name' in rule and rule['process_name'].lower() in process_name:
                if 'score_adjustment' in rule:
                    rule_adjustment += rule['score_adjustment']
    
    final_score = base_score + cross_bonus + system_adjustment + rule_adjustment
    
    details['score_breakdown'] = {k: round(v, 1) for k, v in scores.items()}
    details['cross_bonus'] = cross_bonus
    details['system_adjustment'] = system_adjustment
    details['scoring_method'] = 'rule_based'
    
    return final_score, details

def analyze_process(process, system_metrics, admin_mode, config):
    try:
        if process.pid == 0:
            return {'name': 'System Idle Process', 'pid': 0, 'status': 'system_skip', 'reason': '系统空闲进程'}
        
        process_name = process.name()
        process_name_lower = process_name.lower()
        
        if is_protected(process_name_lower):
            try:
                current_priority = process.nice()
                priority_name = PRIORITY_DISPLAY.get(get_priority_key(current_priority), '未知')
                return {'name': process_name, 'pid': process.pid, 'status': 'protected', 
                        'reason': '系统保护进程', 'current_priority': priority_name}
            except Exception as e:
                logger.debug(f"读取保护进程 {process_name} 优先级失败: {e}")
                return {'name': process_name, 'pid': process.pid, 'status': 'protected', 
                        'reason': '系统保护进程', 'current_priority': '未知'}
        
        if need_admin(process_name_lower) and not admin_mode:
            logger.debug(f"进程 {process_name} 需要管理员权限")
            return {'name': process_name, 'pid': process.pid, 'status': 'need_admin', 'reason': '需要管理员权限'}
        
        score, cpu_percent, memory_percent, proc_type, details = calculate_priority_score(process, system_metrics, config)
        
        if score is None:
            logger.debug(f"无法读取进程 {process_name} 信息")
            return {'name': process_name, 'pid': process.pid, 'status': 'access_denied', 'reason': '无法读取进程信息'}
        
        priority_key, priority_name = score_to_priority(score)
        
        try:
            old_priority = process.nice()
        except psutil.AccessDenied as e:
            if process_name_lower in KNOWN_LIMITED_PROCESSES:
                logger.debug(f"读取受限进程 {process_name} 优先级失败(预期行为)")
            else:
                logger.warning(f"读取进程 {process_name} 优先级失败: {e}")
            return {'name': process_name, 'pid': process.pid, 'status': 'access_denied', 'reason': '无法读取优先级'}
        
        # 记录原始优先级（首次运行时）
        global priority_restore_manager
        priority_restore_manager.record_original_priority(process_name, old_priority)
        
        # 检查是否在黑名单中
        if priority_restore_manager.is_blacklisted(process_name):
            old_priority_name = PRIORITY_DISPLAY.get(get_priority_key(old_priority), '未知')
            return {'name': process_name, 'pid': process.pid, 'status': 'blacklisted', 
                    'reason': '黑名单进程', 'current_priority': old_priority_name}
        
        new_priority_value = PRIORITY_LEVELS[priority_key]
        old_priority_name = PRIORITY_DISPLAY.get(get_priority_key(old_priority), '未知')
        
        if old_priority != new_priority_value:
            try:
                process.nice(new_priority_value)
                logger.info(f"进程 {process_name}(PID:{process.pid}) 优先级已从 {old_priority_name} 调整为 {priority_name}")
            except psutil.AccessDenied as e:
                if process_name_lower in KNOWN_LIMITED_PROCESSES:
                    logger.debug(f"设置受限进程 {process_name} 优先级失败(预期行为)")
                else:
                    logger.warning(f"设置进程 {process_name} 优先级失败: {e}")
                return {'name': process_name, 'pid': process.pid, 'status': 'access_denied', 'reason': '无法设置优先级'}
        
        result = {
            'name': process_name,
            'pid': process.pid,
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'proc_type': proc_type,
            'score': round(score, 1),
            'old_priority': old_priority_name,
            'new_priority': priority_name,
            'status': 'success'
        }
        
        if details:
            result.update(details)
        
        return result
    except psutil.NoSuchProcess:
        logger.debug(f"进程 {process_name if 'process_name' in dir() else 'unknown'} 已终止")
        return {'name': 'unknown', 'pid': 0, 'status': 'no_such_process', 'reason': '进程已终止'}
    except psutil.AccessDenied as e:
        logger.warning(f"访问进程被拒绝: {e}")
        return {'name': process_name if 'process_name' in dir() else 'unknown', 
                'pid': process.pid if 'process' in dir() and hasattr(process, 'pid') else 0, 
                'status': 'access_denied', 'reason': '访问被拒绝'}

def search_processes(keyword=None):
    results = []
    keyword_lower = keyword.lower() if keyword else None
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = proc.name().lower()
            if keyword_lower and keyword_lower not in name:
                continue
            results.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return results

def get_all_windows_services(keyword=None):
    """
    查询所有Windows服务，包括运行中和未运行的服务
    返回服务列表，每个服务包含名称、显示名称、状态、启动类型等信息
    不执行优先级调整，仅用于显示
    """
    services = []
    keyword_lower = keyword.lower() if keyword else None
    
    # 预获取所有进程信息（只执行一次，避免重复遍历）
    process_name_to_pid = {}
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                process_name_to_pid[proc.name().lower()] = proc.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    
    # 使用pywin32获取服务信息
    try:
        import win32service
        import win32serviceutil
        import win32con
        
        scm_handle = win32service.OpenSCManager(
            None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE
        )
        
        try:
            service_types = win32service.SERVICE_WIN32
            service_states = win32service.SERVICE_STATE_ALL
            
            services_info = win32service.EnumServicesStatus(
                scm_handle, service_types, service_states
            )
            
            for service_name, display_name, service_status in services_info:
                service_name_lower = service_name.lower()
                
                # 关键词过滤
                if keyword_lower:
                    if (keyword_lower not in service_name_lower and 
                        keyword_lower not in display_name.lower()):
                        continue
                
                status_code = service_status[1]
                status_map = {
                    win32service.SERVICE_STOPPED: '已停止',
                    win32service.SERVICE_START_PENDING: '正在启动',
                    win32service.SERVICE_STOP_PENDING: '正在停止',
                    win32service.SERVICE_RUNNING: '正在运行',
                    win32service.SERVICE_CONTINUE_PENDING: '正在继续',
                    win32service.SERVICE_PAUSE_PENDING: '正在暂停',
                    win32service.SERVICE_PAUSED: '已暂停'
                }
                status = status_map.get(status_code, '未知')
                is_running = status_code == win32service.SERVICE_RUNNING
                
                # 获取启动类型
                start_type = '未知'
                service_pid = None
                try:
                    service_handle = win32service.OpenService(
                        scm_handle, service_name, 
                        win32service.SERVICE_QUERY_CONFIG | win32service.SERVICE_QUERY_STATUS
                    )
                    try:
                        # 获取启动类型
                        config = win32service.QueryServiceConfig(service_handle)
                        start_type_code = config[0]
                        start_type_map = {
                            win32service.SERVICE_BOOT_START: '系统启动',
                            win32service.SERVICE_SYSTEM_START: '系统启动',
                            win32service.SERVICE_AUTO_START: '自动',
                            win32service.SERVICE_DEMAND_START: '手动',
                            win32service.SERVICE_DISABLED: '已禁用'
                        }
                        start_type = start_type_map.get(start_type_code, '未知')
                        
                        # 获取服务PID（仅对运行中的服务）
                        if is_running:
                            try:
                                # 使用QueryServiceStatusEx获取进程ID
                                status_info = win32service.QueryServiceStatusEx(service_handle)
                                service_pid = status_info.get('ProcessId', None)
                            except Exception:
                                # 备用方法：通过预获取的进程映射查找
                                pass
                    finally:
                        win32service.CloseServiceHandle(service_handle)
                except Exception:
                    pass
                
                # 如果没有获取到PID，尝试通过进程名查找（使用预获取的映射）
                if is_running and service_pid is None and process_name_to_pid:
                    try:
                        service_exe_pattern = service_name.lower()
                        for proc_name, pid in process_name_to_pid.items():
                            if service_exe_pattern in proc_name:
                                service_pid = pid
                                break
                    except Exception:
                        pass
                
                services.append({
                    'name': service_name,
                    'display_name': display_name,
                    'status': status,
                    'status_code': status_code,
                    'start_type': start_type,
                    'pid': service_pid,
                    'is_running': is_running
                })
                
        finally:
            win32service.CloseServiceHandle(scm_handle)
            
        logger.info(f"找到 {len(services)} 个Windows服务")
        return services
            
    except ImportError:
        logger.warning("pywin32未安装")
        # 备用方法：使用subprocess调用sc命令
        try:
            import subprocess
            
            # 获取所有服务列表
            result = subprocess.run(
                ['powershell', '-Command', 'Get-Service | Select-Object Name, DisplayName, Status, StartType | ConvertTo-Json'],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0 and result.stdout:
                import json
                service_list = json.loads(result.stdout)
                
                # 确保是列表格式
                if isinstance(service_list, dict):
                    service_list = [service_list]
                
                for svc in service_list:
                    name = svc.get('Name', '')
                    display_name = svc.get('DisplayName', '')
                    status_code = svc.get('Status', 0)
                    start_type_code = svc.get('StartType', '')
                    
                    if keyword_lower:
                        if (keyword_lower not in name.lower() and 
                            keyword_lower not in display_name.lower()):
                            continue
                    
                    status_map = {
                        1: '已停止',
                        2: '正在启动',
                        3: '正在停止',
                        4: '正在运行',
                        5: '正在继续',
                        6: '正在暂停',
                        7: '已暂停'
                    }
                    status = status_map.get(status_code, '未知')
                    is_running = status_code == 4
                    
                    start_type_map = {
                        'Automatic': '自动',
                        'Manual': '手动',
                        'Disabled': '已禁用',
                        'Boot': '系统启动',
                        'System': '系统启动'
                    }
                    start_type = start_type_map.get(str(start_type_code), '未知')
                    
                    services.append({
                        'name': name,
                        'display_name': display_name,
                        'status': status,
                        'status_code': status_code,
                        'start_type': start_type,
                        'pid': None,
                        'is_running': is_running
                    })
                    
            logger.info(f"找到 {len(services)} 个Windows服务 (PowerShell)")
            return services
                
        except Exception as e:
            logger.error(f"查询Windows服务失败: {e}")
            
    except Exception as e:
        logger.error(f"查询Windows服务失败: {e}")
    
    logger.info(f"找到 {len(services)} 个Windows服务")
    return services

def analyze_all_services(keyword=None, display_only=True):
    """
    分析所有Windows服务，显示服务状态但不执行优先级调整
    
    Args:
        keyword: 可选的关键词，用于过滤服务
        display_only: 是否仅显示而不执行优先级调整（默认为True）
    
    Returns:
        服务列表，包含详细的状态信息
    """
    logger.info("开始分析Windows服务")
    
    # 获取所有服务
    services = get_all_windows_services(keyword)
    
    # 添加额外的分析信息
    for service in services:
        # 标记服务类型
        service_name_lower = service['name'].lower()
        
        # 判断服务类型
        if service_name_lower in SYSTEM_PROCESSES:
            service['category'] = 'system'
            service['category_display'] = '系统服务'
        elif service_name_lower in USER_APP_PROCESSES:
            service['category'] = 'user_app'
            service['category_display'] = '用户应用服务'
        else:
            # 根据服务名称推断类型
            if any(keyword in service_name_lower for keyword in ['windows', 'microsoft', 'system']):
                service['category'] = 'system'
                service['category_display'] = '系统服务'
            elif any(keyword in service_name_lower for keyword in ['chrome', 'edge', 'firefox', 'steam', 'spotify']):
                service['category'] = 'user_app'
                service['category_display'] = '用户应用服务'
            else:
                service['category'] = 'unknown'
                service['category_display'] = '其他服务'
        
        # 标记是否可以调整优先级
        service['can_adjust_priority'] = (
            service['is_running'] and 
            service['pid'] is not None and 
            service_name_lower not in PROTECTED_PROCESSES
        )
        
        # 优先级显示（仅用于显示，不实际调整）
        if service['is_running'] and service['pid']:
            try:
                proc = psutil.Process(service['pid'])
                priority_value = proc.nice()
                priority_key = get_priority_key(priority_value)
                service['current_priority'] = PRIORITY_DISPLAY.get(priority_key, '未知')
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                service['current_priority'] = '无法获取'
        else:
            service['current_priority'] = 'N/A'
    
    # 统计信息
    running_count = sum(1 for s in services if s['is_running'])
    stopped_count = len(services) - running_count
    
    logger.info(f"服务分析完成: 运行中 {running_count} 个, 已停止 {stopped_count} 个, 总计 {len(services)} 个")
    
    # 如果display_only为True，仅返回结果不执行任何调整
    if display_only:
        return services
    
    # 如果display_only为False，可以在这里添加优先级调整逻辑
    # 但根据用户要求，默认情况下不执行优先级调整
    return services

def analyze_all_processes(use_incremental=False):
    try:
        logger.info("开始分析所有进程")
        system_metrics = get_system_metrics()
        admin_mode = is_admin()
        config = load_config()
        
        if not hasattr(APP, '_initialized') or not APP._initialized:
            APP.initialize()
        
        if use_incremental and APP.incremental_scanner:
            new_procs, terminated_procs, changed_procs = APP.incremental_scanner.scan()
            logger.info(f"增量扫描: 新增 {len(new_procs)} 个, 终止 {len(terminated_procs)} 个, 变化 {len(changed_procs)} 个")
            
            processes_to_analyze = []
            for snapshot in new_procs:
                try:
                    proc = psutil.Process(snapshot.pid)
                    processes_to_analyze.append(proc)
                except psutil.NoSuchProcess:
                    continue
            
            for snapshot in changed_procs:
                try:
                    proc = psutil.Process(snapshot.pid)
                    processes_to_analyze.append(proc)
                except psutil.NoSuchProcess:
                    continue
            
            if not processes_to_analyze:
                logger.info("没有需要分析的进程")
                return []
        else:
            processes_to_analyze = search_processes()
            if APP.incremental_scanner:
                APP.incremental_scanner.reset()
        
        logger.info(f"找到 {len(processes_to_analyze)} 个进程")
        results = parallel_analyze(processes_to_analyze, system_metrics, admin_mode, config)
        
        success_count = sum(1 for r in results if r.get('status') == 'success')
        logger.info(f"进程分析完成: 成功 {success_count} 个, 总计 {len(results)} 个")
        
        return results
    except Exception as e:
        logger.error(f"分析进程失败: {e}")
        return []

def get_process_list_for_snapshot():
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info', 'num_threads']):
        try:
            processes.append({
                'pid': proc.pid,
                'name': proc.name(),
                'cpu_percent': proc.cpu_percent(interval=None),
                'memory_percent': proc.memory_percent(),
                'memory_rss': proc.memory_info().rss if proc.memory_info() else 0,
                'num_threads': proc.num_threads(),
                'priority': 'normal',
                'score': 0,
                'category': 'unknown'
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

def search_exe_files(max_results=100):
    exe_files = []
    try:
        for drive in psutil.disk_partitions(all=False):
            try:
                root_path = drive.mountpoint
                pattern = os.path.join(root_path, '**', '*.exe')
                for file_path in glob.iglob(pattern, recursive=True):
                    try:
                        if os.path.isfile(file_path):
                            size = os.path.getsize(file_path) / (1024 ** 2)
                            exe_files.append({
                                'path': file_path,
                                'size': size,
                                'name': os.path.basename(file_path)
                            })
                        if len(exe_files) >= max_results:
                            break
                    except:
                        continue
                if len(exe_files) >= max_results:
                    break
            except:
                continue
    except:
        pass
    return exe_files

def analyze_process_wrapper(args):
    proc, system_metrics, admin_mode, config = args
    try:
        return analyze_process(proc, system_metrics, admin_mode, config)
    except Exception as e:
        logger.debug(f"进程分析包装函数异常: {e}")
        return None

def parallel_analyze(processes, system_metrics, admin_mode, config):
    """并行分析进程，根据性能模式动态调整线程池大小"""
    if not processes:
        return []
    
    process_count = len(processes)
    
    # 根据性能模式获取线程池大小，避免占用过多资源
    base_workers = get_thread_pool_size()
    max_workers = min(base_workers, process_count)
    
    logger.debug(f"并行分析: {process_count} 个进程, 使用 {max_workers} 线程")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        args = [(proc, system_metrics, admin_mode, config) for proc in processes]
        results = list(executor.map(analyze_process_wrapper, args))
    
    return [r for r in results if r is not None]

def write_log(log_entries):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n")
            for entry in log_entries:
                f.write(entry + '\n')
        return True
    except Exception as e:
        print(f"日志写入失败: {e}")
        return False

def batch_configure_gpu(exe_files, config, gpu_choice):
    success_count = 0
    fail_count = 0
    
    gpu_map = {'a': 'auto', 'i': 'integrated', 'd': 'discrete'}
    gpu_value = gpu_map.get(gpu_choice)
    
    for exe_info in exe_files:
        exe_path = exe_info['path']
        exe_name = exe_info['name']
        
        try:
            if set_gpu_preference(exe_path, gpu_value):
                config['gpu_settings'][exe_name] = gpu_value
                success_count += 1
            else:
                fail_count += 1
        except:
            fail_count += 1
    
    save_config(config)
    print(f"\n批量配置完成: 成功 {success_count} 个, 失败 {fail_count} 个")

def scan_and_configure(config):
    print("\n" + "=" * 70)
    print("                批量配置工具")
    print("=" * 70)
    
    print("\n正在扫描所有磁盘分区中的EXE文件...")
    exe_files = search_exe_files(max_results=500)
    print(f"找到 {len(exe_files)} 个EXE文件")
    
    print("\n按应用类型筛选:")
    print("1. 游戏应用 (game, steam, epic等)")
    print("2. 设计软件 (photoshop, blender等)")
    print("3. 浏览器 (chrome, edge等)")
    print("4. 办公软件 (word, excel等)")
    print("5. 全部应用")
    
    try:
        choice = input("\n请输入选择 (1-5): ")
        
        filtered_files = []
        category_name = ""
        
        if choice == '1':
            category_name = "游戏应用"
            for exe in exe_files:
                category, _ = classify_app(exe['name'])
                if category == 'gaming':
                    filtered_files.append(exe)
        elif choice == '2':
            category_name = "设计软件"
            for exe in exe_files:
                category, _ = classify_app(exe['name'])
                if category == 'design':
                    filtered_files.append(exe)
        elif choice == '3':
            category_name = "浏览器"
            for exe in exe_files:
                category, _ = classify_app(exe['name'])
                if category == 'browser':
                    filtered_files.append(exe)
        elif choice == '4':
            category_name = "办公软件"
            for exe in exe_files:
                category, _ = classify_app(exe['name'])
                if category == 'productivity':
                    filtered_files.append(exe)
        elif choice == '5':
            category_name = "全部应用"
            filtered_files = exe_files
        else:
            print("无效选择")
            return
        
        print(f"\n找到 {len(filtered_files)} 个{category_name}:")
        for i, exe in enumerate(filtered_files[:10], 1):
            print(f"  {i}. {exe['name']} ({exe['size']:.1f} MB)")
        if len(filtered_files) > 10:
            print(f"  ... 还有 {len(filtered_files) - 10} 个")
        
        if len(filtered_files) == 0:
            print("  没有找到匹配的应用")
            return
        
        confirm = input(f"\n确定要为 {len(filtered_files)} 个{category_name}配置GPU吗? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        print("\nGPU选项:")
        print("  a - 让 Windows 决定")
        print("  i - 节能 (集成显卡)")
        print("  d - 高性能 (独立显卡)")
        gpu_choice = input("请选择GPU (a/i/d): ").strip().lower()
        
        if gpu_choice in ['a', 'i', 'd']:
            batch_configure_gpu(filtered_files, config, gpu_choice)
        else:
            print("无效选择")
    
    except KeyboardInterrupt:
        print("\n已取消操作")
    except ValueError:
        print("输入无效")

WINDOWS_BUNDLED_APPS = {
    '3dbuilder': {'name': '3D Builder', 'description': '3D建模工具', 'safe': True},
    'alarms': {'name': '闹钟和时钟', 'description': '闹钟应用', 'safe': False},
    'appconnector': {'name': 'App Connector', 'description': '应用连接器', 'safe': True},
    'bingfinance': {'name': 'MSN财经', 'description': '财经新闻', 'safe': True},
    'bingnews': {'name': 'MSN新闻', 'description': '新闻应用', 'safe': True},
    'bingsports': {'name': 'MSN体育', 'description': '体育新闻', 'safe': True},
    'bingweather': {'name': '天气', 'description': '天气应用', 'safe': False},
    'calculator': {'name': '计算器', 'description': '计算器应用', 'safe': False},
    'calendar': {'name': '日历', 'description': '日历应用', 'safe': False},
    'camera': {'name': '相机', 'description': '相机应用', 'safe': False},
    'communicationsapps': {'name': '通信应用', 'description': '邮件和日历', 'safe': False},
    'contacts': {'name': '联系人', 'description': '联系人管理', 'safe': False},
    'cortana': {'name': 'Cortana', 'description': '语音助手', 'safe': True},
    'desktopappinstaller': {'name': '应用安装器', 'description': '应用安装工具', 'safe': False},
    'email': {'name': '邮件', 'description': '邮件应用', 'safe': False},
    'feedbackhub': {'name': '反馈中心', 'description': '反馈工具', 'safe': True},
    'getstarted': {'name': '入门', 'description': '新手入门指南', 'safe': True},
    'maps': {'name': '地图', 'description': '地图应用', 'safe': True},
    'messaging': {'name': '消息', 'description': '短信应用', 'safe': False},
    'microsoft3dviewer': {'name': '3D查看器', 'description': '3D文件查看器', 'safe': True},
    'microsoftedge': {'name': 'Microsoft Edge', 'description': '浏览器', 'safe': False},
    'microsoftsolitairecollection': {'name': '微软纸牌合集', 'description': '游戏合集', 'safe': True},
    'microsoftstickyNotes': {'name': '便笺', 'description': '便笺应用', 'safe': False},
    'money': {'name': 'Microsoft Money', 'description': '理财应用', 'safe': True},
    'music': {'name': '音乐', 'description': '音乐播放器', 'safe': False},
    'news': {'name': '新闻', 'description': '新闻应用', 'safe': True},
    'notepad': {'name': '记事本', 'description': '记事本应用', 'safe': False},
    'onenote': {'name': 'OneNote', 'description': '笔记应用', 'safe': False},
    'people': {'name': '人脉', 'description': '联系人应用', 'safe': True},
    'photos': {'name': '照片', 'description': '照片查看器', 'safe': False},
    'paint': {'name': '画图', 'description': '画图应用', 'safe': False},
    'paint3d': {'name': '画图3D', 'description': '3D画图', 'safe': True},
    'phone': {'name': '手机连接', 'description': '手机连接工具', 'safe': True},
    'pocket': {'name': 'Pocket', 'description': '稍后阅读', 'safe': True},
    'skype': {'name': 'Skype', 'description': '通讯工具', 'safe': True},
    'store': {'name': 'Microsoft Store', 'description': '应用商店', 'safe': False},
    'tips': {'name': '提示', 'description': '使用提示', 'safe': True},
    'weather': {'name': '天气', 'description': '天气应用', 'safe': False},
    'whiteboard': {'name': '白板', 'description': '协作工具', 'safe': True},
    'windowsalarms': {'name': '闹钟', 'description': '闹钟应用', 'safe': False},
    'windowscommunicationsapps': {'name': '通信应用', 'description': '邮件和日历', 'safe': False},
    'windowscamera': {'name': '相机', 'description': '相机应用', 'safe': False},
    'windowsfeedbackhub': {'name': '反馈中心', 'description': '反馈工具', 'safe': True},
    'windowsmaps': {'name': '地图', 'description': '地图应用', 'safe': True},
    'windowsmediaplayer': {'name': 'Windows Media Player', 'description': '媒体播放器', 'safe': False},
    'windowsphone': {'name': '手机', 'description': '手机连接', 'safe': True},
    'windowsphotos': {'name': '照片', 'description': '照片应用', 'safe': False},
    'windowsscan': {'name': '扫描', 'description': '扫描工具', 'safe': True},
    'windowsstore': {'name': '应用商店', 'description': 'Microsoft Store', 'safe': False},
    'windowstips': {'name': '提示', 'description': '使用提示', 'safe': True},
    'worldclock': {'name': '世界时钟', 'description': '时钟应用', 'safe': True},
    'yourphone': {'name': '你的手机', 'description': '手机连接', 'safe': True},
    'zunemusic': {'name': 'Zune音乐', 'description': '音乐播放器', 'safe': True},
    'zunevideo': {'name': 'Zune视频', 'description': '视频播放器', 'safe': True},
}

SAFE_TO_REMOVE_DEFAULT = [
    '3dbuilder', 'appconnector', 'bingfinance', 'bingnews', 'bingsports',
    'cortana', 'feedbackhub', 'getstarted', 'maps', 'microsoft3dviewer',
    'microsoftsolitairecollection', 'money', 'news', 'people', 'paint3d',
    'phone', 'pocket', 'skype', 'tips', 'whiteboard', 'windowsfeedbackhub',
    'windowsmaps', 'windowsphone', 'windowsscan', 'windowstips', 'worldclock',
    'yourphone', 'zunemusic', 'zunevideo'
]

def get_pagefile_info():
    import subprocess
    try:
        result = subprocess.run(
            ['powershell', '-Command', '''
            $pagefile = Get-CimInstance -ClassName Win32_PageFileUsage
            $pagefileConfig = Get-CimInstance -ClassName Win32_PageFileSetting
            $totalMemory = (Get-CimInstance -ClassName Win32_ComputerSystem).TotalPhysicalMemory / 1GB
            [PSCustomObject]@{
                CurrentUsageGB = if ($pagefile) { $pagefile.CurrentUsage / 1024 } else { 0 }
                PeakUsageGB = if ($pagefile) { $pagefile.PeakUsage / 1024 } else { 0 }
                AllocatedGB = if ($pagefileConfig) { $pagefileConfig.AllocatedBaseSize / 1024 } else { 0 }
                MinSizeGB = if ($pagefileConfig) { $pagefileConfig.MinimumSize / 1024 } else { 0 }
                MaxSizeGB = if ($pagefileConfig) { $pagefileConfig.MaximumSize / 1024 } else { 0 }
                TotalRAM = $totalMemory
                Drive = if ($pagefile) { $pagefile.Name } else { "Unknown" }
            } | ConvertTo-Json
            '''.strip()],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except Exception as e:
        print(f"获取虚拟内存信息失败: {e}")
    return None

def suggest_pagefile_settings():
    print("\n" + "=" * 70)
    print("              虚拟内存（页面文件）优化建议")
    print("=" * 70)
    
    info = get_pagefile_info()
    if not info:
        print("无法获取虚拟内存信息")
        return
    
    total_ram = round(info['TotalRAM'], 1)
    current_usage = round(info['CurrentUsageGB'], 1)
    peak_usage = round(info['PeakUsageGB'], 1)
    allocated = round(info['AllocatedGB'], 1)
    min_size = round(info['MinSizeGB'], 1)
    max_size = round(info['MaxSizeGB'], 1)
    
    print(f"\n[当前系统配置]")
    print("-" * 50)
    print(f"物理内存: {total_ram} GB")
    print(f"虚拟内存当前使用: {current_usage} GB")
    print(f"虚拟内存峰值使用: {peak_usage} GB")
    print(f"当前分配大小: {allocated} GB")
    print(f"最小值: {min_size} GB")
    print(f"最大值: {max_size} GB")
    
    print("\n[推荐配置]")
    print("-" * 50)
    
    if total_ram <= 8:
        recommended_min = total_ram * 1.5
        recommended_max = total_ram * 2
        print(f"- 物理内存较小 (<=8GB)")
        print(f"  推荐: 最小值 {round(recommended_min,1)}GB, 最大值 {round(recommended_max,1)}GB")
    elif total_ram <= 16:
        recommended_min = total_ram
        recommended_max = total_ram * 1.5
        print(f"- 物理内存适中 (8GB-16GB)")
        print(f"  推荐: 最小值 {round(recommended_min,1)}GB, 最大值 {round(recommended_max,1)}GB")
    elif total_ram <= 32:
        recommended_min = total_ram * 0.5
        recommended_max = total_ram
        print(f"- 物理内存充足 (16GB-32GB)")
        print(f"  推荐: 最小值 {round(recommended_min,1)}GB, 最大值 {round(recommended_max,1)}GB")
    else:
        recommended_min = 8
        recommended_max = 16
        print(f"- 物理内存充裕 (>=32GB)")
        print(f"  推荐: 最小值 {recommended_min}GB, 最大值 {recommended_max}GB")
    
    print("\n[优化建议]")
    print("-" * 50)
    
    if max_size == 0 or min_size == 0:
        print("❌ 警告: 虚拟内存可能被禁用")
        print("   建议: 启用虚拟内存，设为系统管理或手动配置")
    elif max_size - min_size > 8:
        print("⚠️  提示: 虚拟内存范围过大")
        print("   建议: 将最大最小值设为相同或相近，减少磁盘碎片")
    elif allocated > total_ram * 2:
        print("⚠️  提示: 虚拟内存分配过大")
        print("   建议: 减少虚拟内存大小，避免占用过多磁盘空间")
    elif peak_usage > total_ram:
        print("⚠️  提示: 虚拟内存峰值使用较高")
        print("   建议: 考虑增加物理内存或调整虚拟内存配置")
    else:
        print("✅ 当前虚拟内存配置较为合理")
    
    print("\n[设置方法]")
    print("-" * 50)
    print("1. 右键点击「此电脑」→ 属性")
    print("2. 点击「高级系统设置」")
    print("3. 在「高级」选项卡点击「性能」区域的「设置」")
    print("4. 在「高级」选项卡点击「虚拟内存」区域的「更改」")
    print("5. 取消勾选「自动管理所有驱动器的分页文件大小」")
    print("6. 选择系统盘，设置「自定义大小」")
    print("7. 输入推荐的最小值和最大值，点击「设置」→「确定」")
    
    if is_admin():
        print("\n[快速设置]")
        print("-" * 50)
        print("是否需要我帮你设置虚拟内存？")
        print("[1] 设置为推荐值")
        print("[2] 设置为系统管理")
        print("[3] 返回")
        
        try:
            choice = input("\n请输入选择 (1-3): ").strip()
            if choice == '1':
                set_pagefile(recommended_min, recommended_max)
            elif choice == '2':
                set_pagefile_auto()
            elif choice == '3':
                return
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消")
        except ValueError:
            print("输入无效")

def set_pagefile(min_gb, max_gb):
    import subprocess
    try:
        min_mb = int(min_gb * 1024)
        max_mb = int(max_gb * 1024)
        
        command = f'''
        $drive = $env:SystemDrive
        Write-Host "正在设置虚拟内存: $drive"
        Write-Host "最小值: {min_mb} MB"
        Write-Host "最大值: {max_mb} MB"
        
        Set-CimInstance -ClassName Win32_PageFileSetting -Property @{{
            MinimumSize = {min_mb}
            MaximumSize = {max_mb}
        }} -Filter "Name='${{drive}}\\pagefile.sys'"
        
        if ($?) {{
            Write-Host "虚拟内存设置成功，需要重启生效"
        }} else {{
            Write-Host "设置失败"
        }}
        '''
        
        result = subprocess.run(
            ['powershell', '-Command', command],
            capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        print(result.stdout)
        if result.stderr:
            print(f"错误: {result.stderr}")
            
    except Exception as e:
        print(f"设置失败: {e}")

def set_pagefile_auto():
    import subprocess
    try:
        command = '''
        Write-Host "正在设置虚拟内存为系统管理..."
        Set-CimInstance -ClassName Win32_PageFileSetting -Property @{AutomaticManagedPagefile = $true}
        if ($?) {
            Write-Host "设置成功，需要重启生效"
        } else {
            Write-Host "设置失败"
        }
        '''
        
        result = subprocess.run(
            ['powershell', '-Command', command],
            capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        print(result.stdout)
        if result.stderr:
            print(f"错误: {result.stderr}")
            
    except Exception as e:
        print(f"设置失败: {e}")

def get_installed_apps():
    import subprocess
    try:
        result = subprocess.run(
            ['powershell', '-Command', 'Get-AppxPackage | Select-Object Name, PackageFullName, InstallLocation | ConvertTo-Json'],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            import json
            apps = json.loads(result.stdout)
            if isinstance(apps, dict):
                apps = [apps]
            return apps
    except Exception as e:
        print(f"获取应用列表失败: {e}")
    return []

def remove_app(package_full_name):
    if not is_admin():
        print("需要管理员权限才能卸载应用")
        return False
    
    import subprocess
    try:
        command = f'''
        $package = Get-AppxPackage -Package "{package_full_name}"
        if ($package) {{
            Write-Host "正在卸载: $($package.Name)"
            Remove-AppxPackage -Package "{package_full_name}" -ErrorAction SilentlyContinue
            if ($?) {{
                Write-Host "卸载成功"
                exit 0
            }} else {{
                Write-Host "卸载失败"
                exit 1
            }}
        }} else {{
            Write-Host "未找到应用"
            exit 2
        }}
        '''
        result = subprocess.run(
            ['powershell', '-Command', command],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0
    except Exception as e:
        print(f"卸载失败: {e}")
        return False

def remove_app_for_all_users(package_name):
    if not is_admin():
        print("需要管理员权限才能为所有用户卸载应用")
        return False
    
    import subprocess
    try:
        command = f'''
        $provisioned = Get-AppxProvisionedPackage -Online | Where-Object {{ $_.DisplayName -like "*{package_name}*" }}
        if ($provisioned) {{
            Write-Host "正在从系统中移除预置应用: $($provisioned.DisplayName)"
            Remove-AppxProvisionedPackage -Online -PackageName $provisioned.PackageName -ErrorAction SilentlyContinue
            if ($?) {{
                Write-Host "移除成功"
                exit 0
            }} else {{
                Write-Host "移除失败"
                exit 1
            }}
        }} else {{
            Write-Host "未找到预置应用"
            exit 2
        }}
        '''
        result = subprocess.run(
            ['powershell', '-Command', command],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0
    except Exception as e:
        print(f"移除预置应用失败: {e}")
        return False

def cleanup_windows_apps():
    print("\n" + "=" * 70)
    print("              Windows 自带应用清理器")
    print("=" * 70)
    print("\n📋 卸载方式说明:")
    print("   [方式1] Remove-AppxPackage - 卸载当前用户的应用")
    print("   [方式2] Remove-AppxProvisionedPackage - 从系统中移除预置应用")
    print("           (新用户登录时不会自动安装)")
    print("\n⚠️  警告: 此功能将卸载Windows自带应用")
    print("         请谨慎操作，部分应用卸载后可能影响系统功能")
    print("\n✅  安全卸载列表: 这些应用通常可以安全卸载")
    print("   - 3D Builder、新闻、体育、财经等")
    print("   - 游戏合集、提示、反馈中心等")
    print("\n❌  保护列表: 这些应用不建议卸载")
    print("   - 照片、相机、邮件、日历等")
    print("   - 应用商店、浏览器、计算器等")
    print("-" * 70)
    
    if not is_admin():
        print("\n❌ 当前不是管理员模式")
        print("请右键点击PowerShell -> 以管理员身份运行")
        return
    
    print("\n正在扫描已安装的UWP应用...")
    apps = get_installed_apps()
    
    if not apps:
        print("未能获取应用列表")
        return
    
    bing_apps = [app for app in apps if any(keyword in app['Name'].lower() for keyword in ['bing', 'msn'])]
    microsoft_apps = [app for app in apps if 'Microsoft.' in app['Name']]
    
    print(f"\n找到 {len(apps)} 个UWP应用")
    print(f"其中 {len(bing_apps)} 个Bing/MSN应用")
    
    print("\n[1] 一键清理推荐卸载的应用 (当前用户)")
    print("[2] 一键清理推荐卸载的应用 (所有用户)")
    print("[3] 查看所有可卸载应用")
    print("[4] 手动选择应用卸载")
    print("[5] 返回主菜单")
    
    try:
        choice = input("\n请输入选择 (1-5): ")
        
        if choice == '1' or choice == '2':
            print("\n即将卸载以下应用:")
            print("-" * 50)
            
            to_remove = []
            display_names = []
            for app in apps:
                app_name_lower = app['Name'].lower()
                for safe_key in SAFE_TO_REMOVE_DEFAULT:
                    if safe_key in app_name_lower:
                        info = WINDOWS_BUNDLED_APPS.get(safe_key, {'name': app['Name'], 'description': '未知'})
                        display_names.append(info['name'])
                        to_remove.append(app)
                        break
            
            if not to_remove:
                print("  没有找到可一键卸载的应用")
                return
            
            for name in display_names:
                print(f"  - {name}")
            
            method = "当前用户" if choice == '1' else "所有用户"
            confirm = input(f"\n确定要为 {method} 卸载这 {len(to_remove)} 个应用吗? (y/n): ").strip().lower()
            if confirm != 'y':
                print("已取消")
                return
            
            print("\n正在卸载...")
            success_count = 0
            fail_count = 0
            
            for app in to_remove:
                app_name_lower = app['Name'].lower()
                display_name = app['Name']
                for key, info in WINDOWS_BUNDLED_APPS.items():
                    if key in app_name_lower:
                        display_name = info['name']
                        break
                
                print(f"  正在卸载: {display_name}...", end="")
                success = False
                if choice == '1':
                    success = remove_app(app['PackageFullName'])
                else:
                    success = remove_app_for_all_users(app['Name'])
                
                if success:
                    print(" ✓")
                    success_count += 1
                else:
                    print(" ✗")
                    fail_count += 1
            
            print(f"\n卸载完成: 成功 {success_count} 个, 失败 {fail_count} 个")
            
            if choice == '2':
                print("\n💡 提示: 已从系统预置中移除应用")
                print("         新用户登录时将不会自动安装这些应用")
        
        elif choice == '3':
            print("\n[已安装的UWP应用]")
            print("-" * 70)
            print(f"{'序号':<5} {'名称':<35} {'状态':<10}")
            print("-" * 70)
            
            safe_apps = []
            unsafe_apps = []
            
            for app in sorted(apps, key=lambda x: x['Name']):
                app_name_lower = app['Name'].lower()
                is_safe = False
                display_name = app['Name']
                
                for key, info in WINDOWS_BUNDLED_APPS.items():
                    if key in app_name_lower:
                        display_name = info['name']
                        is_safe = info['safe']
                        break
                
                if is_safe:
                    safe_apps.append((display_name, app))
                else:
                    unsafe_apps.append((display_name, app))
            
            for i, (name, app) in enumerate(safe_apps, 1):
                print(f"{i:<5} {name:<35} ✅可卸载")
            
            for i, (name, app) in enumerate(unsafe_apps, len(safe_apps)+1):
                print(f"{i:<5} {name:<35} ❌不建议")
            
            print("\n提示: 标记为'可卸载'的应用通常可以安全删除")
        
        elif choice == '4':
            print("\n[选择要卸载的应用]")
            print("-" * 70)
            print(f"{'序号':<5} {'名称':<35} {'状态':<10}")
            print("-" * 70)
            
            safe_apps = []
            for app in sorted(apps, key=lambda x: x['Name']):
                app_name_lower = app['Name'].lower()
                is_safe = False
                display_name = app['Name']
                
                for key, info in WINDOWS_BUNDLED_APPS.items():
                    if key in app_name_lower:
                        display_name = info['name']
                        is_safe = info['safe']
                        break
                
                if is_safe:
                    safe_apps.append((display_name, app))
            
            if not safe_apps:
                print("没有找到可卸载的应用")
                return
            
            for i, (name, app) in enumerate(safe_apps, 1):
                print(f"{i:<5} {name:<35} ✅可卸载")
            
            print("\n请输入要卸载的应用序号(用逗号分隔，如: 1,3,5): ")
            selection = input("> ").strip()
            
            selected_indices = []
            try:
                for s in selection.split(','):
                    idx = int(s.strip()) - 1
                    if 0 <= idx < len(safe_apps):
                        selected_indices.append(idx)
            except ValueError:
                print("输入无效")
                return
            
            if not selected_indices:
                print("未选择任何应用")
                return
            
            print("\n即将卸载以下应用:")
            print("-" * 50)
            for idx in selected_indices:
                print(f"  - {safe_apps[idx][0]}")
            
            confirm = input(f"\n确定要卸载这 {len(selected_indices)} 个应用吗? (y/n): ").strip().lower()
            if confirm != 'y':
                print("已取消")
                return
            
            print("\n正在卸载...")
            success_count = 0
            fail_count = 0
            
            for idx in selected_indices:
                display_name, app = safe_apps[idx]
                print(f"  正在卸载: {display_name}...", end="")
                if remove_app(app['PackageFullName']):
                    print(" ✓")
                    success_count += 1
                else:
                    print(" ✗")
                    fail_count += 1
            
            print(f"\n卸载完成: 成功 {success_count} 个, 失败 {fail_count} 个")
        
        elif choice == '5':
            return
        
        else:
            print("无效选择")
    
    except KeyboardInterrupt:
        print("\n已取消操作")
    except ValueError:
        print("输入无效")

def show_gpu_config_menu(config):
    while True:
        print("\n" + "=" * 70)
        print("                GPU 配置管理")
        print("=" * 70)
        
        current_settings = get_gpu_settings_from_registry()
        if current_settings:
            print("\n[当前GPU配置]")
            print("-" * 70)
            for exe_name, setting in current_settings.items():
                print(f"  {exe_name:<25} -> {setting.get('gpu_preference', '自定义')}")
        
        print("\n[自定义配置]")
        print("-" * 70)
        if 'gpu_settings' in config and config['gpu_settings']:
            for exe_name, setting in config['gpu_settings'].items():
                gpu_name = GPU_PREFERENCES.get(setting, setting)
                print(f"  {exe_name:<25} -> {gpu_name}")
        else:
            print("  暂无自定义配置")
        
        print("\n[操作菜单]")
        print("-" * 70)
        print("1. 添加单个GPU配置")
        print("2. 删除GPU配置")
        print("3. 查看优先级规则")
        print("4. 添加优先级规则")
        print("5. 批量配置GPU (扫描硬盘)")
        print("6. 返回上级菜单")
        
        try:
            choice = input("\n请输入选择 (1-6): ")
            if choice == '1':
                exe_name = input("请输入进程名(如 game.exe): ").strip()
                print("\nGPU选项:")
                print("  a - 让 Windows 决定")
                print("  i - 节能 (集成显卡)")
                print("  d - 高性能 (独立显卡)")
                gpu_choice = input("请选择GPU (a/i/d): ").strip().lower()
                
                if gpu_choice in ['a', 'i', 'd']:
                    gpu_map = {'a': 'auto', 'i': 'integrated', 'd': 'discrete'}
                    config['gpu_settings'][exe_name] = gpu_map[gpu_choice]
                    
                    full_path = None
                    for proc in psutil.process_iter(['pid', 'name', 'exe']):
                        try:
                            if proc.name().lower() == exe_name.lower():
                                full_path = proc.exe()
                                break
                        except:
                            continue
                    
                    if full_path and set_gpu_preference(full_path, gpu_map[gpu_choice]):
                        print(f"已成功设置 {exe_name} 的GPU偏好")
                    save_config(config)
                else:
                    print("无效选择")
            
            elif choice == '2':
                exe_name = input("请输入要删除的进程名: ").strip()
                if exe_name in config['gpu_settings']:
                    del config['gpu_settings'][exe_name]
                    save_config(config)
                    print(f"已删除 {exe_name} 的配置")
                else:
                    print("未找到该配置")
            
            elif choice == '3':
                print("\n[优先级规则]")
                print("-" * 70)
                if 'priority_rules' in config and config['priority_rules']:
                    for i, (name, rule) in enumerate(config['priority_rules'].items(), 1):
                        print(f"{i}. {name}:")
                        print(f"   进程名: {rule.get('process_name', '')}")
                        print(f"   评分调整: {rule.get('score_adjustment', 0)}")
                else:
                    print("  暂无优先级规则")
            
            elif choice == '4':
                rule_name = input("请输入规则名称: ").strip()
                process_name = input("请输入进程名(支持包含匹配): ").strip()
                adjustment = int(input("请输入评分调整值(正数提高优先级，负数降低): ").strip())
                
                config['priority_rules'][rule_name] = {
                    'process_name': process_name,
                    'score_adjustment': adjustment
                }
                save_config(config)
                print(f"已添加规则: {rule_name}")
            
            elif choice == '5':
                scan_and_configure(config)
            
            elif choice == '6':
                return
            
            else:
                print("无效选择")
        
        except KeyboardInterrupt:
            print("\n已取消操作")
            return
        except ValueError:
            print("输入无效")


def show_system_cleanup_menu(config):
    cleanup_windows_apps()


def show_system_optimization_menu(config):
    suggest_pagefile_settings()


def show_config_import_export_menu():
    while True:
        print("\n" + "=" * 70)
        print("                配置导入/导出")
        print("=" * 70)
        print("\n[功能菜单]")
        print("-" * 70)
        print("1. 导出配置包")
        print("2. 导入配置包")
        print("3. 查看当前配置状态")
        print("4. 热重载配置")
        print("5. 返回上级菜单")
        
        try:
            choice = input("\n请输入选择 (1-5): ")
            if choice == '1':
                if CONFIG_MANAGER:
                    path = CONFIG_MANAGER.export_config()
                    if path:
                        print(f"\n✅ 配置已导出到: {path}")
                    else:
                        print("\n❌ 导出失败")
                else:
                    print("\n❌ 配置管理器不可用")
            elif choice == '2':
                if CONFIG_MANAGER:
                    import_path = input("请输入配置包路径: ").strip()
                    if CONFIG_MANAGER.import_config(import_path):
                        print("\n✅ 配置导入成功")
                    else:
                        print("\n❌ 导入失败")
                else:
                    print("\n❌ 配置管理器不可用")
            elif choice == '3':
                if CONFIG_MANAGER:
                    config = CONFIG_MANAGER.get_app_categories()
                    print(f"\n配置版本: {config.get('version', '未知')}")
                    print(f"更新时间: {config.get('last_updated', '未知')}")
                    print(f"分类数量: {len(config.get('categories', {}))}")
                else:
                    print("\n❌ 配置管理器不可用")
            elif choice == '4':
                if CONFIG_MANAGER:
                    CONFIG_MANAGER.reload_all()
                    print("\n✅ 配置已重载")
                else:
                    print("\n❌ 配置管理器不可用")
            elif choice == '5':
                return
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return

def show_monitoring_menu():
    while True:
        print("\n" + "=" * 70)
        print("                监控与报告")
        print("=" * 70)
        print("\n[功能菜单]")
        print("-" * 70)
        print("1. 生成优化报告")
        print("2. 导出报告(JSON)")
        print("3. 检测异常进程")
        print("4. Windows性能计数器")
        print("5. 返回上级菜单")
        
        try:
            choice = input("\n请输入选择 (1-5): ")
            if choice == '1':
                if HISTORY_MANAGER:
                    print(HISTORY_MANAGER.get_report_summary_text())
                else:
                    print("\n❌ 历史管理器不可用")
            elif choice == '2':
                if HISTORY_MANAGER:
                    path = HISTORY_MANAGER.export_report()
                    if path:
                        print(f"\n✅ 报告已导出到: {path}")
                    else:
                        print("\n❌ 导出失败")
                else:
                    print("\n❌ 历史管理器不可用")
            elif choice == '3':
                if HISTORY_MANAGER:
                    anomalies = HISTORY_MANAGER.detect_anomalies()
                    if anomalies:
                        print("\n[异常进程检测结果]")
                        print("-" * 70)
                        for anomaly in anomalies:
                            severity = "🔴 高" if anomaly['severity'] == 'high' else "🟡 中"
                            print(f"\n{severity} {anomaly['process_name']}")
                            print(f"  CPU: {anomaly['current_cpu']:.1f}% | 内存: {anomaly['current_memory']:.1f}%")
                            print(f"  原因: {', '.join(anomaly['reasons'])}")
                            notification_manager.anomaly_detected(
                                anomaly['process_name'],
                                ', '.join(anomaly['reasons'])
                            )
                    else:
                        print("\n✅ 未检测到异常进程")
                else:
                    print("\n❌ 历史管理器不可用")
            elif choice == '4':
                if PERF_COUNTER:
                    print(PERF_COUNTER.get_formatted_metrics())
                else:
                    print("\n❌ 性能计数器不可用")
            elif choice == '5':
                return
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return

def show_process_history_menu():
    """进程历史查询菜单"""
    global HISTORY_MANAGER
    while True:
        print("\n" + "=" * 70)
        print("                进程历史追溯")
        print("=" * 70)

        print("\n[功能菜单]")
        print("-" * 70)
        print("1. 查询进程历史记录")
        print("2. 查看优先级变更")
        print("3. 查看进程统计")
        print("4. 返回上级菜单")

        try:
            choice = input("\n请输入选择 (1-4): ")
            if choice == '1':
                process_name = input("请输入进程名称: ").strip()
                if not process_name:
                    print("❌ 进程名称不能为空")
                    continue
                days = input("查询天数 (默认7天): ").strip()
                days = int(days) if days else 7

                history = HISTORY_MANAGER.get_process_history(process_name, days)
                print(f"\n[历史记录] 共 {len(history)} 条")
                print("-" * 70)
                for record in history[:20]:
                    print(f"  {record['timestamp']} | PID:{record['pid']} | CPU:{record['cpu_percent']:.1f}% | MEM:{record['memory_percent']:.1f}% | 优先级:{record['priority']}")
                if len(history) > 20:
                    print(f"  ... 还有 {len(history) - 20} 条记录")

            elif choice == '2':
                process_name = input("请输入进程名称: ").strip()
                if not process_name:
                    print("❌ 进程名称不能为空")
                    continue
                days = input("查询天数 (默认7天): ").strip()
                days = int(days) if days else 7

                changes = HISTORY_MANAGER.get_priority_changes(process_name, days)
                print(f"\n[优先级变更] 共 {len(changes)} 条")
                print("-" * 70)
                for change in changes:
                    print(f"  {change['timestamp']} | PID:{change['pid']} | {change['from']} -> {change['to']}")
                if not changes:
                    print("  暂无优先级变更记录")

            elif choice == '3':
                process_name = input("请输入进程名称: ").strip()
                if not process_name:
                    print("❌ 进程名称不能为空")
                    continue
                days = input("查询天数 (默认7天): ").strip()
                days = int(days) if days else 7

                stats = HISTORY_MANAGER.get_process_avg_stats(process_name, days)
                count = HISTORY_MANAGER.get_process_appearance_count(process_name, days)
                print(f"\n[进程统计] {process_name}")
                print("-" * 70)
                print(f"  出现次数: {count}")
                print(f"  平均CPU: {stats['avg_cpu']:.2f}%")
                print(f"  平均内存: {stats['avg_memory']:.2f}%")
                print(f"  平均评分: {stats['avg_score']:.2f}")

            elif choice == '4':
                return
            else:
                print("无效选择")
        except ValueError:
            print("❌ 请输入有效的数字")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return

def show_blacklist_menu():
    """游戏黑名单管理菜单"""
    global priority_restore_manager
    while True:
        print("\n" + "=" * 70)
        print("                游戏黑名单管理")
        print("=" * 70)
        
        blacklist = priority_restore_manager.get_blacklist()
        print(f"\n[当前黑名单] (共 {len(blacklist)} 个进程)")
        print("-" * 70)
        if blacklist:
            for i, proc in enumerate(blacklist, 1):
                print(f"  {i}. {proc}")
        else:
            print("  (空)")
        
        print("\n[操作选项]")
        print("-" * 70)
        print("1. 添加进程到黑名单")
        print("2. 从黑名单移除进程")
        print("3. 清空黑名单")
        print("4. 返回上级菜单")
        
        try:
            choice = input("\n请输入选择 (1-4): ")
            if choice == '1':
                proc_name = input("请输入要添加的进程名称: ").strip()
                if proc_name:
                    priority_restore_manager.add_to_blacklist(proc_name)
                    print(f"✅ 已添加 '{proc_name}' 到黑名单")
                else:
                    print("❌ 进程名称不能为空")
            elif choice == '2':
                proc_name = input("请输入要移除的进程名称: ").strip()
                if proc_name:
                    priority_restore_manager.remove_from_blacklist(proc_name)
                    print(f"✅ 已从黑名单移除 '{proc_name}'")
                else:
                    print("❌ 进程名称不能为空")
            elif choice == '3':
                confirm = input("确定要清空黑名单吗? (y/n): ").strip().lower()
                if confirm == 'y':
                    for proc in priority_restore_manager.get_blacklist():
                        priority_restore_manager.remove_from_blacklist(proc)
                    print("✅ 黑名单已清空")
            elif choice == '4':
                return
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return

def show_preference_learner_menu():
    """用户偏好学习设置菜单"""
    global preference_learner
    while True:
        print("\n" + "=" * 70)
        print("                用户偏好设置")
        print("=" * 70)
        
        # 显示当前学习功能状态
        print(f"\n[学习功能状态]")
        print("-" * 70)
        status = "已启用" if preference_learner.learning_enabled else "已禁用"
        print(f"  学习功能: {status}")
        
        # 显示已学习的进程数量
        adjusted_processes = preference_learner.get_all_adjusted_processes()
        print(f"  已学习进程数: {len(adjusted_processes)}")
        
        # 显示置信度分布
        high_conf = sum(1 for p in adjusted_processes if preference_learner.get_confidence(p) >= 0.8)
        med_conf = sum(1 for p in adjusted_processes if 0.3 <= preference_learner.get_confidence(p) < 0.8)
        low_conf = sum(1 for p in adjusted_processes if preference_learner.get_confidence(p) < 0.3)
        print(f"  高置信度(>=80%): {high_conf} 个")
        print(f"  中置信度(30-80%): {med_conf} 个")
        print(f"  低置信度(<30%): {low_conf} 个")
        
        print("\n[操作菜单]")
        print("-" * 70)
        print("1. 启用/禁用学习功能")
        print("2. 查看已学习的进程")
        print("3. 清除单个进程历史")
        print("4. 清除所有学习历史")
        print("5. 返回上级菜单")
        
        try:
            choice = input("\n请输入选择 (1-5): ")
            if choice == '1':
                if preference_learner.learning_enabled:
                    preference_learner.set_learning_enabled(False)
                    print("✅ 学习功能已禁用")
                else:
                    preference_learner.set_learning_enabled(True)
                    print("✅ 学习功能已启用")
            elif choice == '2':
                print("\n[已学习的进程]")
                print("-" * 70)
                if not adjusted_processes:
                    print("  暂无学习记录")
                else:
                    print(f"{'进程名':<25} {'调整次数':<10} {'置信度':<10} {'偏好优先级'}")
                    print("-" * 70)
                    for proc in sorted(adjusted_processes):
                        count = preference_learner.get_adjustment_count(proc)
                        confidence = preference_learner.get_confidence(proc)
                        preferred = preference_learner.get_preferred_priority(proc) or '无'
                        conf_str = f"{confidence*100:.0f}%"
                        print(f"{proc:<25} {count:<10} {conf_str:<10} {preferred}")
            elif choice == '3':
                proc_name = input("请输入要清除的进程名称: ").strip()
                if proc_name:
                    if proc_name in adjusted_processes:
                        preference_learner.clear_process_history(proc_name)
                        print(f"✅ 已清除 '{proc_name}' 的学习历史")
                    else:
                        print(f"❌ 未找到 '{proc_name}' 的学习记录")
                else:
                    print("❌ 进程名称不能为空")
            elif choice == '4':
                confirm = input("确定要清除所有学习历史吗? (y/n): ").strip().lower()
                if confirm == 'y':
                    for proc in list(adjusted_processes):
                        preference_learner.clear_process_history(proc)
                    print("✅ 已清除所有学习历史")
            elif choice == '5':
                return
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return
        except ValueError:
            print("❌ 请输入有效的选项")

def restore_all_priorities():
    """一键恢复所有进程到原始优先级"""
    global priority_restore_manager
    print("\n" + "=" * 70)
    print("                一键恢复原始优先级")
    print("=" * 70)
    
    original_priorities = priority_restore_manager.original_priorities
    if not original_priorities:
        print("\n⚠️  没有记录任何原始优先级")
        print("   请先运行一次优化，系统会自动记录进程原始优先级")
        return
    
    restored_count = 0
    failed_count = 0
    skipped_count = 0
    
    print(f"\n正在恢复 {len(original_priorities)} 个进程的原始优先级...")
    print("-" * 70)
    
    for proc_name, original_priority in original_priorities.items():
        # 检查是否是受保护的系统进程
        proc_name_lower = proc_name.lower()
        if proc_name_lower in [p.lower() for p in RESTORE_PROTECTED_PROCESSES]:
            logger.debug(f"跳过受保护进程: {proc_name}")
            skipped_count += 1
            continue
        
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.name().lower() == proc_name_lower:
                    try:
                        proc.nice(original_priority)
                        logger.info(f"已恢复进程 {proc_name} (PID:{proc.pid}) 优先级为 {original_priority}")
                        restored_count += 1
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        failed_count += 1
                    break
        except Exception as e:
            logger.debug(f"恢复进程 {proc_name} 失败: {e}")
            failed_count += 1
    
    print(f"\n[恢复结果]")
    print("-" * 70)
    print(f"  ✅ 成功恢复: {restored_count} 个进程")
    print(f"  ❌ 恢复失败: {failed_count} 个进程")
    print(f"  ⏭️  跳过(受保护): {skipped_count} 个进程")
    
    if restored_count > 0:
        notification_manager.priority_restored(f"{restored_count} 个进程")

def show_notification_settings():
    """通知设置菜单"""
    global notification_manager
    while True:
        print("\n" + "=" * 70)
        print("                通知设置")
        print("=" * 70)
        
        status = "开启" if notification_manager.is_enabled() else "关闭"
        print(f"\n[当前状态] 通知功能: {status}")
        print("-" * 70)
        
        print("\n[操作菜单]")
        print("-" * 70)
        print("1. 开启通知")
        print("2. 关闭通知")
        print("3. 测试通知")
        print("4. 返回上级菜单")
        
        try:
            choice = input("\n请输入选择 (1-4): ")
            if choice == '1':
                notification_manager.set_enabled(True)
                print("\n✅ 通知功能已开启")
            elif choice == '2':
                notification_manager.set_enabled(False)
                print("\n✅ 通知功能已关闭")
            elif choice == '3':
                notification_manager.notify("智优进程管理器", "这是一条测试通知", "info")
                print("\n✅ 测试通知已发送")
            elif choice == '4':
                return
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return
        except ValueError:
            print("输入无效")

def train_rl_model():
    """训练强化学习模型"""
    global HISTORY_MANAGER
    try:
        from ml.rl_agent import RLPriorityAgent
        from ml.rl_trainer import RLTrainer
        
        print("\n" + "=" * 70)
        print("                训练强化学习模型")
        print("=" * 70)
        
        if not HISTORY_MANAGER:
            print("\n⚠️  历史管理器不可用")
            return
        
        agent = RLPriorityAgent()
        trainer = RLTrainer(agent)
        trainer.set_history_manager(HISTORY_MANAGER)
        
        episodes = 100
        try:
            episodes_input = input(f"\n请输入训练轮次 (默认 {episodes}): ")
            if episodes_input.strip():
                episodes = int(episodes_input)
        except ValueError:
            print("输入无效，使用默认值")
        
        print(f"\n开始训练 {episodes} 轮...")
        result = trainer.train_from_history(episodes)
        
        if result['status'] == 'success':
            print(f"\n✅ 训练完成！")
            print(f"   训练轮次: {result['episodes']}")
            info = trainer.get_model_info()
            print(f"   Q表大小: {info['q_table_size']}")
        else:
            print(f"\n❌ 训练失败: {result.get('message', '未知错误')}")
    except ImportError as e:
        print(f"\n❌ 无法导入RL模块: {e}")

def show_rl_model_status():
    """查看RL模型状态"""
    try:
        from ml.rl_agent import RLPriorityAgent
        from ml.rl_trainer import RLTrainer
        
        print("\n" + "=" * 70)
        print("                RL模型状态")
        print("=" * 70)
        
        trainer = RLTrainer()
        
        if trainer.load_model():
            info = trainer.get_model_info()
            print("\n[模型信息]")
            print("-" * 70)
            print(f"  状态: ✅ 已加载")
            print(f"  Q表大小: {info['q_table_size']}")
            print(f"  学习率: {info['learning_rate']}")
            print(f"  折扣因子: {info['discount_factor']}")
            print(f"  Epsilon: {info['epsilon']:.4f}")
        else:
            print("\n⚠️  模型尚未训练或加载")
            print("   请先选择「训练强化学习模型」选项")
    except ImportError as e:
        print(f"\n❌ 无法导入RL模块: {e}")

def show_advanced_menu(config):
    while True:
        print("\n" + "=" * 70)
        print("                高级功能管理")
        print("=" * 70)
        print("\n[功能菜单]")
        print("-" * 70)
        print("1. GPU 配置管理")
        print("2. Windows应用清理")
        print("3. 虚拟内存优化")
        print("4. 配置导入/导出")
        print("5. 监控与报告")
        print("6. 返回主菜单")
        print("7. 游戏黑名单管理")
        print("8. 一键恢复原始优先级")
        print("9. 查看进程历史")
        print("10. 用户偏好设置")
        print("11. 训练强化学习模型")
        print("12. 查看RL模型状态")
        print("13. 通知设置")
        print("14. 快捷键设置")
        print("15. NVIDIA 控制面板优化")

        try:
            choice = input("\n请输入选择 (1-15): ")
            if choice == '1':
                show_gpu_config_menu(config)
            elif choice == '2':
                show_system_cleanup_menu(config)
            elif choice == '3':
                show_system_optimization_menu(config)
            elif choice == '4':
                show_config_import_export_menu()
            elif choice == '5':
                show_monitoring_menu()
            elif choice == '6':
                return
            elif choice == '7':
                show_blacklist_menu()
            elif choice == '8':
                restore_all_priorities()
            elif choice == '9':
                show_process_history_menu()
            elif choice == '10':
                show_preference_learner_menu()
            elif choice == '11':
                train_rl_model()
            elif choice == '12':
                show_rl_model_status()
            elif choice == '13':
                show_notification_settings()
            elif choice == '14':
                show_shortcut_settings()
            elif choice == '15':
                show_nvidia_optimizer_menu()
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return


# ==================== 系统托盘功能 ====================

APP_DISPLAY_NAME = "智优进程管理器"
APP_VERSION = "v1.3.0"

def create_tray_icon():
    """创建精美的托盘图标"""
    try:
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color=(80, 150, 220))
        draw = ImageDraw.Draw(image)
        
        # 绘制一个现代风格的CPU图标
        
        # 外框 - 使用圆角矩形（兼容旧版PIL）
        draw.ellipse([8, 8, 56, 56], fill=(60, 120, 200))
        
        # 散热片 - 三个矩形
        draw.rectangle([12, 12, 18, 52], fill=(100, 160, 230))
        draw.rectangle([28, 16, 36, 48], fill=(100, 160, 230))
        draw.rectangle([46, 12, 52, 52], fill=(100, 160, 230))
        
        # 中心装饰
        draw.ellipse([26, 26, 38, 38], fill=(160, 200, 250))
        
        # 添加光泽效果
        draw.ellipse([10, 10, 20, 20], fill=(255, 255, 255, 50))
        
        logger.debug("精美托盘图标创建成功")
        return image
    except Exception as e:
        logger.error(f"创建图标失败: {e}")
        # 返回一个简单的备用图标
        image = Image.new('RGB', (64, 64), color=(80, 150, 220))
        draw = ImageDraw.Draw(image)
        draw.ellipse([10, 10, 54, 54], fill=(120, 180, 240))
        return image

def run_cleanup():
    """执行缓存清理 - 在单独线程中执行"""
    def _do_cleanup():
        try:
            import shutil
            import tempfile
            
            cleaned_total = 0
            cleaned_count = 0
            error_count = 0
            
            # 清理目标列表
            temp_locations = []
            
            # Windows 用户临时文件夹
            user_temp = os.path.join(os.environ.get('TEMP', ''), '')
            if user_temp and os.path.exists(user_temp):
                temp_locations.append(('用户临时文件夹', user_temp))
            
            # Windows 系统临时文件夹
            system_temp = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Temp')
            if os.path.exists(system_temp):
                temp_locations.append(('系统临时文件夹', system_temp))
            
            # IE/Edge 临时文件
            ie_cache = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'INetCache')
            if os.path.exists(ie_cache):
                temp_locations.append(('IE/Edge 缓存', ie_cache))
            
            # Chrome 临时文件 (如果存在)
            chrome_cache = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default', 'Cache')
            if os.path.exists(chrome_cache):
                temp_locations.append(('Chrome 缓存', chrome_cache))
            
            # pip 缓存
            pip_cache = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'pip', 'cache')
            if os.path.exists(pip_cache):
                temp_locations.append(('pip 缓存', pip_cache))
            
            result_text = "缓存清理完成\n\n"
            safe_print("正在清理系统缓存...")
            
            for name, path in temp_locations:
                try:
                    if not os.path.exists(path):
                        continue
                        
                    size_before = 0
                    count_before = 0
                    for root, dirs, files in os.walk(path):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                size_before += os.path.getsize(fp)
                                count_before += 1
                            except:
                                pass
                    
                    if count_before == 0:
                        continue
                    
                    # 清理
                    deleted_size = 0
                    deleted_count = 0
                    for root, dirs, files in os.walk(path):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                os.remove(fp)
                                try:
                                    deleted_size += os.path.getsize(fp)
                                except:
                                    pass
                                deleted_count += 1
                            except:
                                pass
                    
                    cleaned_total += deleted_size
                    cleaned_count += deleted_count
                    
                    if deleted_count > 0:
                        size_str = format_size(deleted_size)
                        logger.info(f"清理 {name}: {deleted_count} 个文件, {size_str}")
                        
                except Exception as e:
                    error_count += 1
                    logger.warning(f"清理 {name} 失败: {e}")
            
            # 清理日志文件（保留最近的）
            try:
                log_dir = os.path.dirname(LOG_FILE) if LOG_FILE else 'logs'
                if os.path.exists(log_dir):
                    log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
                    log_files.sort(key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True)
                    for old_log in log_files[5:]:  # 保留最近5个
                        try:
                            fp = os.path.join(log_dir, old_log)
                            size = os.path.getsize(fp)
                            os.remove(fp)
                            cleaned_total += size
                            cleaned_count += 1
                            logger.debug(f"删除旧日志: {old_log}")
                        except:
                            pass
            except:
                pass
            
            result_text += f"清理文件数: {cleaned_count} 个\n"
            result_text += f"释放空间: {format_size(cleaned_total)}\n"
            if error_count > 0:
                result_text += f"错误: {error_count} 处"
            
            safe_print(f"缓存清理完成: {cleaned_count} 个文件, {format_size(cleaned_total)}")
            show_quick_message("清理完成", result_text, "info")
            
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            show_quick_message("清理失败", f"清理缓存失败: {e}", "error")
    
    thread = threading.Thread(target=_do_cleanup, daemon=True)
    thread.start()

def format_size(size_bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def on_tray_click(icon, item):
    """托盘菜单点击处理"""
    item_str = str(item)
    logger.info(f"托盘菜单点击: {item_str}")

    try:
        if item_str == "查看状态":
            show_status()
        elif item_str == "查看游戏":
            show_games()
        elif item_str == "立即优化":
            run_optimization()
        elif item_str == "NVIDIA一键优化":
            run_nvidia_optimization(preset_name="low_latency")
        elif item_str == "清理缓存":
            run_cleanup()
        elif item_str == "打开主窗口":
            main_window = get_main_window()
            main_window.set_callback('view_status', show_status)
            main_window.set_callback('view_games', show_games)
            main_window.set_callback('optimize', run_optimization)
            main_window.set_callback('nvidia_optimize', run_nvidia_optimization)
            main_window.set_callback('view_services', show_services)
            main_window.set_callback('cleanup', run_cleanup)
            main_window.show()
        elif item_str == "查看服务":
            show_services()
        elif item_str == "退出":
            logger.info("用户点击退出")
            icon.stop()
            sys.exit(0)
    except Exception as e:
        logger.error(f"托盘菜单处理失败: {e}")
        safe_print(f"托盘菜单处理失败: {e}")

# ==================== 全局快捷键功能 ====================

def _init_shortcuts():
    """初始化全局快捷键"""
    global shortcut_manager
    
    def do_optimize():
        print("\n[快捷键] 触发立即优化...")
        run_optimization()
    
    def do_show_status():
        print("\n[快捷键] 显示系统状态...")
        show_status()
    
    def do_show_games():
        print("\n[快捷键] 显示游戏进程...")
        show_games()
    
    def do_restore():
        print("\n[快捷键] 触发一键恢复...")
        restore_all_priorities()
    
    def do_nvidia():
        print("\n[快捷键] 触发 NVIDIA 一键优化...")
        run_nvidia_optimization(preset_name="low_latency")

    def do_quit():
        print("\n[快捷键] 退出程序...")
        shortcut_manager.unregister_all()
        sys.exit(0)

    # 注册快捷键
    shortcut_manager.register('ctrl+shift+o', do_optimize, "立即优化")
    shortcut_manager.register('ctrl+shift+s', do_show_status, "显示状态")
    shortcut_manager.register('ctrl+shift+g', do_show_games, "显示游戏")
    shortcut_manager.register('ctrl+shift+n', do_nvidia, "NVIDIA一键优化")
    shortcut_manager.register('ctrl+shift+r', do_restore, "一键恢复")
    shortcut_manager.register('ctrl+shift+q', do_quit, "退出程序")
    print("✅ 全局快捷键注册完成")

def show_shortcut_settings():
    """显示快捷键设置"""
    shortcuts = shortcut_manager.get_registered_shortcuts()
    
    print("\n" + "=" * 70)
    print("                快捷键设置")
    print("=" * 70)
    
    if not shortcuts:
        print("\n⚠️  当前没有注册任何快捷键")
        print("\n快捷键功能需要安装 keyboard 库: pip install keyboard")
        print("\n按回车键返回...")
        input()
        return
    
    print("\n已注册的快捷键:")
    print("-" * 70)
    for i, shortcut in enumerate(shortcuts, 1):
        print(f"  {i}. {shortcut['hotkey']:20} - {shortcut['description']}")
    
    print("\n" + "-" * 70)
    print(f"快捷键功能: {'已启用' if shortcut_manager.is_enabled() else '已禁用'}")
    
    print("\n操作选项:")
    print("  1. 启用快捷键")
    print("  2. 禁用快捷键")
    print("  0. 返回")
    
    try:
        choice = input("\n请输入选择: ")
        if choice == '1':
            shortcut_manager.set_enabled(True)
            print("✅ 快捷键功能已启用")
        elif choice == '2':
            shortcut_manager.set_enabled(False)
            print("✅ 快捷键功能已禁用")
    except KeyboardInterrupt:
        pass

def show_games():
    """显示当前运行的游戏 - 在单独线程中执行"""
    def _show_games():
        try:
            if hasattr(APP, 'detect_games'):
                has_games, game_list = APP.detect_games()
                
                
                game_text = "╔══════════════════════════════════════════════════════════╗\n"
                game_text += "║           智优进程管理器 v1.1.0 - 游戏检测              ║\n"
                game_text += "╚══════════════════════════════════════════════════════════╝\n\n"
                
                if has_games:
                    game_text += "┌──────────────────────────────────────────────────────────┐\n"
                    game_text += f"│  🎮 检测到 {len(game_list)} 个游戏进程                     │\n"
                    game_text += "├──────────────────────────────────────────────────────────┤\n"
                    
                    for i, game in enumerate(game_list[:10], 1):
                        game_text += f"│  {i:2d}. {game:45} │\n"
                    if len(game_list) > 10:
                        game_text += f"│     ... 等共 {len(game_list)} 个游戏                        │\n"
                    
                    game_text += "└──────────────────────────────────────────────────────────┘\n"
                    
                    game_text += "\n┌──────────────────────────────────────────────────────────┐\n"
                    game_text += "│                     优化状态                            │\n"
                    game_text += "├──────────────────────────────────────────────────────────┤\n"
                    game_text += "│  ✅ 智能优化:      已启用                              │\n"
                    game_text += f"│  ⏱ 优化冷却:      {APP.game_cooldown}秒                  │\n"
                    game_text += f"│  🔄 已优化次数:    {APP.game_optimization_count}次        │\n"
                    
                    remaining = APP.game_cooldown - (time.time() - APP.last_game_optimization)
                    if remaining > 0:
                        game_text += f"│  ⏳ 下次优化:      {int(remaining)}秒后                  │\n"
                    else:
                        game_text += "│  🟢 下次优化:      随时可以                            │\n"
                    game_text += "└──────────────────────────────────────────────────────────┘\n"
                    
                else:
                    game_text += "┌──────────────────────────────────────────────────────────┐\n"
                    game_text += "│  ⏳ 当前没有检测到游戏进程                               │\n"
                    game_text += "├──────────────────────────────────────────────────────────┤\n"
                    game_text += "│  游戏检测功能持续监控中...                              │\n"
                    game_text += "│  启动游戏后将自动优化相关进程                          │\n"
                    game_text += "│  支持: Steam、Epic、原神、明日方舟等100+游戏            │\n"
                    game_text += "└──────────────────────────────────────────────────────────┘\n"
                
                # 打印到控制台
                print("\n" + game_text)
                
                # 显示消息框（简化版）
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    
                    msg_text = f"智优进程管理器 - 游戏检测\n\n"
                    if has_games:
                        msg_text += f"检测到 {len(game_list)} 个游戏进程:\n\n"
                        for i, game in enumerate(game_list[:7], 1):
                            msg_text += f"{i}. {game}\n"
                        if len(game_list) > 7:
                            msg_text += f"...\n\n共 {len(game_list)} 个游戏"
                        msg_text += f"\n\n优化状态:\n"
                        msg_text += f"  智能优化: 已启用\n"
                        msg_text += f"  优化冷却: {APP.game_cooldown}秒\n"
                        msg_text += f"  已优化次数: {APP.game_optimization_count}\n"
                        remaining = APP.game_cooldown - (time.time() - APP.last_game_optimization)
                        msg_text += f"  下次优化: {'随时可以' if remaining <= 0 else f'{int(remaining)}秒后'}"
                    else:
                        msg_text += "当前没有检测到游戏进程\n\n"
                        msg_text += "游戏检测功能持续监控中...\n"
                        msg_text += "启动游戏后将自动优化相关进程"
                    
                    messagebox.showinfo("游戏检测", msg_text)
                    root.destroy()
                except ImportError:
                    pass
            else:
                print("游戏检测功能不可用")
                
        except Exception as e:
            logger.error(f"显示游戏信息失败: {e}")
    
    thread = threading.Thread(target=_show_games, daemon=True)
    thread.start()

def show_status():
    """显示当前系统状态 - 在单独线程中执行"""
    def _show_status():
        try:
            system_metrics = get_system_metrics()

            # 构建状态文本
            status_text = "智优进程管理器 v1.2.0 - 系统状态\n\n"
            status_text += f"CPU: {system_metrics['cpu_percent']}% ({system_metrics['cpu_count']}核)\n"
            status_text += f"内存: {system_metrics['memory_percent']}%\n"
            status_text += f"可用内存: {system_metrics['memory_available']:.1f} GB\n"

            if system_metrics['gpus']:
                status_text += "\nGPU 信息:\n"
                for i, gpu in enumerate(system_metrics['gpus']):
                    status_text += f"  GPU {i+1}: {gpu['name']} - {gpu['utilization']}%\n"

            # 游戏检测状态
            has_games = False
            if hasattr(APP, 'detect_games'):
                has_games, game_list = APP.detect_games()
                if has_games:
                    games_str = ", ".join(game_list[:3])
                    if len(game_list) > 3:
                        games_str += f" 等{len(game_list)}个"
                    status_text += f"\n检测到游戏: {games_str}\n"
                    status_text += f"已优化次数: {APP.game_optimization_count}次\n"
                else:
                    status_text += "\n游戏检测: 等待中\n"

            # 安全打印到控制台
            safe_print("\n" + status_text)

            # 使用 GUI 消息框显示
            show_quick_message("系统状态", status_text, "info")

        except Exception as e:
            logger.error(f"显示状态失败: {e}")
            show_quick_message("错误", f"显示状态失败: {e}", "error")

    thread = threading.Thread(target=_show_status, daemon=True)
    thread.start()

def run_optimization():
    """执行进程优化 - 在单独线程中执行"""
    def _run_optimization():
        safe_print("正在执行进程优先级优化...")

        try:
            results = analyze_all_processes()
            success_count = sum(1 for r in results if r.get('status') == 'success')

            result_text = "进程优先级优化完成\n\n"
            result_text += f"成功优化: {success_count} 个进程\n"
            result_text += f"总计分析: {len(results)} 个进程\n"
            if len(results) > 0:
                result_text += f"优化成功率: {(success_count/len(results)*100):.1f}%\n"
            result_text += "\n系统资源已智能分配，游戏体验更流畅！"

            safe_print(result_text)
            show_quick_message("优化完成", result_text, "info")

        except Exception as e:
            logger.error(f"优化失败: {e}")
            show_quick_message("优化失败", f"优化失败: {e}", "error")

    thread = threading.Thread(target=_run_optimization, daemon=True)
    thread.start()

def show_services():
    """显示服务状态 - 在单独线程中执行"""
    def _show_services():
        safe_print("正在查询Windows服务状态...")

        try:
            services = analyze_all_services()
            running_count = sum(1 for s in services if s['is_running'])
            stopped_count = len(services) - running_count

            result_text = "Windows 服务状态\n\n"
            result_text += f"总计服务: {len(services)} 个\n"
            result_text += f"运行中: {running_count} 个\n"
            result_text += f"已停止: {stopped_count} 个"

            safe_print(result_text)
            show_quick_message("服务状态", result_text, "info")

        except Exception as e:
            logger.error(f"显示服务失败: {e}")
            show_quick_message("查询失败", f"查询服务失败: {e}", "error")

    thread = threading.Thread(target=_show_services, daemon=True)
    thread.start()


def run_nvidia_optimization(preset_name: str = "low_latency", silent: bool = False):
    """执行 NVIDIA 一键低延迟优化 - 在单独线程中执行"""
    def _run_optimization():
        try:
            if not nvidia_optimizer.is_available():
                msg = "未检测到 NVIDIA 显卡或驱动，无法应用 NVIDIA 优化。"
                safe_print(f"警告: {msg}")
                if not silent:
                    show_quick_message("NVIDIA 优化", msg, "warning")
                return

            safe_print("正在执行 NVIDIA 低延迟优化...")

            ok, details = nvidia_optimizer.apply(preset_name=preset_name, backup=True)

            preset_display = details.get("display_name", preset_name)
            success_count = details.get("success", 0)
            failed_count = details.get("failed", 0)
            total_count = details.get("total", 0)

            result_text = "NVIDIA 低延迟优化完成\n\n"
            result_text += f"应用预设: {preset_display}\n"
            result_text += f"成功: {success_count}/{total_count} 项设置\n"
            result_text += f"失败: {failed_count}/{total_count} 项设置\n\n"

            for item in details.get("items", []):
                status = "成功" if item.get("success") else "失败"
                result_text += f"{item['name']}: {item.get('label', item['value'])} [{status}]\n"

            result_text += "\n提示：部分设置可能需要重新启动游戏或 NVIDIA 控制面板才能生效。"
            safe_print(result_text)

            if not silent:
                msg_type = "warning" if failed_count > 0 else "info"
                msg = f"NVIDIA 优化完成\n\n预设: {preset_display}\n成功: {success_count}/{total_count}\n失败: {failed_count}/{total_count}\n\n"
                if failed_count > 0:
                    msg += "部分注册表项写入失败，建议手动在 NVIDIA 控制面板确认。"
                else:
                    msg += "设置已应用，建议重启游戏以生效。"
                show_quick_message("NVIDIA 优化", msg, msg_type)

        except Exception as e:
            logger.error(f"NVIDIA 优化失败: {e}")
            safe_print(f"NVIDIA 优化失败: {e}")
            if not silent:
                show_quick_message("NVIDIA 优化失败", f"优化失败: {e}", "error")

    thread = threading.Thread(target=_run_optimization, daemon=True)
    thread.start()


def show_nvidia_status():
    """显示 NVIDIA 优化状态 - 在单独线程中执行"""
    def _show_status():
        try:
            status = nvidia_optimizer.get_status()

            text = "NVIDIA 显卡与 3D 设置状态\n\n"
            available = status.get("available", False)
            text += f"检测状态: {'可用' if available else '不可用'}\n"
            text += f"GPU 存在: {'是' if status.get('gpu_present') else '否'}\n"
            text += f"驱动安装: {'是' if status.get('driver_installed') else '否'}\n\n"

            text += "当前全局 3D 设置:\n"
            for name, info in status.get("current_settings", {}).items():
                display_name = name.replace('_', ' ').title()
                text += f"  {display_name}: {info.get('label', '未知')}\n"

            safe_print("\n" + text)
            show_quick_message("NVIDIA 状态", text, "info")

        except Exception as e:
            logger.error(f"显示 NVIDIA 状态失败: {e}")
            show_quick_message("错误", f"显示 NVIDIA 状态失败: {e}", "error")

    thread = threading.Thread(target=_show_status, daemon=True)
    thread.start()


def show_nvidia_optimizer_menu():
    """NVIDIA 优化设置菜单"""
    while True:
        safe_print("\n" + "=" * 70)
        safe_print("                NVIDIA 控制面板优化")
        safe_print("=" * 70)
        safe_print("\n[功能菜单]")
        safe_print("-" * 70)
        safe_print("1. 竞技低延迟一键优化 (CS2/Valorant/LOL/APEX)")
        safe_print("2. 3A 画质平衡优化")
        safe_print("3. 从备份恢复设置")
        safe_print("4. 查看当前 NVIDIA 状态")
        safe_print("5. 打开 NVIDIA 控制面板")
        safe_print("0. 返回上级菜单")

        try:
            choice = input("\n请输入选择 (0-5): ")
            if choice == '1':
                run_nvidia_optimization(preset_name="low_latency")
            elif choice == '2':
                run_nvidia_optimization(preset_name="balanced")
            elif choice == '3':
                ok, details = nvidia_optimizer.restore()
                if ok:
                    safe_print("已从备份恢复 NVIDIA 设置")
                    show_quick_message("NVIDIA 恢复", "已从备份恢复 NVIDIA 设置", "info")
                else:
                    safe_print(f"恢复失败: {details.get('error', '未知错误')}")
                    show_quick_message("NVIDIA 恢复失败", details.get('error', '未知错误'), "error")
            elif choice == '4':
                show_nvidia_status()
            elif choice == '5':
                if launch_nvidia_control_panel():
                    safe_print("已打开 NVIDIA 控制面板")
                else:
                    safe_print("无法打开 NVIDIA 控制面板")
                    show_quick_message("错误", "无法打开 NVIDIA 控制面板", "error")
            elif choice == '0':
                return
            else:
                print("无效选择")
        except KeyboardInterrupt:
            print("\n已取消操作")
            return


def run_tray_service():
    """启动系统托盘服务"""
    try:
        # 设置日志 - 用户模式
        setup_logging(verbose=False)

        safe_print("智优进程管理器 v1.2.0 - 启动中...")

        # 初始化应用
        APP.initialize()
        safe_print("应用初始化完成")

        # 创建托盘菜单
        menu = pystray.Menu(
            pystray.MenuItem("查看状态", on_tray_click),
            pystray.MenuItem("查看游戏", on_tray_click),
            pystray.MenuItem("立即优化", on_tray_click),
            pystray.MenuItem("NVIDIA一键优化", on_tray_click),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("清理缓存", on_tray_click),
            pystray.MenuItem("打开主窗口", on_tray_click),
            pystray.MenuItem("查看服务", on_tray_click),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_tray_click)
        )
        safe_print("托盘菜单创建完成")

        # 创建图标
        tray_icon = create_tray_icon()
        safe_print("托盘图标创建完成")

        # 创建托盘图标
        icon = pystray.Icon(
            name=APP_DISPLAY_NAME,
            icon=tray_icon,
            title=f"{APP_DISPLAY_NAME} {APP_VERSION}\n智能游戏优化已启用"
        )
        icon.menu = menu

        # 启动定时任务
        APP.start_scheduler()
        safe_print("定时任务启动成功")

        # 初始化全局快捷键
        _init_shortcuts()

        safe_print("\n智优进程管理器 v1.2.0 已启动")
        safe_print("智能游戏检测已启用")
        safe_print("全局快捷键已启用")
        safe_print("\n右键点击托盘图标查看菜单")

        # 显示启动成功通知
        show_quick_message("智优进程管理器", "已启动并运行在后台\n右键托盘图标查看菜单", "info")

        # 运行托盘事件循环
        icon.run()

    except Exception as e:
        logger.error(f"启动失败: {e}")
        safe_print(f"启动失败: {e}")
        show_quick_message("启动失败", f"启动失败: {e}", "error")


def main():
    start_time = time.time()
    log_entries = []
    config = load_config()
    
    APP.initialize()
    
    global CONFIG_MANAGER, ML_MODEL, HISTORY_MANAGER, PERF_COUNTER, NETWORK_MONITOR
    CONFIG_MANAGER = APP.config_manager
    ML_MODEL = APP.ml_model
    HISTORY_MANAGER = APP.history_manager
    PERF_COUNTER = APP.perf_counter
    NETWORK_MONITOR = APP.network_monitor
    
    admin_mode = is_admin()
    
    # 性能模式处理（需要在其他参数之前处理）
    global PERFORMANCE_MODE
    for arg in sys.argv[1:]:
        if arg in ('--fast', '--balanced', '--thorough'):
            PERFORMANCE_MODE = arg[2:]  # 去掉 '--'
            print(f"[性能模式] {PERFORMANCE_MODE} 模式已启用")
            log_entries.append(f"性能模式: {PERFORMANCE_MODE}")
            break
    
    if len(sys.argv) == 1:
        run_tray_service()
        return

    if len(sys.argv) > 1:
        if sys.argv[1] == '--config':
            show_advanced_menu(config)
            return
        elif sys.argv[1] == '--report':
            if HISTORY_MANAGER:
                print(HISTORY_MANAGER.get_report_summary_text())
            else:
                print("历史管理器不可用")
            return
        elif sys.argv[1] == '--perf':
            if PERF_COUNTER:
                print(PERF_COUNTER.get_formatted_metrics())
            else:
                print("性能计数器不可用")
            return
        elif sys.argv[1] == '--ml-train':
            if ML_MODEL and HISTORY_MANAGER:
                data = ML_MODEL.prepare_training_data(HISTORY_MANAGER)
                result = ML_MODEL.train_model(data)
                print("ML模型训练结果:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("ML模型或历史管理器不可用")
            return
        elif sys.argv[1] == '--ml-info':
            if ML_MODEL:
                info = ML_MODEL.get_model_info()
                print("ML模型信息:")
                print(json.dumps(info, indent=2, ensure_ascii=False))
            else:
                print("ML模型不可用")
            return
        elif sys.argv[1] == '--api':
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
            start_api_server(port)
            return
        elif sys.argv[1] == '--nvidia-optimize':
            preset = sys.argv[2] if len(sys.argv) > 2 else "low_latency"
            if preset not in PRESETS:
                preset = "low_latency"
            ok, details = nvidia_optimizer.apply(preset_name=preset, backup=True)
            print(json.dumps(details, indent=2, ensure_ascii=False))
            return
        elif sys.argv[1] == '--nvidia-menu':
            show_nvidia_optimizer_menu()
            return
        elif sys.argv[1] == '--nvidia-status':
            status = nvidia_optimizer.get_status()
            print(json.dumps(status, indent=2, ensure_ascii=False))
            return
        elif sys.argv[1] == '--nvidia-restore':
            ok, details = nvidia_optimizer.restore()
            print(json.dumps(details, indent=2, ensure_ascii=False))
            return
        elif sys.argv[1] == '--console':
            pass

    print("=" * 90)
    print("          AI 智能进程优先级分配 v1.1.0")
    print("=" * 90)
    
    log_entries.append(f"版本: v1.1.0")
    log_entries.append(f"管理员模式: {admin_mode}")
    
    if admin_mode:
        print("[管理员模式] 已获得管理员权限")
    else:
        print("[普通模式] 部分系统进程需要管理员权限")
    
    # 显示当前性能模式
    print(f"[性能模式] 当前模式: {PERFORMANCE_MODE}")
    
    print(f"\n[提示] 使用 python {sys.argv[0]} --config 进入配置管理")
    print(f"[提示] 性能模式选项: --fast(快速) --balanced(平衡) --thorough(彻底)")
    print(f"[提示] NVIDIA优化: --nvidia-optimize [low_latency|balanced|default]")
    print(f"[提示] NVIDIA恢复: --nvidia-restore")
    
    keyword = None
    for arg in sys.argv[1:]:
        if not arg.startswith('--'):
            keyword = arg
            break
    
    if keyword:
        print(f"\n搜索关键词: {keyword}")
        log_entries.append(f"搜索关键词: {keyword}")
    
    system_metrics = get_system_metrics()
    
    print(f"\n[系统概览]")
    print(f"CPU: {system_metrics['cpu_percent']}% ({system_metrics['cpu_count']}核)")
    print(f"内存: {system_metrics['memory_percent']}% ({system_metrics['memory_available']:.1f}/{system_metrics['memory_total']:.1f} GB)")
    
    log_entries.append(f"CPU: {system_metrics['cpu_percent']}% ({system_metrics['cpu_count']}核)")
    log_entries.append(f"内存: {system_metrics['memory_percent']}%")
    
    if system_metrics['gpus']:
        print("\n[GPU信息]")
        brands_found = {}
        for i, gpu in enumerate(system_metrics['gpus']):
            gpu_type = "独立显卡" if gpu.get('type') == 'discrete' else "集成显卡"
            brand_name = gpu.get('brand_name', '未知')
            brand = gpu.get('brand', 'Unknown')
            color = gpu.get('color', '灰色')
            
            if brand not in brands_found:
                brands_found[brand] = {'count': 0, 'brand_name': brand_name}
            brands_found[brand]['count'] += 1
            
            print(f"  GPU {i+1}: {gpu['name']}")
            print(f"    ├─ 品牌: {brand_name} ({color})")
            print(f"    ├─ 类型: {gpu_type}")
            print(f"    ├─ 显存: {gpu['memory_used']}/{gpu['memory_total']} MB")
            if gpu['utilization'] > 0:
                print(f"    └─ 使用率: {gpu['utilization']}%")
            else:
                print(f"    └─ 使用率: 未检测")
            log_entries.append(f"GPU {i+1}: {gpu['name']} ({brand_name}, {gpu_type}, {gpu['memory_total']} MB)")
        
        if brands_found:
            print(f"\n  [品牌统计]")
            for brand, info in brands_found.items():
                print(f"    - {info['brand_name']}: {info['count']} 张")
        
        if len(system_metrics['gpus']) >= 2:
            gpu_load_diff = abs(system_metrics['gpus'][0]['utilization'] - system_metrics['gpus'][1]['utilization'])
            if gpu_load_diff > 30:
                print(f"\n  ⚠️  GPU负载差异较大 ({gpu_load_diff}%)，建议检查应用程序GPU配置")
            
            discrete_gpus = [g for g in system_metrics['gpus'] if g.get('type') == 'discrete']
            if len(discrete_gpus) >= 2:
                print(f"\n  💡 检测到 {len(discrete_gpus)} 张独立显卡，建议为不同应用配置不同GPU")
    
    print("\n[磁盘分区]")
    for part in system_metrics['disk_partitions']:
        print(f"  {part['device']}: {part['mountpoint']} - {part['percent']}% 可用")
        log_entries.append(f"磁盘 {part['device']}: {part['percent']}%")
    
    print("-" * 90)
    
    processes = search_processes(keyword)
    print(f"找到 {len(processes)} 个进程")
    log_entries.append(f"进程总数: {len(processes)}")
    
    print(f"使用 {THREAD_COUNT} 线程并行分析...", end="", flush=True)
    
    psutil.cpu_percent(interval=0.01)
    
    all_results = parallel_analyze(processes, system_metrics, admin_mode, config)
    
    elapsed_time = time.time() - start_time
    print(f"\r分析完成! ({elapsed_time:.2f}秒)")
    log_entries.append(f"分析耗时: {elapsed_time:.2f}秒")
    
    results = [r for r in all_results if r['status'] == 'success']
    access_denied_list = [r for r in all_results if r['status'] == 'access_denied']
    protected_list = [r for r in all_results if r['status'] == 'protected']
    need_admin_count = sum(1 for r in all_results if r['status'] == 'need_admin')
    system_skip_count = sum(1 for r in all_results if r['status'] == 'system_skip')
    
    print("\n[优先级调整结果]")
    print("-" * 90)
    print(f"{'PID':<8} {'名称':<20} {'类型':<8} {'CPU':<5} {'内存':<5} {'线程':<4} {'评分':<5} {'优先级变化'}")
    print("-" * 90)
    
    sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    for result in sorted_results[:20]:
        arrow = "->" if result['old_priority'] != result['new_priority'] else "=="
        threads = result.get('num_threads', 1)
        print(f"{result['pid']:<8} {result['name']:<20} {result['proc_type']:<8} "
              f"{result['cpu_percent']:<5.1f} {result['memory_percent']:<5.1f} "
              f"{threads:<4} {result['score']:<5.1f} {result['old_priority']:>8} {arrow} {result['new_priority']}")
        log_entries.append(f"进程: {result['name']} PID:{result['pid']} 评分:{result['score']} 优先级:{result['old_priority']}{arrow}{result['new_priority']}")
    
    if len(results) > 20:
        print(f"\n... 还有 {len(results) - 20} 个进程未显示")
    
    if protected_list:
        print("\n[系统保护进程]")
        print("-" * 90)
        print(f"{'PID':<8} {'名称':<20} {'当前优先级'}")
        print("-" * 90)
        for result in protected_list[:5]:
            print(f"{result['pid']:<8} {result['name']:<20} {result['current_priority']}")
        if len(protected_list) > 5:
            print(f"... 还有 {len(protected_list) - 5} 个保护进程")
    
    if access_denied_list and admin_mode:
        print("\n[访问被拒绝的进程]")
        print("-" * 90)
        print(f"{'PID':<8} {'名称':<20} {'原因'}")
        print("-" * 90)
        for result in access_denied_list[:5]:
            print(f"{result['pid']:<8} {result['name']:<20} {result['reason']}")
        if len(access_denied_list) > 5:
            print(f"... 还有 {len(access_denied_list) - 5} 个进程")
    
    print("\n[性能统计]")
    print("-" * 90)
    print(f"成功调整: {len(results):>6} | 访问被拒绝: {len(access_denied_list):>6}")
    print(f"需要管理员: {need_admin_count:>6} | 系统跳过: {system_skip_count:>6}")
    print(f"系统保护: {len(protected_list):>6} | 总进程数: {len(processes):>6}")
    print("-" * 90)
    
    log_entries.append(f"成功调整: {len(results)}")
    log_entries.append(f"访问被拒绝: {len(access_denied_list)}")
    log_entries.append(f"系统保护: {len(protected_list)}")
    
    cpu_heavy = [r for r in results if r['cpu_percent'] > 10]
    memory_heavy = [r for r in results if r['memory_percent'] > 2]
    
    if cpu_heavy:
        print(f"\n[CPU占用较高进程] ({len(cpu_heavy)}个)")
        for r in sorted(cpu_heavy, key=lambda x: x['cpu_percent'], reverse=True)[:5]:
            print(f"  {r['name']:<20} PID:{r['pid']:<6} CPU:{r['cpu_percent']:.1f}%")
    
    if memory_heavy:
        print(f"\n[内存占用较高进程] ({len(memory_heavy)}个)")
        for r in sorted(memory_heavy, key=lambda x: x['memory_percent'], reverse=True)[:5]:
            print(f"  {r['name']:<20} PID:{r['pid']:<6} 内存:{r['memory_percent']:.1f}% ({r.get('memory_rss', 0):.1f} MB)")
    
    if system_metrics['gpus'] and len(system_metrics['gpus']) >= 2:
        print("\n[🤖 AI GPU智能推荐]")
        print("-" * 90)
        print(f"{'进程名':<20} {'应用类型':<12} {'推荐GPU':<20} {'理由'}")
        print("-" * 90)
        
        recommendations = []
        for result in sorted_results[:15]:
            rec = ai_gpu_recommendation(result['name'], system_metrics['gpus'])
            if rec['best_gpu']:
                recommendations.append(rec)
        
        for rec in recommendations:
            gpu_name = rec['best_gpu']['name'] if rec['best_gpu'] else '未知'
            print(f"{rec['app_name']:<20} {rec['category_desc']:<12} {gpu_name[:18]:<20} {rec['reason']}")
        
        print("\n[💡 推荐策略说明]")
        print("=" * 90)
        print("")
        print("┌─────────────────────────────────────────────────────────────────────┐")
        print("│ 🔰 独立显卡 → 适合需要大量图形处理的应用                           │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        print("│ NVIDIA GeForce: 游戏、AI、3D渲染首选                               │")
        print("│ AMD Radeon: 视频编码、多屏显示、性价比首选                         │")
        print("│ Intel Arc: 轻量级创作、XeSS超分辨率、办公+轻度创作                  │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        print("│ - 游戏应用: 英雄联盟、CSGO、GTA、赛博朋克等                        │")
        print("│ - 影视剪辑: Premiere、After Effects、达芬奇Resolve                  │")
        print("│ - 图像设计: Photoshop、Illustrator、Blender、Cinema 4D             │")
        print("│ - AI计算: Stable Diffusion、TensorFlow、PyTorch                   │")
        print("│ - 视频播放: 4K/8K高清视频解码、HDR内容                            │")
        print("└─────────────────────────────────────────────────────────────────────┘")
        print("")
        print("┌─────────────────────────────────────────────────────────────────────┐")
        print("│ ⚡ 集成显卡 (Intel UHD/HD) → 适合日常办公和轻量级应用               │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        print("│ - 浏览器: Chrome、Edge、Firefox等                                  │")
        print("│ - 办公软件: Word、Excel、PowerPoint、Outlook                       │")
        print("│ - 聊天工具: Teams、Discord、微信、QQ                               │")
        print("│ - 安全软件: 杀毒软件、防火墙                                       │")
        print("│ - 系统进程: 资源管理器、桌面窗口管理器等                            │")
        print("└─────────────────────────────────────────────────────────────────────┘")
        print("")
        print("[🌟 品牌优先推荐]")
        print("  - 游戏/AI/专业渲染 → NVIDIA (CUDA加速性能最佳)")
        print("  - 视频编码/AV1解码 → AMD (视频处理能力强)")
        print("  - 轻度创作/办公 → Intel Arc (平衡性能与功耗)")
        print("  - 日常办公/省电 → Intel UHD (功耗最低，续航最长)")
        print("")
        print("[💬 简单来说]")
        print("  如果你做影视剪辑、做图、玩游戏 → 用 NVIDIA/AMD/Intel Arc 独立显卡")
        print("  如果你只是上网、办公 → 用 Intel UHD 集成显卡就够了")
    
    if HISTORY_MANAGER:
        try:
            HISTORY_MANAGER.record_process_snapshot(results)
            HISTORY_MANAGER.clean_old_data()
        except Exception as e:
            print(f"\n[历史记录保存失败] {e}")
    
    if write_log(log_entries):
        print(f"\n[日志已保存] {LOG_FILE}")
    else:
        print("\n[日志保存失败]")
    
    if need_admin_count > 0 and not admin_mode:
        print("\n[提示] 部分系统进程需要管理员权限")
        print("请右键点击PowerShell -> 以管理员身份运行")
    
    print("=" * 90)

def run_web_server():
    if not FLASK_AVAILABLE:
        print("\n❌ Flask 未安装，请安装 Flask: pip install flask")
        return
    
    APP.initialize()
    APP.start_scheduler()
    
    global CONFIG_MANAGER, ML_MODEL, HISTORY_MANAGER, PERF_COUNTER, NETWORK_MONITOR
    CONFIG_MANAGER = APP.config_manager
    ML_MODEL = APP.ml_model
    HISTORY_MANAGER = APP.history_manager
    PERF_COUNTER = APP.perf_counter
    NETWORK_MONITOR = APP.network_monitor
    
    app = Flask(__name__)
    
    WEB_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI进程优先级管理器</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif; 
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0d1b2a 100%); 
            min-height: 100vh; 
            color: #ffffff;
            background-attachment: fixed;
        }
        .header { 
            background: rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(20px);
            padding: 1.25rem 2.5rem; 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.3);
            position: sticky;
            top: 0;
            z-index: 500;
        }
        .header h1 { 
            font-size: 1.75rem; 
            background: linear-gradient(90deg, #00d4ff, #7c3aed, #f093fb); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-weight: 700;
        }
        .header .version {
            font-size: 0.75rem;
            opacity: 0.5;
            font-weight: 400;
        }
        .header .status { 
            padding: 0.625rem 1.25rem; 
            border-radius: 25px; 
            font-size: 0.875rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.3s ease;
        }
        .header .status.admin { 
            background: linear-gradient(135deg, #10b981, #059669); 
            color: #ffffff;
            box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
        }
        .header .status.normal { 
            background: linear-gradient(135deg, #f59e0b, #d97706); 
            color: #ffffff;
            box-shadow: 0 0 20px rgba(245, 158, 11, 0.4);
        }
        .container { 
            padding: 2.5rem; 
            max-width: 1600px; 
            margin: 0 auto; 
        }
        .stats-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); 
            gap: 1.5rem; 
            margin-bottom: 2.5rem; 
        }
        .stat-card { 
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.02));
            backdrop-filter: blur(10px);
            border-radius: 20px; 
            padding: 2rem; 
            border: 1px solid rgba(255, 255, 255, 0.08);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }
        .stat-card.cpu::before { background: linear-gradient(180deg, #00d4ff, #3b82f6); }
        .stat-card.memory::before { background: linear-gradient(180deg, #7c3aed, #8b5cf6); }
        .stat-card.process::before { background: linear-gradient(180deg, #10b981, #059669); }
        .stat-card.disk::before { background: linear-gradient(180deg, #f59e0b, #d97706); }
        .stat-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 15px 40px rgba(0, 0, 0, 0.35);
        }
        .stat-card .value { 
            font-size: 2.75rem; 
            font-weight: 700; 
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        .stat-card .label { 
            font-size: 1rem; 
            opacity: 0.7; 
            color: rgba(255, 255, 255, 0.7);
            font-weight: 500;
        }
        .search-bar { 
            display: flex; 
            gap: 1rem; 
            margin-bottom: 2.5rem;
            align-items: center;
            flex-wrap: wrap;
        }
        .search-bar input { 
            flex: 1; 
            min-width: 280px;
            padding: 1rem 1.25rem; 
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px; 
            background: rgba(255, 255, 255, 0.05); 
            color: #ffffff; 
            font-size: 1rem;
            transition: all 0.3s ease;
            outline: none;
        }
        .search-bar input:focus {
            border-color: #00d4ff;
            box-shadow: 0 0 25px rgba(0, 212, 255, 0.2);
            background: rgba(255, 255, 255, 0.08);
        }
        .search-bar input::placeholder {
            color: rgba(255, 255, 255, 0.4);
        }
        .search-bar select {
            padding: 1rem 1.25rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.05);
            color: #ffffff;
            font-size: 1rem;
            cursor: pointer;
            min-width: 160px;
            transition: all 0.3s ease;
            outline: none;
        }
        .search-bar select:focus {
            border-color: #00d4ff;
            box-shadow: 0 0 25px rgba(0, 212, 255, 0.2);
        }
        .search-bar select option {
            background: #1a1a2e;
            color: #ffffff;
        }
        .search-bar button { 
            padding: 1rem 2rem; 
            border: none; 
            border-radius: 14px; 
            background: linear-gradient(90deg, #00d4ff, #7c3aed); 
            color: #ffffff; 
            font-weight: 600; 
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            white-space: nowrap;
        }
        .search-bar button:hover { 
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 212, 255, 0.4);
        }
        .search-bar button.auto {
            background: linear-gradient(90deg, #10b981, #059669);
        }
        .search-bar button.auto:hover {
            box-shadow: 0 8px 25px rgba(16, 185, 129, 0.4);
        }
        .process-table-wrapper {
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02));
            backdrop-filter: blur(10px);
            border-radius: 20px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.06);
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
        }
        .process-table { 
            width: 100%; 
            border-collapse: collapse; 
        }
        .process-table th, .process-table td { 
            padding: 1.25rem 1.5rem; 
            text-align: left; 
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }
        .process-table th { 
            background: rgba(0, 0, 0, 0.15); 
            font-weight: 600;
            font-size: 0.95rem;
            color: rgba(255, 255, 255, 0.8);
            cursor: pointer;
            position: relative;
            transition: all 0.2s ease;
        }
        .process-table th:hover {
            background: rgba(0, 0, 0, 0.25);
        }
        .process-table th.sortable::after {
            content: ' ↕';
            font-size: 0.7rem;
            opacity: 0.4;
            margin-left: 0.25rem;
        }
        .process-table tr {
            transition: all 0.2s ease;
        }
        .process-table tr:hover { 
            background: rgba(255, 255, 255, 0.04);
            transform: scale(1.002);
        }
        .priority { 
            padding: 0.5rem 1.125rem; 
            border-radius: 10px; 
            font-size: 0.85rem; 
            font-weight: 700;
            text-align: center;
            min-width: 90px;
            display: inline-block;
        }
        .priority.high { 
            background: linear-gradient(135deg, #ef4444, #dc2626); 
            box-shadow: 0 3px 12px rgba(239, 68, 68, 0.4);
        }
        .priority.above { 
            background: linear-gradient(135deg, #f59e0b, #d97706); 
            box-shadow: 0 3px 12px rgba(245, 158, 11, 0.4);
        }
        .priority.normal { 
            background: linear-gradient(135deg, #10b981, #059669); 
            box-shadow: 0 3px 12px rgba(16, 185, 129, 0.4);
        }
        .priority.below { 
            background: linear-gradient(135deg, #6b7280, #4b5563); 
        }
        .priority.idle { 
            background: linear-gradient(135deg, #374151, #1f2937); 
        }
        .btn { 
            padding: 0.625rem 1.375rem; 
            border: none; 
            border-radius: 10px; 
            cursor: pointer; 
            font-size: 0.9rem;
            font-weight: 600;
            transition: all 0.25s ease;
        }
        .btn.up { 
            background: linear-gradient(135deg, #10b981, #059669); 
            color: #ffffff; 
        }
        .btn.up:hover {
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.5);
            transform: translateY(-1px);
        }
        .btn.down { 
            background: linear-gradient(135deg, #ef4444, #dc2626); 
            color: #ffffff; 
        }
        .btn.down:hover {
            box-shadow: 0 4px 15px rgba(239, 68, 68, 0.5);
            transform: translateY(-1px);
        }
        .btn.cancel { 
            background: rgba(255, 255, 255, 0.1); 
            color: #ffffff; 
        }
        .btn.cancel:hover {
            background: rgba(255, 255, 255, 0.15);
        }
        .modal { 
            display: none; 
            position: fixed; 
            top: 0; 
            left: 0; 
            width: 100%; 
            height: 100%; 
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(10px);
            justify-content: center; 
            align-items: center; 
            z-index: 1000;
            animation: fadeIn 0.25s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        .modal.active { display: flex; }
        .modal-content { 
            background: linear-gradient(145deg, #1a1a2e, #16213e);
            padding: 2.5rem; 
            border-radius: 24px; 
            min-width: 480px;
            box-shadow: 0 25px 80px rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.08);
            animation: slideUp 0.35s ease;
            position: relative;
        }
        @keyframes slideUp {
            from { transform: translateY(30px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        .modal-content h3 { 
            margin-bottom: 1.5rem; 
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            color: #ffffff;
        }
        .modal-content label { 
            display: block; 
            margin-bottom: 0.875rem;
            font-weight: 600;
            color: rgba(255, 255, 255, 0.9);
            font-size: 1rem;
        }
        .modal-content select { 
            width: 100%; 
            padding: 1rem 1.25rem; 
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px; 
            background: rgba(255, 255, 255, 0.05); 
            color: #ffffff; 
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.3s ease;
            outline: none;
        }
        .modal-content select:focus {
            border-color: #00d4ff;
            box-shadow: 0 0 25px rgba(0, 212, 255, 0.2);
        }
        .modal-content select option {
            background: #1a1a2e;
            color: #ffffff;
        }
        .modal-content .buttons { 
            display: flex; 
            gap: 1rem; 
            margin-top: 2rem; 
        }
        .modal-content .btn { 
            flex: 1; 
            padding: 1rem;
            font-size: 1rem;
        }
        .modal-content .process-info {
            margin-bottom: 1.5rem;
            padding: 1rem 1.25rem;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            font-size: 0.95rem;
        }
        .modal-content .process-info span {
            opacity: 0.6;
            margin-right: 0.5rem;
        }
        .modal-content .tip {
            margin-top: 1.25rem;
            padding: 1rem 1.25rem;
            background: rgba(0, 212, 255, 0.1);
            border-radius: 10px;
            font-size: 0.875rem;
            opacity: 0.85;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .loading { 
            text-align: center; 
            padding: 4rem; 
            color: #00d4ff;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 1.5rem;
        }
        .loading::before {
            content: '';
            width: 48px;
            height: 48px;
            border: 3px solid rgba(0, 212, 255, 0.2);
            border-top-color: #00d4ff;
            border-radius: 50%;
            animation: spin 0.9s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .notification {
            position: fixed;
            bottom: 2.5rem;
            right: 2.5rem;
            padding: 1.25rem 1.75rem;
            border-radius: 14px;
            color: #ffffff;
            font-weight: 600;
            z-index: 2000;
            animation: slideIn 0.35s ease;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        @keyframes slideIn {
            from { transform: translateX(120px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        .notification.success {
            background: linear-gradient(135deg, #10b981, #059669);
        }
        .notification.error {
            background: linear-gradient(135deg, #ef4444, #dc2626);
        }
        .notification.info {
            background: linear-gradient(135deg, #00d4ff, #3b82f6);
        }
        .type-badge {
            padding: 0.375rem 0.875rem;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.1);
            color: rgba(255, 255, 255, 0.9);
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AI进程优先级管理器<span class="version">v8.3</span></h1>
        <span class="status {{ 'admin' if admin_mode_str == 'true' else 'normal' }}">
            {{ '🛡️ 管理员模式' if admin_mode_str == 'true' else '🔒 普通模式' }}
        </span>
    </div>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card process">
                <div class="value">{{ total_processes }}</div>
                <div class="label">总进程数</div>
            </div>
            <div class="stat-card cpu">
                <div class="value">{{ cpu_percent }}%</div>
                <div class="label">CPU使用率</div>
            </div>
            <div class="stat-card memory">
                <div class="value">{{ memory_percent }}%</div>
                <div class="label">内存使用率</div>
            </div>
            <div class="stat-card disk">
                <div class="value">{{ disk_percent }}%</div>
                <div class="label">磁盘使用率</div>
            </div>
        </div>
        
        <div class="search-bar">
            <input type="text" id="searchInput" placeholder="🔍 搜索进程名称..." onkeyup="filterTable()">
            <select id="typeFilter" onchange="filterTable()">
                <option value="">全部类型</option>
                <option value="game">🎮 游戏</option>
                <option value="video">🎬 视频/渲染</option>
                <option value="system">⚙️ 系统</option>
                <option value="office">📊 办公</option>
                <option value="unknown">❓ 未知</option>
            </select>
            <button onclick="refreshProcesses()">🔄 刷新</button>
            <button onclick="autoOptimize()">🤖 自动优化</button>
        </div>
        
        <div class="loading" id="loading" style="display: none;">正在分析进程...</div>
        
        <div class="process-table-wrapper">
            <table class="process-table" id="processTable">
                <thead>
                    <tr>
                        <th class="sortable" onclick="sortTable('pid')">PID</th>
                        <th class="sortable" onclick="sortTable('name')">名称</th>
                        <th class="sortable" onclick="sortTable('type')">类型</th>
                        <th class="sortable" onclick="sortTable('cpu')">CPU%</th>
                        <th class="sortable" onclick="sortTable('memory')">内存%</th>
                        <th class="sortable" onclick="sortTable('threads')">线程</th>
                        <th class="sortable" onclick="sortTable('score')">评分</th>
                        <th>优先级</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="processBody">
                </tbody>
            </table>
        </div>
    </div>
    
    <div class="modal" id="priorityModal">
        <div class="modal-content">
            <h3>⚙️ 设置优先级</h3>
            <input type="hidden" id="modalPid">
            <input type="hidden" id="modalProcessName">
            <div class="process-info">
                <span>目标进程:</span>
                <span id="modalProcessDisplay" style="font-weight: 600;"></span>
            </div>
            <label>选择优先级:</label>
            <select id="prioritySelect">
                <option value="high">🔴 高 (H)</option>
                <option value="above_normal">🟠 高于正常 (A)</option>
                <option value="normal">🟢 正常 (N)</option>
                <option value="below_normal">⬜ 低于正常 (B)</option>
                <option value="idle">⚫ 空闲 (I)</option>
            </select>
            <div class="tip">💡 优先级更改后，部分应用可能需要重启才能生效</div>
            <div class="buttons">
                <button class="btn cancel" onclick="closeModal()">取消</button>
                <button class="btn" onclick="setPriority()">确定</button>
            </div>
        </div>
    </div>

    <script>
        let processes = [];
        
        async function loadProcesses() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('processTable').style.display = 'none';
            const tbody = document.getElementById('processBody');
            tbody.innerHTML = '';
            
            try {
                const response = await fetch('/api/processes');
                if (!response.ok) {
                    throw new Error('网络请求失败');
                }
                const data = await response.json();
                processes = data.processes || [];
                console.log('加载到进程数:', processes.length);
                renderTable();
            } catch (error) {
                console.error('加载失败:', error);
                tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#ef4444;">加载进程失败</td></tr>';
            }
            
            document.getElementById('loading').style.display = 'none';
            document.getElementById('processTable').style.display = 'table';
        }
        
        function renderTable(filter = '', typeFilter = '') {
            const tbody = document.getElementById('processBody');
            
            if (!processes || processes.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#f59e0b;padding:2rem;">暂无进程数据，请点击刷新按钮</td></tr>';
                return;
            }
            
            let filtered = processes.filter(p => 
                p.name && p.name.toLowerCase().includes(filter.toLowerCase())
            );
            
            if (typeFilter && typeFilter !== '') {
                filtered = filtered.filter(p => p.type === typeFilter);
            }
            
            filtered.sort((a, b) => {
                let aVal = a[sortField];
                let bVal = b[sortField];
                
                if (typeof aVal === 'string') aVal = aVal.toLowerCase();
                if (typeof bVal === 'string') bVal = bVal.toLowerCase();
                
                if (sortOrder === 'asc') {
                    return aVal > bVal ? 1 : -1;
                } else {
                    return aVal < bVal ? 1 : -1;
                }
            });
            
            if (filtered.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#6b7280;padding:2rem;">未找到匹配的进程</td></tr>';
                return;
            }
            
            const totalPages = Math.ceil(filtered.length / pageSize);
            const start = (currentPage - 1) * pageSize;
            const end = start + pageSize;
            const pageData = filtered.slice(start, end);
            
            const getTypeLabel = (type) => {
                const labels = {
                    'game': '🎮 游戏',
                    'video': '🎬 视频',
                    'system': '⚙️ 系统',
                    'office': '📊 办公',
                    'unknown': '❓ 未知'
                };
                return labels[type] || '❓ 未知';
            };
            
            tbody.innerHTML = pageData.map(p => {
                const cpu = typeof p.cpu === 'number' ? p.cpu.toFixed(1) : '0.0';
                const memory = typeof p.memory === 'number' ? p.memory.toFixed(1) : '0.0';
                const score = typeof p.score === 'number' ? p.score.toFixed(1) : '0.0';
                
                return `
                <tr>
                    <td style="font-family: monospace; font-weight: 600;">${p.pid || 'N/A'}</td>
                    <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${p.name || 'Unknown'}</td>
                    <td>${getTypeLabel(p.type)}</td>
                    <td>${cpu}</td>
                    <td>${memory}</td>
                    <td>${p.threads || 1}</td>
                    <td style="font-weight: 600;">${score}</td>
                    <td><span class="priority ${getPriorityClass(p.priority)}">${p.priority_display || 'N/A'}</span></td>
                    <td>
                        <button class="btn up" onclick="openModal(${p.pid})">设置</button>
                    </td>
                </tr>
                `;
            }).join('');
        }
        
        function getPriorityClass(priority) {
            const map = { '高(H)': 'high', '高于正常(A)': 'above', '正常(N)': 'normal', '低于正常(B)': 'below', '空闲(I)': 'idle' };
            return map[priority] || 'normal';
        }
        
        let currentPage = 1;
        const pageSize = 20;
        let sortField = 'score';
        let sortOrder = 'desc';
        
        function filterTable() {
            const filter = document.getElementById('searchInput').value;
            const typeFilter = document.getElementById('typeFilter').value;
            currentPage = 1;
            renderTable(filter, typeFilter);
        }
        
        function sortTable(field) {
            if (sortField === field) {
                sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                sortField = field;
                sortOrder = field === 'score' ? 'desc' : 'asc';
            }
            renderTable(document.getElementById('searchInput').value, document.getElementById('typeFilter').value);
        }
        
        function openModal(pid) {
            const process = processes.find(p => p.pid === pid);
            document.getElementById('modalPid').value = pid;
            document.getElementById('modalProcessName').value = process?.name || '';
            document.getElementById('modalProcessDisplay').textContent = `PID: ${pid} - ${process?.name || '未知进程'}`;
            document.getElementById('priorityModal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('priorityModal').classList.remove('active');
        }
        
        async function setPriority() {
            const pid = document.getElementById('modalPid').value;
            const priority = document.getElementById('prioritySelect').value;
            
            try {
                const response = await fetch(`/api/set_priority/${pid}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ priority })
                });
                const data = await response.json();
                if (data.success) {
                    loadProcesses();
                }
            } catch (error) {
                console.error('设置失败:', error);
            }
            closeModal();
        }
        
        async function refreshProcesses() {
            await loadProcesses();
        }
        
        async function autoOptimize() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('processTable').style.display = 'none';
            
            try {
                const response = await fetch('/api/optimize', { method: 'POST' });
                const data = await response.json();
                alert(`优化完成! 成功调整: ${data.success} 个进程`);
            } catch (error) {
                console.error('优化失败:', error);
            }
            
            await loadProcesses();
        }
        
        document.addEventListener('DOMContentLoaded', loadProcesses);
    </script>
</body>
</html>
    """
    
    @app.route('/')
    def index():
        admin_mode = is_admin()
        system_stats = get_system_stats_for_web()
        return render_template_string(WEB_TEMPLATE, 
            admin_mode_str='true' if admin_mode else 'false',
            total_processes=system_stats['total_processes'],
            cpu_percent=system_stats['cpu_percent'],
            memory_percent=system_stats['memory_percent'],
            disk_percent=system_stats['disk_percent']
        )
    
    def get_process_priority_display(proc):
        try:
            priority_value = proc.nice()
            priority_key = get_priority_key(priority_value)
            return PRIORITY_DISPLAY.get(priority_key, '未知')
        except:
            return '未知'
    
    def calculate_score(process_name, cpu_percent, memory_percent, num_threads):
        score = 50
        
        process_name_lower = process_name.lower()
        
        proc_type = classify_process(process_name_lower)
        
        type_scores = {'game': 70, 'video': 65, 'system': 60, 'office': 50, 'unknown': 45}
        base_score = type_scores.get(proc_type, 45)
        
        score = base_score
        
        if cpu_percent > 0:
            score += min(cpu_percent / 4, 20)
        if memory_percent > 0:
            score += min(memory_percent / 4, 15)
        if num_threads > 4:
            score += min((num_threads - 4) * 2, 10)
        
        type_bonus = {'game': 10, 'video': 8, 'system': 5}
        score += type_bonus.get(proc_type, 0)
        
        return min(max(score, 0), 100)
    
    @app.route('/api/processes')
    def api_processes():
        processes_data = []
        try:
            all_procs = list(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'num_threads']))
            print(f"Total processes found: {len(all_procs)}")
            
            for proc in all_procs:
                try:
                    proc_info = proc.info
                    if proc_info['name'] and proc_info['pid']:
                        proc_type = classify_process(proc_info['name'])
                        cpu_val = float(proc_info['cpu_percent']) if proc_info['cpu_percent'] else 0.0
                        mem_val = float(proc_info['memory_percent']) if proc_info['memory_percent'] else 0.0
                        threads_val = int(proc_info['num_threads']) if proc_info['num_threads'] else 1
                        score = calculate_score(proc_info['name'], cpu_val, mem_val, threads_val)
                        priority = get_process_priority_display(proc)
                        
                        processes_data.append({
                            'pid': int(proc_info['pid']),
                            'name': str(proc_info['name']),
                            'type': str(proc_type),
                            'cpu': cpu_val,
                            'memory': mem_val,
                            'threads': threads_val,
                            'score': float(score),
                            'priority': str(priority),
                            'priority_display': str(priority)
                        })
                except Exception as e:
                    print(f"Process error: {e}")
                    continue
            
            print(f"Processes after filtering: {len(processes_data)}")
            processes_data.sort(key=lambda x: x['score'], reverse=True)
        except Exception as e:
            print(f"API Error: {e}")
        
        return jsonify({'processes': processes_data})
    
    @app.route('/api/set_priority/<int:pid>', methods=['POST'])
    def api_set_priority(pid):
        try:
            data = request.get_json()
            priority = data.get('priority')
            
            if priority not in PRIORITY_LEVELS:
                return jsonify({'success': False, 'error': '无效的优先级'})
            
            proc = psutil.Process(pid)
            # 记录调整前的优先级
            old_priority = proc.nice()
            old_priority_key = get_priority_key(old_priority)
            proc.nice(PRIORITY_LEVELS[priority])
            
            # 记录用户手动调整
            process_name = proc.name()
            preference_learner.record_manual_adjustment(process_name, old_priority_key, priority)
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/api/optimize', methods=['POST'])
    def api_optimize():
        results = analyze_all_processes()
        success_count = sum(1 for r in results if r['status'] == 'success')
        return jsonify({'success': success_count})
    
    def get_system_stats_for_web():
        cpu_percent = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': mem.percent,
            'disk_percent': disk.percent,
            'total_processes': len(list(psutil.process_iter()))
        }
    
    print("\nWeb服务器启动中...")
    print("访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务器")
    app.run(host='0.0.0.0', port=5000, debug=False)

def start_api_server(port=5000):
    global API_SERVER, CONFIG_MANAGER, ML_MODEL, HISTORY_MANAGER, PERF_COUNTER, NETWORK_MONITOR, CONFIG_WATCHER
    
    if not API_AVAILABLE:
        print("❌ API模块不可用，请安装 flask 和 flask-cors")
        return
    
    try:
        APP.initialize()
        
        CONFIG_MANAGER = APP.config_manager
        CONFIG_WATCHER = APP.config_watcher
        ML_MODEL = APP.ml_model
        HISTORY_MANAGER = APP.history_manager
        PERF_COUNTER = APP.perf_counter
        NETWORK_MONITOR = APP.network_monitor
        
        def api_analyze_process(proc, use_ml=False):
            system_metrics = get_system_metrics()
            admin_mode = is_admin()
            config = CONFIG_MANAGER.get_app_categories() if CONFIG_MANAGER else APP_CATEGORIES
            return analyze_process(proc, system_metrics, admin_mode, config)
        
        def api_set_priority(pid, priority):
            try:
                proc = psutil.Process(pid)
                proc.nice(PRIORITY_LEVELS.get(priority, PRIORITY_LEVELS['NORMAL_PRIORITY_CLASS']))
                return True
            except Exception:
                return False
        
        API_SERVER = ProcessPriorityAPI(port=port)
        
        API_SERVER.set_dependencies(
            config_manager=CONFIG_MANAGER,
            history_manager=HISTORY_MANAGER,
            perf_counter=PERF_COUNTER,
            network_monitor=NETWORK_MONITOR,
            ml_model=ML_MODEL,
            analyze_process_func=api_analyze_process,
            set_priority_func=api_set_priority,
            is_admin_func=is_admin
        )
        
        API_SERVER.start()
        
        print(f"\n🚀 REST API服务已启动")
        print(f"访问地址: http://localhost:{port}")
        print(f"API文档: http://localhost:{port}/api/health")
        print("按 Ctrl+C 停止服务")
        
        while True:
            time.sleep(1)
    
    except ImportError:
        print("❌ Flask不可用，请安装: pip install flask flask-cors")
    except Exception as e:
        print(f"❌ API服务启动失败: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == '--web':
            run_web_server()
            sys.exit(0)
        elif sys.argv[1] == '--tray':
            if TRAY_AVAILABLE:
                run_tray_service()
            else:
                print("❌ 系统托盘功能不可用，请安装依赖: pip install pystray pillow")
                sys.exit(1)
            sys.exit(0)
        elif sys.argv[1] == '--widget':
            # 启动小组件模式
            from api.app import ProcessPriorityAPI
            try:
                from dashboard.widget import widget_bp
                api = ProcessPriorityAPI()
                api.app.register_blueprint(widget_bp)
                api.start()
                print("\n🎮 小组件服务已启动")
                print("访问地址: http://localhost:5000/widget")
                print("按 Ctrl+C 停止服务")
                while True:
                    time.sleep(1)
            except ImportError as e:
                print(f"❌ 导入失败: {e}")
                sys.exit(1)
            sys.exit(0)
    
    main()