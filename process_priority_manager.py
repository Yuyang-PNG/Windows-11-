import psutil
import sys
import os
import time
import threading
from queue import Queue
import glob
from datetime import datetime
import json

PRIORITY_LEVELS = {
    'idle': psutil.IDLE_PRIORITY_CLASS,
    'below_normal': psutil.BELOW_NORMAL_PRIORITY_CLASS,
    'normal': psutil.NORMAL_PRIORITY_CLASS,
    'above_normal': psutil.ABOVE_NORMAL_PRIORITY_CLASS,
    'high': psutil.HIGH_PRIORITY_CLASS,
    'realtime': psutil.REALTIME_PRIORITY_CLASS
}

PRIORITY_DISPLAY = {
    'idle': '空闲(I)',
    'below_normal': '低于正常(B)',
    'normal': '正常(N)',
    'above_normal': '高于正常(A)',
    'high': '高(H)',
    'realtime': '实时(R)'
}

SYSTEM_PROCESSES = {'system', 'system idle process', 'smss.exe', 'csrss.exe', 
                    'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe',
                    'fontdrvhost.exe', 'dwm.exe', 'taskhostw.exe', 'explorer.exe'}

USER_APP_PROCESSES = {'chrome.exe', 'msedge.exe', 'firefox.exe', 'notepad.exe',
                      'code.exe', 'visualstudio.exe', 'idea64.exe', 'pycharm.exe',
                      'teams.exe', 'discord.exe', 'steam.exe', 'spotify.exe',
                      'word.exe', 'excel.exe', 'powerpnt.exe', 'outlook.exe'}

NEED_ADMIN_PROCESSES = {'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe', 
                        'lsass.exe', 'system', 'system idle process'}

PROTECTED_PROCESSES = {'dwm.exe', 'explorer.exe', 'csrss.exe', 'smss.exe', 
                       'lsass.exe', 'system', 'system idle process'}

THREAD_COUNT = 8
LOG_FILE = 'process_priority_log.txt'
CONFIG_FILE = 'gpu_config.json'

GPU_PREFERENCES = {
    'auto': '让 Windows 决定',
    'integrated': '节能 (集成显卡)',
    'discrete': '高性能 (独立显卡)'
}

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
        'keywords': ['browser', 'chrome', 'edge', 'firefox', 'brave', 'opera', 'safari',
                     'cent', 'maxthon'],
        'paths': ['google\\chrome', 'microsoft\\edge', 'mozilla\\firefox',
                  'brave software', 'opera software'],
        'window_titles': ['- Google Chrome', '- Microsoft Edge', '- Mozilla Firefox'],
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
                     'smss', 'csrss', 'wininit', 'winlogon', 'rundll32', 'cmd', 'powershell'],
        'paths': ['windows\\system32', 'windows\\syswow64'],
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

def classify_app(process_name, exe_path=None, window_title=None, company_name=None):
    name_lower = process_name.lower()
    path_lower = exe_path.lower() if exe_path else ""
    title_lower = window_title.lower() if window_title else ""
    company_lower = company_name.lower() if company_name else ""
    
    matched_categories = []
    
    for category, info in APP_CATEGORIES.items():
        score = 0
        
        for keyword in info.get('keywords', []):
            if keyword in name_lower:
                score += 10
        
        for path_keyword in info.get('paths', []):
            if path_keyword in path_lower:
                score += 8
        
        for title_keyword in info.get('window_titles', []):
            if title_keyword.lower() in title_lower:
                score += 12
        
        company_keywords = {
            'gaming': ['valve', 'riot', 'blizzard', 'epic', 'rockstar', 'ubisoft', 'ea', 'nintendo'],
            'browser': ['google', 'microsoft', 'mozilla', 'opera', 'brave'],
            'productivity': ['microsoft', 'kingsoft', 'wps'],
            'design': ['adobe', 'autodesk', 'maxon'],
            'system': ['microsoft'],
            'communication': ['tencent', 'discord', 'telegram']
        }
        
        if category in company_keywords:
            for company_keyword in company_keywords[category]:
                if company_keyword in company_lower:
                    score += 15
        
        if score > 0:
            matched_categories.append((category, score, info))
    
    if matched_categories:
        matched_categories.sort(key=lambda x: x[1], reverse=True)
        top_category = matched_categories[0]
        return top_category[0], top_category[2]
    
    if exe_path:
        if '\\games\\' in path_lower or '\\steamapps\\' in path_lower:
            return 'gaming', APP_CATEGORIES['gaming']
        if '\\adobe\\' in path_lower:
            return 'design', APP_CATEGORIES['design']
        if '\\microsoft office\\' in path_lower:
            return 'productivity', APP_CATEGORIES['productivity']
        if '\\windows\\' in path_lower:
            return 'system', APP_CATEGORIES['system']
    
    return 'unknown', {'description': '未知应用', 'suggested_gpu': 'auto', 'priority': 'medium'}

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

