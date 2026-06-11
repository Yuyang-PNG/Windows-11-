import threading
import time
from typing import Tuple, Dict, Optional, Any
from core.di_container import ServiceProvider
from core.logger import get_logger


class TTLCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            data, timestamp = self._cache[key]
            if self._is_expired(timestamp):
                del self._cache[key]
                return None
            return data

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = (value, self._get_timestamp())

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def _is_expired(self, timestamp: float) -> bool:
        return self._get_timestamp() - timestamp > self._ttl

    @staticmethod
    def _get_timestamp() -> float:
        return time.time()


CategoryInfo = Dict[str, Any]
CategoryConfig = Dict[str, CategoryInfo]

class AppClassifier:
    DEFAULT_CATEGORIES: CategoryConfig = {
        'gaming': {
            'keywords': ['game', 'gaming', 'steam', 'epic', 'battle.net', 'blizzard',
                         'league of legends', 'csgo', 'dota', 'valorant', 'pubg',
                         'fortnite', 'apex', 'minecraft', 'roblox', 'gta', 'elden ring',
                         'cyberpunk', 'starfield', 'wow', 'world of warcraft', 'lol',
                         'arknights', '明日方舟', 'honkai', 'genshin', '原神', '崩坏',
                         'touhou', '东方', 'fgo', 'fate', 'blue archive', 'bluearchive',
                         'azur lane', 'azurlane', 'warship girls', '战舰少女',
                         'counter-strike', 'overwatch', 'destiny', 'warframe'],
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
                         'system', 'conhost', 'wuahost', 'wudfhost', 'fontdrvhost'],
            'paths': ['windows\\system32', 'windows\\syswow64', 'program files\\nvidia',
                      'program files\\intel', 'program files\\amd'],
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

    def __init__(self):
        self._logger = get_logger(__name__)
        self._classification_cache = TTLCache(ttl_seconds=600)
        self._smart_classifier = None

    def _get_smart_classifier(self):
        if self._smart_classifier is None:
            from ml.smart_classifier import SmartAppClassifier
            self._smart_classifier = ServiceProvider.try_get(SmartAppClassifier)
        return self._smart_classifier

    def _get_categories(self) -> CategoryConfig:
        from config.config_manager import ConfigManager
        config_manager = ServiceProvider.try_get(ConfigManager)
        if config_manager:
            try:
                config = config_manager.get_app_categories()
                return config.get('categories', self.DEFAULT_CATEGORIES)
            except Exception as e:
                self._logger.error(f"加载外置配置失败: {e}")
        return self.DEFAULT_CATEGORIES

    def _build_cache_key(self, process_name: str, exe_path: Optional[str] = None,
                        window_title: Optional[str] = None) -> str:
        parts = [process_name.lower()]
        if exe_path:
            path_lower = exe_path.lower()
            if '\\windows\\' in path_lower or '\\system32\\' in path_lower or '\\syswow64\\' in path_lower:
                parts.append("system")
            elif '\\steam\\' in path_lower or '\\steamapps\\' in path_lower:
                parts.append("gaming")
            elif '\\program files\\' in path_lower:
                parts.append("userapp")
        if window_title:
            parts.append(window_title.lower()[:50])
        return "_".join(parts)

    def classify(self, process_name: str, exe_path: Optional[str] = None,
                window_title: Optional[str] = None, company_name: Optional[str] = None,
                use_smart: bool = True) -> Tuple[str, CategoryInfo]:
        cache_key = self._build_cache_key(process_name, exe_path, window_title)
        
        cached = self._classification_cache.get(cache_key)
        if cached is not None:
            self._logger.debug(f"使用缓存的分类结果: {process_name}")
            return cached

        name_lower = process_name.lower()
        path_lower = exe_path.lower() if exe_path else ""
        title_lower = window_title.lower() if window_title else ""
        company_lower = company_name.lower() if company_name else ""
        
        categories = self._get_categories()

        result = self._smart_inference(name_lower, categories)
        if result:
            self._classification_cache.set(cache_key, result)
            return result

        result = self._keyword_matching(name_lower, path_lower, title_lower, company_lower, categories)
        if result:
            self._classification_cache.set(cache_key, result)
            return result

        if use_smart:
            smart_classifier = self._get_smart_classifier()
            if smart_classifier:
                ml_category, confidence, method = smart_classifier.predict_with_fallback(
                    process_name, exe_path, window_title, company_name
                )
                if ml_category is not None:
                    cat_info = categories.get(ml_category, self.DEFAULT_CATEGORIES.get(ml_category, {}))
                    if cat_info:
                        self._logger.debug(f"进程 {process_name} 通过智能分类器分类为 {ml_category} (置信度: {confidence:.2f})")
                        result = (ml_category, cat_info)
                        self._classification_cache.set(cache_key, result)
                        return result

        result = self._path_pattern_matching(path_lower, categories)
        if result:
            self._classification_cache.set(cache_key, result)
            return result

        self._logger.debug(f"进程 {process_name} 无法分类，返回未知")
        result = ('unknown', {'description': '未知应用', 'suggested_gpu': 'auto', 'priority': 'medium'})
        self._classification_cache.set(cache_key, result)
        return result

    def _smart_inference(self, name_lower: str, categories: CategoryConfig) -> Optional[Tuple[str, CategoryInfo]]:
        game_features = ['gameclient', 'game', 'steam', 'epic', 'battle', 'riot', 'valorant', 'league']
        if any(x in name_lower for x in game_features):
            return ('gaming', categories.get('gaming', self.DEFAULT_CATEGORIES.get('gaming', {})))

        dev_features = ['code', 'idea', 'pycharm', 'webstorm', 'datagrip', 'clion', 'rider', 'android', 'xcode']
        if any(x in name_lower for x in dev_features):
            return ('development', categories.get('development', self.DEFAULT_CATEGORIES.get('development', {})))

        design_features = ['photoshop', 'illustrator', 'afterfx', 'premiere', 'audition', 'indesign', 'blender', 'maya']
        if any(x in name_lower for x in design_features):
            return ('design', categories.get('design', self.DEFAULT_CATEGORIES.get('design', {})))

        office_features = ['excel', 'word', 'powerpoint', 'outlook', 'onenote', 'access', 'project', 'visio', 'notion', 'wps']
        if any(x in name_lower for x in office_features):
            return ('productivity', categories.get('productivity', self.DEFAULT_CATEGORIES.get('productivity', {})))

        browser_features = ['browser', 'chrome', 'firefox', 'safari', 'opera', 'brave', 'vivaldi', 'liebao', 'sogou', 'qqbrowser']
        if any(x in name_lower for x in browser_features):
            return ('browser', categories.get('browser', self.DEFAULT_CATEGORIES.get('browser', {})))

        comm_features = ['wechat', 'dingtalk', 'feishu', 'slack', 'discord', 'teams', 'zoom', 'qq', 'tm', 'tim', 'whatsapp', 'telegram']
        if any(x in name_lower for x in comm_features):
            return ('communication', categories.get('communication', self.DEFAULT_CATEGORIES.get('communication', {})))

        media_features = ['player', 'vlc', 'potplayer', 'mpc', 'media', 'music', 'audio', 'obs', 'stream']
        if any(x in name_lower for x in media_features):
            category_key = 'video' if 'player' in name_lower or 'vlc' in name_lower else 'music'
            return (category_key, categories.get(category_key, self.DEFAULT_CATEGORIES.get(category_key, {})))

        security_features = ['security', 'antivirus', '360', 'qqpc', 'baidu', 'kingsoft', 'avast', 'avg', 'kaspersky', 'norton', 'mcafee', 'defender']
        if any(x in name_lower for x in security_features):
            return ('security', categories.get('security', self.DEFAULT_CATEGORIES.get('security', {})))

        update_features = ['update', 'updater', 'service', 'daemon', 'helper', 'agent', 'tray', 'notification']
        if any(x in name_lower for x in update_features):
            return ('system', categories.get('system', self.DEFAULT_CATEGORIES.get('system', {})))

        return None

    def _keyword_matching(self, name_lower: str, path_lower: str, title_lower: str,
                         company_lower: str, categories: CategoryConfig) -> Optional[Tuple[str, CategoryInfo]]:
        matched_categories: List[Tuple[str, int, CategoryInfo]] = []

        for category, info in categories.items():
            score = 0

            for keyword in info.get('keywords', []):
                if isinstance(keyword, str) and keyword in name_lower:
                    score += 10

            for path_keyword in info.get('paths', []):
                if isinstance(path_keyword, str) and path_keyword in path_lower:
                    score += 8

            for title_keyword in info.get('window_titles', []):
                if isinstance(title_keyword, str) and title_keyword.lower() in title_lower:
                    score += 12

            company_keywords = info.get('company_keywords', [])
            for company_keyword in company_keywords:
                if isinstance(company_keyword, str) and company_keyword in company_lower:
                    score += 15

            if score > 0:
                matched_categories.append((category, score, info))

        if matched_categories:
            matched_categories.sort(key=lambda x: x[1], reverse=True)
            top_category = matched_categories[0]
            self._logger.debug(f"进程分类为 {top_category[0]} (评分: {top_category[1]})")
            return (top_category[0], top_category[2])

        return None

    def _path_pattern_matching(self, path_lower: str, categories: CategoryConfig) -> Optional[Tuple[str, CategoryInfo]]:
        path_patterns = [
            ('\\games\\', 'gaming'),
            ('\\steamapps\\', 'gaming'),
            ('\\epic games\\', 'gaming'),
            ('\\origin\\', 'gaming'),
            ('\\ubisoft\\', 'gaming'),
            ('\\adobe\\', 'design'),
            ('\\photoshop\\', 'design'),
            ('\\illustrator\\', 'design'),
            ('\\premiere\\', 'design'),
            ('\\autodesk\\', 'design'),
            ('\\blender\\', 'design'),
            ('\\microsoft office\\', 'productivity'),
            ('\\office15\\', 'productivity'),
            ('\\office16\\', 'productivity'),
            ('\\python\\', 'development'),
            ('\\visual studio\\', 'development'),
            ('\\jetbrains\\', 'development'),
            ('\\git\\', 'development'),
            ('\\nodejs\\', 'development'),
            ('\\windows\\', 'system'),
            ('\\system32\\', 'system'),
            ('\\syswow64\\', 'system'),
        ]
        
        for pattern, category in path_patterns:
            if pattern in path_lower:
                cat_info = categories.get(category, self.DEFAULT_CATEGORIES.get(category, {}))
                self._logger.debug(f"通过路径 {pattern} 分类为 {category}")
                return (category, cat_info)

        return None

    def clear_cache(self):
        self._classification_cache.invalidate()

    def get_cache_size(self) -> int:
        return len(self._classification_cache)