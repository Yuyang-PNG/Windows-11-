import json
import os
from datetime import datetime
from typing import Dict, List, Optional

class PriorityRestoreManager:
    ORIGINAL_PRIORITY_FILE = 'config/original_priorities.json'
    
    def __init__(self):
        self.original_priorities: Dict[str, int] = {}
        self.blacklist: List[str] = []
        self._load()
    
    def _load(self):
        if os.path.exists(self.ORIGINAL_PRIORITY_FILE):
            with open(self.ORIGINAL_PRIORITY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.original_priorities = data.get('priorities', {})
                self.blacklist = data.get('blacklist', [])
    
    def save(self):
        os.makedirs('config', exist_ok=True)
        with open(self.ORIGINAL_PRIORITY_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'priorities': self.original_priorities,
                'blacklist': self.blacklist,
                'saved_at': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
    
    def record_original_priority(self, process_name: str, priority: int):
        """记录进程原始优先级"""
        if process_name not in self.original_priorities:
            self.original_priorities[process_name] = priority
            self.save()
    
    def add_to_blacklist(self, process_name: str):
        """添加到黑名单"""
        if process_name.lower() not in [x.lower() for x in self.blacklist]:
            self.blacklist.append(process_name)
            self.save()
    
    def remove_from_blacklist(self, process_name: str):
        """从黑名单移除"""
        self.blacklist = [x for x in self.blacklist if x.lower() != process_name.lower()]
        self.save()
    
    def is_blacklisted(self, process_name: str) -> bool:
        """检查是否在黑名单"""
        return process_name.lower() in [x.lower() for x in self.blacklist]
    
    def get_original_priority(self, process_name: str) -> Optional[int]:
        """获取进程原始优先级"""
        return self.original_priorities.get(process_name)
    
    def get_blacklist(self) -> List[str]:
        """获取黑名单"""
        return self.blacklist.copy()