def detect_gpu_brand(name):
    name_upper = name.upper()
    if 'NVIDIA' in name_upper or 'GEFORCE' in name_upper:
        return {'brand': 'NVIDIA', 'brand_name': '英伟达', 'color': '绿色'}
    elif 'AMD' in name_upper or 'RADEON' in name_upper:
        return {'brand': 'AMD', 'brand_name': '超威半导体', 'color': '红色'}
    elif 'INTEL ARC' in name_upper:
        return {'brand': 'Intel', 'brand_name': '英特尔 Arc', 'color': '蓝色', 'is_discrete': True}
    elif 'INTEL' in name_upper or 'UHD' in name_upper or 'HD GRAPHICS' in name_upper:
        return {'brand': 'Intel', 'brand_name': '英特尔', 'color': '蓝色', 'is_discrete': False}
    elif 'ATI' in name_upper:
        return {'brand': 'ATI', 'brand_name': 'ATI', 'color': '红色'}
    elif 'SAPPHIRE' in name_upper:
        return {'brand': 'Sapphire', 'brand_name': '蓝宝石', 'color': '蓝色'}
    elif 'EVGA' in name_upper:
        return {'brand': 'EVGA', 'brand_name': 'EVGA', 'color': '绿色'}
    elif 'MSI' in name_upper:
        return {'brand': 'MSI', 'brand_name': '微星', 'color': '红色'}
    else:
        return {'brand': 'Unknown', 'brand_name': '未知', 'color': '灰色', 'is_discrete': False}

