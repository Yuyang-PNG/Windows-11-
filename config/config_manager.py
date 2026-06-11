import os
import yaml
import json
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from config.config_validator import ConfigValidator


class ConfigManager:
    def __init__(self, config_dir: str = 'config'):
        self.config_dir = config_dir
        self.app_categories_path = os.path.join(config_dir, 'app_categories.yaml')
        self.scoring_rules_path = os.path.join(config_dir, 'scoring_rules.yaml')
        self.cross_factors_path = os.path.join(config_dir, 'cross_factors.yaml')
        self.gpu_config_path = os.path.join(config_dir, 'gpu_config.json')
        self.priority_rules_path = os.path.join(config_dir, 'priority_rules.json')
        
        self._config_cache: Dict[str, Dict[str, Any]] = {}
        self._last_load_time: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._validation_errors: Dict[str, List[str]] = {}
        
        self._ensure_dir()
        self.load_all_configs()
    
    def _ensure_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
    
    def load_yaml_config(self, filepath: str, config_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if config_type and config:
                is_valid, errors = ConfigValidator.validate(config_type, config)
                if not is_valid:
                    self._validation_errors[config_type] = errors
                    print(f"配置校验失败 {filepath}: {errors}")
                    config = ConfigValidator.fix_config(config_type, config)
                    print(f"已自动修复配置")
            
            return config
        except Exception as e:
            print(f"加载YAML配置失败 {filepath}: {e}")
            return None
    
    def save_yaml_config(self, filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            return True
        except Exception as e:
            print(f"保存YAML配置失败 {filepath}: {e}")
            return False
    
    def load_json_config(self, filepath):
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载JSON配置失败 {filepath}: {e}")
            return None
    
    def save_json_config(self, filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存JSON配置失败 {filepath}: {e}")
            return False
    
    def load_all_configs(self) -> None:
        with self._lock:
            self._config_cache['app_categories'] = self.load_yaml_config(self.app_categories_path, 'app_categories') or self._get_default_app_categories()
            self._config_cache['scoring_rules'] = self.load_yaml_config(self.scoring_rules_path, 'scoring_rules') or self._get_default_scoring_rules()
            self._config_cache['cross_factors'] = self.load_yaml_config(self.cross_factors_path, 'cross_factors') or self._get_default_cross_factors()
            self._config_cache['gpu_settings'] = self.load_json_config(self.gpu_config_path) or {'gpu_settings': {}, 'priority_rules': {}}
            self._config_cache['priority_rules'] = self.load_json_config(self.priority_rules_path) or {}
            
            for key in self._config_cache:
                self._last_load_time[key] = time.time()
                
    def get_validation_errors(self, config_type: Optional[str] = None) -> Dict[str, List[str]]:
        """获取配置校验错误"""
        if config_type:
            return {config_type: self._validation_errors.get(config_type, [])}
        return self._validation_errors
    
    def validate_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """校验所有配置文件并返回报告"""
        reports = {}
        configs = [
            ('app_categories', self.get_app_categories()),
            ('scoring_rules', self.get_scoring_rules()),
            ('cross_factors', self.get_cross_factors())
        ]
        
        for config_type, config in configs:
            reports[config_type] = ConfigValidator.get_validation_report(config_type, config)
        
        return reports
    
    def upgrade_config_version(self) -> bool:
        """升级配置文件版本"""
        try:
            updated = False
            
            for config_type in ['app_categories', 'scoring_rules', 'cross_factors']:
                config = self._config_cache.get(config_type)
                if config and config.get('version') != ConfigValidator.CURRENT_VERSION:
                    fixed = ConfigValidator.fix_config(config_type, config)
                    self._config_cache[config_type] = fixed
                    filepath = self._get_config_path(config_type)
                    if filepath.endswith('.yaml'):
                        self.save_yaml_config(filepath, fixed)
                    updated = True
            
            if updated:
                self.load_all_configs()
            
            return updated
        except Exception as e:
            print(f"配置版本升级失败: {e}")
            return False
    
    def _get_default_app_categories(self) -> Dict[str, Any]:
        return {
            'version': ConfigValidator.CURRENT_VERSION,
            'description': '默认应用分类配置',
            'categories': {
                'gaming': {
                    'description': '游戏应用',
                    'suggested_gpu': 'discrete',
                    'priority': 'high',
                    'base_score': 70,
                    'bonus_score': 10,
                    'keywords': ['game', 'gaming', 'steam'],
                    'paths': [],
                    'window_titles': [],
                    'company_keywords': []
                },
                'unknown': {
                    'description': '未知应用',
                    'suggested_gpu': 'auto',
                    'priority': 'medium',
                    'base_score': 50,
                    'bonus_score': 0,
                    'keywords': [],
                    'paths': [],
                    'window_titles': [],
                    'company_keywords': []
                }
            },
            'priority_scoring': {
                'cpu_weight': 25,
                'memory_weight': 20,
                'type_weight': 20,
                'threads_weight': 10,
                'io_weight': 10,
                'system_load_weight': 10,
                'age_weight': 5
            },
            'process_types': {
                'user_app': {'name': '用户应用', 'score_bonus': 12},
                'system': {'name': '系统进程', 'score_bonus': 8},
                'service': {'name': '服务进程', 'score_bonus': 3},
                'background': {'name': '后台进程', 'score_bonus': -5}
            }
        }
    
    def _get_default_scoring_rules(self) -> Dict[str, Any]:
        return {
            'version': ConfigValidator.CURRENT_VERSION,
            'weights': {
                'cpu_weight': 25,
                'memory_weight': 20,
                'threads_weight': 10,
                'io_weight': 8,
                'uptime_weight': 7,
                'status_weight': 5,
                'type_weight': 15
            },
            'category_base_scores': {
                'gaming': 75, 'video': 55, 'browser': 45, 'productivity': 45,
                'development': 55, 'design': 65, 'ai': 65, 'system': 50,
                'security': 40, 'utility': 40, 'communication': 42,
                'music': 42, 'cloud': 40, 'unknown': 45
            },
            'process_type_bonus': {
                'user_app': 8, 'system': 5, 'service': 2, 'background': -5, 'unknown': 0
            },
            'uptime_rules': [
                {'condition': '< 300', 'score': 8},
                {'condition': '< 1800', 'score': 4},
                {'condition': '> 86400', 'score': -5}
            ],
            'status_scores': {
                'running': 5, 'sleeping': -3, 'waiting': -2, 'stopped': -10, 'zombie': -15
            }
        }
    
    def _get_default_cross_factors(self) -> Dict[str, Any]:
        return {
            'version': ConfigValidator.CURRENT_VERSION,
            'factors': [],
            'system_adjustments': [
                {'condition': {'field': 'system_cpu', 'operator': '>', 'value': 80}, 'adjustment': -8},
                {'condition': {'field': 'system_memory', 'operator': '>', 'value': 90}, 'adjustment': -5}
            ]
        }
    
    def get_app_categories(self, reload=False):
        with self._lock:
            if reload or self._need_reload('app_categories'):
                self._config_cache['app_categories'] = self.load_yaml_config(self.app_categories_path) or self._get_default_app_categories()
                self._last_load_time['app_categories'] = time.time()
            return self._config_cache['app_categories']
    
    def get_scoring_rules(self, reload=False):
        with self._lock:
            if reload or self._need_reload('scoring_rules'):
                self._config_cache['scoring_rules'] = self.load_yaml_config(self.scoring_rules_path) or self._get_default_scoring_rules()
                self._last_load_time['scoring_rules'] = time.time()
            return self._config_cache['scoring_rules']
    
    def get_cross_factors(self, reload=False):
        with self._lock:
            if reload or self._need_reload('cross_factors'):
                self._config_cache['cross_factors'] = self.load_yaml_config(self.cross_factors_path) or self._get_default_cross_factors()
                self._last_load_time['cross_factors'] = time.time()
            return self._config_cache['cross_factors']
    
    def get_gpu_settings(self, reload=False):
        with self._lock:
            if reload or self._need_reload('gpu_settings'):
                self._config_cache['gpu_settings'] = self.load_json_config(self.gpu_config_path) or {'gpu_settings': {}, 'priority_rules': {}}
                self._last_load_time['gpu_settings'] = time.time()
            return self._config_cache['gpu_settings']
    
    def get_priority_rules(self, reload=False):
        with self._lock:
            if reload or self._need_reload('priority_rules'):
                self._config_cache['priority_rules'] = self.load_json_config(self.priority_rules_path) or {}
                self._last_load_time['priority_rules'] = time.time()
            return self._config_cache['priority_rules']
    
    def _need_reload(self, config_key):
        if config_key not in self._last_load_time:
            return True
        
        filepath = self._get_config_path(config_key)
        if not os.path.exists(filepath):
            return False
        
        file_mtime = os.path.getmtime(filepath)
        return file_mtime > self._last_load_time.get(config_key, 0)
    
    def _get_config_path(self, config_key):
        paths = {
            'app_categories': self.app_categories_path,
            'scoring_rules': self.scoring_rules_path,
            'cross_factors': self.cross_factors_path,
            'gpu_settings': self.gpu_config_path,
            'priority_rules': self.priority_rules_path
        }
        return paths.get(config_key, '')
    
    def save_gpu_settings(self, settings):
        with self._lock:
            self._config_cache['gpu_settings'] = settings
            success = self.save_json_config(self.gpu_config_path, settings)
            if success:
                self._last_load_time['gpu_settings'] = time.time()
            return success
    
    def save_priority_rules(self, rules):
        with self._lock:
            self._config_cache['priority_rules'] = rules
            success = self.save_json_config(self.priority_rules_path, rules)
            if success:
                self._last_load_time['priority_rules'] = time.time()
            return success
    
    def update_app_categories(self, categories):
        with self._lock:
            config = self.get_app_categories()
            config['categories'].update(categories)
            config['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            success = self.save_yaml_config(self.app_categories_path, config)
            if success:
                self._config_cache['app_categories'] = config
                self._last_load_time['app_categories'] = time.time()
            return success
    
    def add_custom_category(self, category_id, category_data):
        with self._lock:
            config = self.get_app_categories()
            config['categories'][category_id] = category_data
            config['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            success = self.save_yaml_config(self.app_categories_path, config)
            if success:
                self._config_cache['app_categories'] = config
                self._last_load_time['app_categories'] = time.time()
            return success
    
    def export_config(self, export_path=None):
        if export_path is None:
            export_path = os.path.join(self.config_dir, f'config_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
        
        try:
            import zipfile
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(self.app_categories_path, 'app_categories.yaml')
                zf.write(self.scoring_rules_path, 'scoring_rules.yaml')
                zf.write(self.cross_factors_path, 'cross_factors.yaml')
                if os.path.exists(self.gpu_config_path):
                    zf.write(self.gpu_config_path, 'gpu_config.json')
                if os.path.exists(self.priority_rules_path):
                    zf.write(self.priority_rules_path, 'priority_rules.json')
            return export_path
        except Exception as e:
            print(f"导出配置失败: {e}")
            return None
    
    def import_config(self, import_path):
        try:
            import zipfile
            with zipfile.ZipFile(import_path, 'r') as zf:
                zf.extract('app_categories.yaml', self.config_dir)
                zf.extract('scoring_rules.yaml', self.config_dir)
                zf.extract('cross_factors.yaml', self.config_dir)
                if 'gpu_config.json' in zf.namelist():
                    zf.extract('gpu_config.json', self.config_dir)
                if 'priority_rules.json' in zf.namelist():
                    zf.extract('priority_rules.json', self.config_dir)
            
            self.load_all_configs()
            return True
        except Exception as e:
            print(f"导入配置失败: {e}")
            return False
    
    def reload_all(self):
        self.load_all_configs()
        return True
    
    def get_category_info(self, category_id):
        config = self.get_app_categories()
        return config['categories'].get(category_id, None)
    
    def get_all_category_ids(self):
        config = self.get_app_categories()
        return list(config['categories'].keys())
    
    def get_priority_scoring_weights(self):
        rules = self.get_scoring_rules()
        return rules.get('weights', self._get_default_scoring_rules()['weights'])
    
    def get_category_base_score(self, category):
        rules = self.get_scoring_rules()
        return rules.get('category_base_scores', {}).get(category, 45)
    
    def get_process_type_bonus(self, process_type):
        rules = self.get_scoring_rules()
        return rules.get('process_type_bonus', {}).get(process_type, 0)
    
    def get_status_score(self, status):
        rules = self.get_scoring_rules()
        return rules.get('status_scores', {}).get(status, 0)
    
    def calculate_uptime_score(self, uptime_seconds):
        rules = self.get_scoring_rules()
        uptime_rules = rules.get('uptime_rules', [])
        
        for rule in uptime_rules:
            condition = rule['condition']
            score = rule['score']
            
            if condition.startswith('< '):
                threshold = float(condition.split()[1])
                if uptime_seconds < threshold:
                    return score
            elif condition.startswith('> '):
                threshold = float(condition.split()[1])
                if uptime_seconds > threshold:
                    return score
        
        return 0