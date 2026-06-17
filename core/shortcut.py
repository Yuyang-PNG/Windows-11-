import threading
import time
from typing import Callable, Dict, Optional, List

class GlobalShortcutManager:
    """全局快捷键管理器"""
    
    # 默认快捷键配置
    DEFAULT_SHORTCUTS = {
        'ctrl+shift+o': 'optimize_all',      # 立即优化所有进程
        'ctrl+shift+s': 'show_status',        # 显示状态
        'ctrl+shift+g': 'show_games',         # 显示游戏进程
        'ctrl+shift+r': 'restore_priorities', # 一键恢复
        'ctrl+shift+q': 'quit'                # 退出程序
    }
    
    def __init__(self):
        self.registered_shortcuts: Dict[str, Dict] = {}
        self.enabled = True
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._keyboard = None
        
        # 尝试导入keyboard库
        try:
            import keyboard
            self._keyboard = keyboard
        except ImportError:
            print("keyboard库不可用，快捷键功能禁用")
    
    def register(self, hotkey: str, callback: Callable, description: str = "") -> bool:
        """注册快捷键"""
        if not self._keyboard:
            print("keyboard库未安装，快捷键功能禁用")
            return False
        
        try:
            # 移除已存在的快捷键
            if hotkey in self.registered_shortcuts:
                self.unregister(hotkey)
            
            # 注册新快捷键
            self._keyboard.add_hotkey(hotkey, self._make_callback_wrapper(hotkey))
            
            self.registered_shortcuts[hotkey] = {
                'description': description,
                'hotkey': hotkey
            }
            self._callbacks[hotkey] = callback
            
            return True
        except Exception as e:
            print(f"注册快捷键失败 {hotkey}: {e}")
            return False
    
    def _make_callback_wrapper(self, hotkey: str):
        """创建回调包装器"""
        def wrapper():
            if self.enabled and hotkey in self._callbacks:
                try:
                    callback = self._callbacks[hotkey]
                    callback()
                except Exception as e:
                    print(f"快捷键回调执行失败 {hotkey}: {e}")
        return wrapper
    
    def unregister(self, hotkey: str) -> bool:
        """注销快捷键"""
        if hotkey not in self.registered_shortcuts:
            return False
        
        try:
            if self._keyboard:
                self._keyboard.remove_hotkey(hotkey)
            del self.registered_shortcuts[hotkey]
            if hotkey in self._callbacks:
                del self._callbacks[hotkey]
            return True
        except Exception as e:
            print(f"注销快捷键失败 {hotkey}: {e}")
            return False
    
    def unregister_all(self):
        """注销所有快捷键"""
        with self._lock:
            for hotkey in list(self.registered_shortcuts.keys()):
                self.unregister(hotkey)
    
    def get_registered_shortcuts(self) -> List[Dict]:
        """获取已注册的快捷键列表"""
        return [
            {'hotkey': k, 'description': v['description']}
            for k, v in self.registered_shortcuts.items()
        ]
    
    def set_enabled(self, enabled: bool):
        """设置快捷键功能开关"""
        self.enabled = enabled
    
    def is_enabled(self) -> bool:
        return self.enabled
    
    def __del__(self):
        self.unregister_all()