def get_gpu_info():
    gpus = []
    detected_gpus = set()
    
    try:
        import subprocess
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,utilization.gpu', '--format=csv,noheader,nounits'], 
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.split(',')
                if len(parts) >= 4:
                    gpu_name = parts[0].strip()
                    if gpu_name not in detected_gpus:
                        detected_gpus.add(gpu_name)
                        brand_info = detect_gpu_brand(gpu_name)
                        gpus.append({
                            'name': gpu_name,
                            'memory_total': int(parts[1].strip()),
                            'memory_used': int(parts[2].strip()),
                            'utilization': int(parts[3].strip()),
                            'type': 'discrete',
                            **brand_info
                        })
    except:
        pass
    
    try:
        result = subprocess.run(['amdgpu-info', '--json'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            for gpu in data.get('amdgpu', []):
                gpu_name = gpu.get('name', 'Unknown AMD GPU')
                if gpu_name not in detected_gpus:
                    detected_gpus.add(gpu_name)
                    brand_info = detect_gpu_brand(gpu_name)
                    gpus.append({
                        'name': gpu_name,
                        'memory_total': int(gpu.get('memory_total', 0)),
                        'memory_used': int(gpu.get('memory_used', 0)),
                        'utilization': int(gpu.get('utilization', 0)),
                        'type': 'discrete',
                        **brand_info
                    })
    except:
        pass
    
    try:
        import wmi
        c = wmi.WMI()
        for adapter in c.Win32_VideoController():
            gpu_name = adapter.Name
            if gpu_name not in detected_gpus:
                detected_gpus.add(gpu_name)
                brand_info = detect_gpu_brand(gpu_name)
                vram = int(adapter.AdapterRAM) // (1024 ** 2) if adapter.AdapterRAM else 0
                
                if brand_info.get('is_discrete'):
                    gpu_type = 'discrete'
                elif 'Intel Arc' in gpu_name:
                    gpu_type = 'discrete'
                elif 'Intel' in gpu_name or 'UHD' in gpu_name or 'HD Graphics' in gpu_name:
                    gpu_type = 'integrated'
                else:
                    gpu_type = 'discrete' if vram > 1024 else 'integrated'
                
                gpus.append({
                    'name': gpu_name,
                    'memory_total': vram,
                    'memory_used': 0,
                    'utilization': 0,
                    'type': gpu_type,
                    **brand_info
                })
    except:
        pass
    
    for i, gpu in enumerate(gpus):
        gpu['index'] = i
    
    return gpus

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

def get_system_metrics():
    cpu_percent = psutil.cpu_percent(interval=0.01)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    gpus = get_gpu_info()
    
    disk_partitions = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disk_partitions.append({
                'device': part.device,
                'mountpoint': part.mountpoint,
                'percent': usage.percent,
                'free': usage.free / (1024 ** 3)
            })
        except:
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

def classify_process(process_name_lower):
    if process_name_lower in SYSTEM_PROCESSES:
        return 'system'
    if process_name_lower in USER_APP_PROCESSES:
        return 'user_app'
    if 'service' in process_name_lower or 'svc' in process_name_lower:
        return 'service'
    if 'background' in process_name_lower or 'daemon' in process_name_lower:
        return 'background'
    return 'unknown'

def need_admin(process_name_lower):
    return process_name_lower in NEED_ADMIN_PROCESSES

def is_protected(process_name_lower):
    return process_name_lower in PROTECTED_PROCESSES

def score_to_priority(score):
    if score >= 85:
        return 'high', PRIORITY_DISPLAY['high']
    elif score >= 70:
        return 'above_normal', PRIORITY_DISPLAY['above_normal']
    elif score >= 45:
        return 'normal', PRIORITY_DISPLAY['normal']
    elif score >= 25:
        return 'below_normal', PRIORITY_DISPLAY['below_normal']
    else:
        return 'idle', PRIORITY_DISPLAY['idle']

def get_priority_key(priority_value):
    for key, value in PRIORITY_LEVELS.items():
        if value == priority_value:
            return key
    return 'normal'

def calculate_priority_score(process, system_metrics, config):
    try:
        cpu_percent = process.cpu_percent(interval=None)
        if cpu_percent > 100:
            cpu_percent = 50
        
        memory_percent = process.memory_percent()
        
        try:
            memory_info = process.memory_info()
            memory_rss = memory_info.rss / (1024 ** 2)
            memory_vms = memory_info.vms / (1024 ** 2)
        except:
            memory_rss = 0
            memory_vms = 0
        
        try:
            io_counters = process.io_counters()
            io_read = io_counters.read_bytes / (1024 ** 2)
            io_write = io_counters.write_bytes / (1024 ** 2)
        except:
            io_read = 0
            io_write = 0
        
        try:
            num_threads = process.num_threads()
        except:
            num_threads = 1
        
        try:
            create_time = process.create_time()
            uptime = time.time() - create_time
        except:
            uptime = 3600
        
        try:
            status = process.status()
        except:
            status = 'running'
        
        process_name = process.name().lower()
        proc_type = classify_process(process_name)
        
        exe_path = ""
        try:
            exe_path = process.exe()
        except:
            pass
        
        window_title = get_process_window_title(process.pid)
        company_name = get_process_company_name(exe_path) if exe_path else None
        
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
            'num_threads': num_threads,
            **details
        }
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return None, None, None, None, None

def cross_analysis_scoring(metrics, system_metrics, config):
    scores = {}
    details = {}
    
    scores['category_base'] = {
        'gaming': 75,
        'design': 65,
        'ai': 65,
        'video': 55,
        'development': 55,
        'browser': 45,
        'productivity': 45,
        'security': 40,
        'utility': 40,
        'system': 50,
        'unknown': 45
    }[metrics['category']]
    
    cpu_score = min(25, metrics['cpu'] * 0.5)
    scores['cpu'] = cpu_score
    
    memory_score = min(20, metrics['memory'] * 0.4)
    scores['memory'] = memory_score
    
    thread_score = min(10, min(metrics['threads'], 50) * 0.2)
    scores['threads'] = thread_score
    
    io_score = min(8, metrics['io'])
    scores['io'] = io_score
    
    uptime_score = 0
    if metrics['uptime'] < 300:
        uptime_score = 8
    elif metrics['uptime'] < 1800:
        uptime_score = 4
    elif metrics['uptime'] > 86400:
        uptime_score = -5
    scores['uptime'] = uptime_score
    
    status_score = 0
    if metrics['status'] == 'running':
        status_score = 5
    elif metrics['status'] == 'sleeping':
        status_score = -3
    scores['status'] = status_score
    
    type_bonus = {
        'system': 5,
        'user_app': 8,
        'service': 2,
        'background': -5,
        'unknown': 0
    }[metrics['proc_type']]
    scores['type'] = type_bonus
    
    base_score = sum(scores.values())
    
    cross_factors = []
    
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
            except:
                return {'name': process_name, 'pid': process.pid, 'status': 'protected', 
                        'reason': '系统保护进程', 'current_priority': '未知'}
        
        if need_admin(process_name_lower) and not admin_mode:
            return {'name': process_name, 'pid': process.pid, 'status': 'need_admin', 'reason': '需要管理员权限'}
        
        score, cpu_percent, memory_percent, proc_type, details = calculate_priority_score(process, system_metrics, config)
        
        if score is None:
            return {'name': process_name, 'pid': process.pid, 'status': 'access_denied', 'reason': '无法读取进程信息'}
        
        priority_key, priority_name = score_to_priority(score)
        
        try:
            old_priority = process.nice()
        except psutil.AccessDenied:
            return {'name': process_name, 'pid': process.pid, 'status': 'access_denied', 'reason': '无法读取优先级'}
        
        new_priority_value = PRIORITY_LEVELS[priority_key]
        
        if old_priority != new_priority_value:
            try:
                process.nice(new_priority_value)
            except psutil.AccessDenied:
                return {'name': process_name, 'pid': process.pid, 'status': 'access_denied', 'reason': '无法设置优先级'}
        
        result = {
            'name': process_name,
            'pid': process.pid,
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'proc_type': proc_type,
            'score': round(score, 1),
            'old_priority': PRIORITY_DISPLAY.get(get_priority_key(old_priority), '未知'),
            'new_priority': priority_name,
            'status': 'success'
        }
        
        if details:
            result.update(details)
        
        return result
    except psutil.NoSuchProcess:
        return {'name': 'unknown', 'pid': 0, 'status': 'no_such_process', 'reason': '进程已终止'}
    except psutil.AccessDenied:
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

def worker(queue, system_metrics, admin_mode, config, results, lock):
    while True:
        proc = queue.get()
        if proc is None:
            break
        try:
            result = analyze_process(proc, system_metrics, admin_mode, config)
            with lock:
                results.append(result)
        except:
            pass
        queue.task_done()

def parallel_analyze(processes, system_metrics, admin_mode, config):
    queue = Queue()
    results = []
    lock = threading.Lock()
    
    for proc in processes:
        queue.put(proc)
    
    for _ in range(THREAD_COUNT):
        queue.put(None)
    
    threads = []
    for _ in range(THREAD_COUNT):
        t = threading.Thread(target=worker, args=(queue, system_metrics, admin_mode, config, results, lock))
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join()
    
    return results

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
        print("6. 返回主菜单")
        
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
                cleanup_windows_apps()
            
            else:
                print("无效选择")

        except KeyboardInterrupt:
            print("\n已取消操作")
            return
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

def get_installed_apps():
    import subprocess
    try:
        result = subprocess.run(
            ['powershell', '-Command', 'Get-AppxPackage | Select-Object Name, PackageFullName, InstallLocation | ConvertTo-Json'],
            capture_output=True, text=True, timeout=30
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
            capture_output=True, text=True, timeout=30
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
            capture_output=True, text=True, timeout=30
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
    print("   • 3D Builder、新闻、体育、财经等")
    print("   • 游戏合集、提示、反馈中心等")
    print("\n❌  保护列表: 这些应用不建议卸载")
    print("   • 照片、相机、邮件、日历等")
    print("   • 应用商店、浏览器、计算器等")
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
                print(f"  • {name}")
            
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
                print(f"  • {safe_apps[idx][0]}")
            
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
        print("6. Windows应用清理器")
        print("7. 返回主菜单")
        
        try:
            choice = input("\n请输入选择 (1-7): ")
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
                cleanup_windows_apps()
            
            elif choice == '7':
                return
            
            else:
                print("无效选择")
        
        except KeyboardInterrupt:
            print("\n已取消操作")
            return
        except ValueError:
            print("输入无效")

def main():
    start_time = time.time()
    log_entries = []
    config = load_config()
    
    admin_mode = is_admin()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--config':
            show_gpu_config_menu(config)
            return
    
    print("=" * 90)
    print("          AI 智能进程优先级分配 v7.0")
    print("=" * 90)
    
    log_entries.append(f"版本: v7.0")
    log_entries.append(f"管理员模式: {admin_mode}")
    
    if admin_mode:
        print("[管理员模式] 已获得管理员权限")
    else:
        print("[普通模式] 部分系统进程需要管理员权限")
    
    print(f"\n[提示] 使用 python {sys.argv[0]} --config 进入配置管理")
    
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
                print(f"    • {info['brand_name']}: {info['count']} 张")
        
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
        print("│ • 游戏应用: 英雄联盟、CSGO、GTA、赛博朋克等                        │")
        print("│ • 影视剪辑: Premiere、After Effects、达芬奇Resolve                  │")
        print("│ • 图像设计: Photoshop、Illustrator、Blender、Cinema 4D             │")
        print("│ • AI计算: Stable Diffusion、TensorFlow、PyTorch                   │")
        print("│ • 视频播放: 4K/8K高清视频解码、HDR内容                            │")
        print("└─────────────────────────────────────────────────────────────────────┘")
        print("")
        print("┌─────────────────────────────────────────────────────────────────────┐")
        print("│ ⚡ 集成显卡 (Intel UHD/HD) → 适合日常办公和轻量级应用               │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        print("│ • 浏览器: Chrome、Edge、Firefox等                                  │")
        print("│ • 办公软件: Word、Excel、PowerPoint、Outlook                       │")
        print("│ • 聊天工具: Teams、Discord、微信、QQ                               │")
        print("│ • 安全软件: 杀毒软件、防火墙                                       │")
        print("│ • 系统进程: 资源管理器、桌面窗口管理器等                            │")
        print("└─────────────────────────────────────────────────────────────────────┘")
        print("")
        print("[🌟 品牌优先推荐]")
        print("  • 游戏/AI/专业渲染 → NVIDIA (CUDA加速性能最佳)")
        print("  • 视频编码/AV1解码 → AMD (视频处理能力强)")
        print("  • 轻度创作/办公 → Intel Arc (平衡性能与功耗)")
        print("  • 日常办公/省电 → Intel UHD (功耗最低，续航最长)")
        print("")
        print("[💬 简单来说]")
        print("  如果你做影视剪辑、做图、玩游戏 → 用 NVIDIA/AMD/Intel Arc 独立显卡")
        print("  如果你只是上网、办公 → 用 Intel UHD 集成显卡就够了")
    
    if write_log(log_entries):
        print(f"\n[日志已保存] {LOG_FILE}")
    else:
        print("\n[日志保存失败]")
    
    if need_admin_count > 0 and not admin_mode:
        print("\n[提示] 部分系统进程需要管理员权限")
        print("请右键点击PowerShell -> 以管理员身份运行")
    
    print("=" * 90)

if __name__ == "__main__":
    main()