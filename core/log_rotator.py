import os
import gzip
import shutil
from datetime import datetime
from pathlib import Path


class LogRotator:
    MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_LOG_FILES = 5
    LOG_DIR = 'logs'
    
    def __init__(self, log_file='process_priority_log.txt'):
        self.log_file = log_file
        self.log_path = Path(self.LOG_DIR) / log_file
        self._ensure_dir()
    
    def _ensure_dir(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def should_rotate(self) -> bool:
        if not self.log_path.exists():
            return False
        return self.log_path.stat().st_size >= self.MAX_LOG_SIZE
    
    def rotate(self):
        """日志轮转：压缩旧日志，创建新日志"""
        if not self.should_rotate():
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        rotated_name = f"{self.log_path.stem}_{timestamp}.txt.gz"
        rotated_path = self.log_path.parent / rotated_name
        
        # 压缩旧日志
        with open(self.log_path, 'rb') as f_in:
            with gzip.open(rotated_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # 清空当前日志
        self.log_path.unlink()
        self.log_path.touch()
        
        # 清理过期日志
        self._clean_old_logs()
    
    def _clean_old_logs(self):
        """删除最旧的日志文件，保持 MAX_LOG_FILES 个"""
        logs = sorted(self.log_path.parent.glob(f"{self.log_path.stem}_*.txt.gz"))
        for old_log in logs[:-self.MAX_LOG_FILES]:
            old_log.unlink()
    
    def get_log_size(self) -> int:
        return self.log_path.stat().st_size if self.log_path.exists() else 0
