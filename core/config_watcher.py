import os
import threading
import time
from typing import Callable, List, Dict
from datetime import datetime

class ConfigWatcher:
    """配置文件监视器，用于检测配置变更并自动热更新"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.watch_files: Dict[str, float] = {}
        self.callbacks: List[Callable] = []
        self.running = False
        self.thread: threading.Thread = None
        self._lock = threading.Lock()
    
    def set_config_manager(self, config_manager):
        """设置配置管理器"""
        self.config_manager = config_manager
    
    def add_watch(self, filepath: str):
        """添加监视文件"""
        with self._lock:
            if os.path.exists(filepath):
                self.watch_files[filepath] = os.path.getmtime(filepath)
            else:
                self.watch_files[filepath] = 0
    
    def on_config_change(self, callback: Callable):
        """配置变更回调"""
        self.callbacks.append(callback)
    
    def start(self):
        """启动监视线程"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
        print("配置监视已启动")
    
    def stop(self):
        """停止监视"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print("配置监视已停止")
    
    def _watch_loop(self):
        """监视循环"""
        last_check_time = time.time()
        
        while self.running:
            try:
                time.sleep(1)  # 每秒检查一次
                
                with self._lock:
                    for filepath, last_mtime in list(self.watch_files.items()):
                        if not os.path.exists(filepath):
                            continue
                        
                        current_mtime = os.path.getmtime(filepath)
                        
                        # 检测到文件变更
                        if current_mtime > last_mtime:
                            print(f"配置变更检测: {filepath}")
                            self.watch_files[filepath] = current_mtime
                            
                            # 重新加载配置
                            if self.config_manager:
                                try:
                                    # 根据文件类型重新加载对应配置
                                    if 'app_categories' in filepath:
                                        self.config_manager.get_app_categories(reload=True)
                                    elif 'scoring_rules' in filepath:
                                        self.config_manager.get_scoring_rules(reload=True)
                                    elif 'cross_factors' in filepath:
                                        self.config_manager.get_cross_factors(reload=True)
                                    elif 'gpu_config' in filepath:
                                        self.config_manager.get_gpu_settings(reload=True)
                                    elif 'priority_rules' in filepath:
                                        self.config_manager.get_priority_rules(reload=True)
                                except Exception as e:
                                    print(f"配置重载失败: {e}")
                            
                            # 触发回调
                            for callback in self.callbacks:
                                try:
                                    callback(filepath)
                                except Exception as e:
                                    print(f"回调执行失败: {e}")
            except Exception as e:
                print(f"配置监视异常: {e}")
    
    def get_watch_status(self) -> Dict:
        """获取监视状态"""
        return {
            'running': self.running,
            'watching_files': list(self.watch_files.keys()),
            'file_count': len(self.watch_files)
        }
    
    def check_now(self):
        """立即检查所有配置文件"""
        for filepath in list(self.watch_files.keys()):
            if os.path.exists(filepath):
                current_mtime = os.path.getmtime(filepath)
                if filepath in self.watch_files:
                    if current_mtime > self.watch_files[filepath]:
                        print(f"立即检查发现变更: {filepath}")
                        self.watch_files[filepath] = current_mtime