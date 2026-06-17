import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, Optional, List

class PreferenceLearner:
    PREFERENCES_FILE = 'config/user_preferences.json'
    
    def __init__(self):
        self.preferences: Dict[str, any] = {}
        self.manual_adjustments: Dict[str, List] = defaultdict(list)
        self.learning_enabled = True
        self._load()
    
    def _load(self):
        if os.path.exists(self.PREFERENCES_FILE):
            try:
                with open(self.PREFERENCES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.preferences = data.get('preferences', {})
                    self.manual_adjustments = defaultdict(list, data.get('adjustments', {}))
                    self.learning_enabled = data.get('learning_enabled', True)
            except Exception as e:
                print(f"加载用户偏好失败: {e}")
                self.preferences = {}
                self.manual_adjustments = defaultdict(list)
    
    def save(self):
        config_dir = os.path.dirname(self.PREFERENCES_FILE)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        with open(self.PREFERENCES_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'preferences': self.preferences,
                'adjustments': dict(self.manual_adjustments),
                'learning_enabled': self.learning_enabled,
                'updated_at': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
    
    def record_manual_adjustment(self, process_name: str, old_priority: str, new_priority: str):
        """记录用户手动调整"""
        self.manual_adjustments[process_name].append({
            'timestamp': datetime.now().isoformat(),
            'from': old_priority,
            'to': new_priority
        })
        
        # 只保留最近100条
        if len(self.manual_adjustments[process_name]) > 100:
            self.manual_adjustments[process_name] = self.manual_adjustments[process_name][-100:]
        
        self.save()
    
    def get_preferred_priority(self, process_name: str) -> Optional[str]:
        """获取用户偏好的优先级"""
        adjustments = self.manual_adjustments.get(process_name, [])
        if not adjustments:
            return None
        
        # 统计用户最终选择的优先级
        priority_counts = defaultdict(int)
        for adj in adjustments[-20:]:  # 最近20次
            priority_counts[adj['to']] += 1
        
        if priority_counts:
            return max(priority_counts, key=priority_counts.get)
        return None
    
    def get_adjustment_count(self, process_name: str) -> int:
        """获取用户调整次数"""
        return len(self.manual_adjustments.get(process_name, []))
    
    def get_all_adjusted_processes(self) -> List[str]:
        """获取所有被用户调整过的进程"""
        return list(self.manual_adjustments.keys())
    
    def should_adjust_score(self, process_name: str, default_score: float, category: str) -> float:
        """根据用户偏好调整评分"""
        if not self.learning_enabled:
            return default_score
        
        preferred = self.get_preferred_priority(process_name)
        if preferred:
            # 用户有偏好，调整分数使其命中目标优先级
            adjustments = {
                'high': 15,
                'above_normal': 5,
                'normal': 0,
                'below_normal': -10,
                'idle': -20
            }
            return default_score + adjustments.get(preferred, 0)
        return default_score
    
    def clear_process_history(self, process_name: str):
        """清除某个进程的学习历史"""
        if process_name in self.manual_adjustments:
            del self.manual_adjustments[process_name]
            self.save()
    
    def set_learning_enabled(self, enabled: bool):
        """设置学习功能开关"""
        self.learning_enabled = enabled
        self.save()
    
    def get_confidence(self, process_name: str) -> float:
        """获取学习置信度"""
        count = self.get_adjustment_count(process_name)
        if count == 0:
            return 0.0
        elif count < 5:
            return 0.3
        elif count < 10:
            return 0.6
        elif count < 20:
            return 0.8
        else:
            return 0.95