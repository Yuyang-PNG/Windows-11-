import os
import gzip
import shutil
import tempfile
import unittest
import time
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_rotator import LogRotator


class TestLogRotator(unittest.TestCase):
    """LogRotator 测试类"""
    
    def setUp(self):
        """创建临时日志目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)
    
    def tearDown(self):
        """清理临时目录"""
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init_creates_log_dir(self):
        """测试初始化时创建日志目录"""
        rotator = LogRotator('test_log.txt')
        self.assertTrue(rotator.log_path.parent.exists())
        self.assertEqual(rotator.log_path.parent.name, 'logs')
    
    def test_should_rotate_returns_false_for_new_file(self):
        """测试新文件不需要轮转"""
        rotator = LogRotator('test_log.txt')
        self.assertFalse(rotator.should_rotate())
    
    def test_should_rotate_returns_false_when_too_small(self):
        """测试文件小于阈值时不轮转"""
        rotator = LogRotator('test_log.txt')
        rotator.log_path.write_text('small content')
        self.assertFalse(rotator.should_rotate())
    
    def test_should_rotate_returns_true_when_large_enough(self):
        """测试文件达到阈值时需要轮转"""
        rotator = LogRotator('test_log.txt')
        # 写入大于 5MB 的内容
        large_content = 'x' * (5 * 1024 * 1024 + 1)
        rotator.log_path.write_text(large_content)
        self.assertTrue(rotator.should_rotate())
    
    def test_rotate_compresses_old_log(self):
        """测试轮转时压缩旧日志"""
        rotator = LogRotator('test_log.txt')
        # 先写入大于阈值的内容使 should_rotate 返回 True
        large_content = 'x' * (5 * 1024 * 1024 + 1)
        rotator.log_path.write_text(large_content)
        
        rotator.rotate()
        
        # 检查是否存在压缩的旧日志
        rotated_logs = list(rotator.log_path.parent.glob('test_log_*.txt.gz'))
        self.assertEqual(len(rotated_logs), 1)
        
        # 验证压缩内容正确
        with gzip.open(rotated_logs[0], 'rt') as f:
            self.assertEqual(f.read(), large_content)
        
        # 检查主日志文件已清空
        self.assertEqual(rotator.log_path.read_text(), '')
    
    def test_rotate_cleans_old_logs_beyond_max(self):
        """测试轮转时清理超过最大数量的旧日志"""
        rotator = LogRotator('test_log.txt')
        rotator.MAX_LOG_FILES = 2
        
        # 创建多个旧日志（每次都需要先写入大于阈值的内容）
        large_content = 'x' * (5 * 1024 * 1024 + 1)
        for i in range(4):
            rotator.log_path.write_text(large_content)  # 每次都重写确保大小足够
            rotator.rotate()
            time.sleep(1.1)  # 确保时间戳不同
        
        # 应该只保留 2 个
        rotated_logs = list(rotator.log_path.parent.glob('test_log_*.txt.gz'))
        self.assertEqual(len(rotated_logs), 2)
    
    def test_get_log_size(self):
        """测试获取日志大小"""
        rotator = LogRotator('test_log.txt')
        self.assertEqual(rotator.get_log_size(), 0)
        
        rotator.log_path.write_text('test content')
        self.assertEqual(rotator.get_log_size(), 12)
    
    def test_get_log_size_nonexistent(self):
        """测试获取不存在日志的大小"""
        rotator = LogRotator('nonexistent.txt')
        self.assertEqual(rotator.get_log_size(), 0)
    
    def test_custom_log_dir(self):
        """测试自定义日志目录"""
        rotator = LogRotator('my_log.txt')
        self.assertEqual(rotator.log_path.parent.name, 'logs')
        self.assertEqual(rotator.log_path.name, 'my_log.txt')


if __name__ == '__main__':
    unittest.main()
