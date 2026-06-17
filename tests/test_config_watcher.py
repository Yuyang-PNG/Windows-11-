import os
import time
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

class TestConfigWatcher(unittest.TestCase):
    """配置监视器测试"""
    
    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, 'test_config.yaml')
        
        # 创建测试配置文件
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write('version: 1\ntest: true\n')
    
    def tearDown(self):
        """测试后清理"""
        # 停止监视器
        if hasattr(self, 'watcher') and self.watcher:
            self.watcher.stop()
        
        # 删除测试文件
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        os.rmdir(self.test_dir)
    
    def test_config_watcher_import(self):
        """测试 ConfigWatcher 导入"""
        from core.config_watcher import ConfigWatcher
        self.assertIsNotNone(ConfigWatcher)
    
    def test_config_watcher_initialization(self):
        """测试 ConfigWatcher 初始化"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        
        self.assertIsNone(watcher.config_manager)
        self.assertEqual(watcher.watch_files, {})
        self.assertEqual(watcher.callbacks, [])
        self.assertFalse(watcher.running)
    
    def test_add_watch(self):
        """测试添加监视文件"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        watcher.add_watch(self.test_file)
        
        self.assertIn(self.test_file, watcher.watch_files)
        self.assertGreater(watcher.watch_files[self.test_file], 0)
    
    def test_add_watch_nonexistent_file(self):
        """测试添加不存在的文件"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        nonexistent = os.path.join(self.test_dir, 'nonexistent.yaml')
        watcher.add_watch(nonexistent)
        
        self.assertIn(nonexistent, watcher.watch_files)
        self.assertEqual(watcher.watch_files[nonexistent], 0)
    
    def test_on_config_change_callback(self):
        """测试配置变更回调"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        
        callback_called = {'called': False, 'filepath': None}
        
        def test_callback(filepath):
            callback_called['called'] = True
            callback_called['filepath'] = filepath
        
        watcher.on_config_change(test_callback)
        self.assertEqual(len(watcher.callbacks), 1)
    
    def test_get_watch_status(self):
        """测试获取监视状态"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        watcher.add_watch(self.test_file)
        
        status = watcher.get_watch_status()
        
        self.assertFalse(status['running'])
        self.assertEqual(status['file_count'], 1)
        self.assertIn(self.test_file, status['watching_files'])
    
    def test_start_stop(self):
        """测试启动和停止"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        
        self.assertFalse(watcher.running)
        
        watcher.start()
        self.assertTrue(watcher.running)
        
        watcher.stop()
        self.assertFalse(watcher.running)
    
    def test_set_config_manager(self):
        """测试设置配置管理器"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        
        mock_manager = MagicMock()
        watcher.set_config_manager(mock_manager)
        
        self.assertEqual(watcher.config_manager, mock_manager)
    
    def test_watch_loop_detects_change(self):
        """测试监视循环检测变更"""
        from core.config_watcher import ConfigWatcher
        
        mock_manager = MagicMock()
        watcher = ConfigWatcher(mock_manager)
        watcher.add_watch(self.test_file)
        
        change_detected = {'detected': False}
        
        def on_change(filepath):
            change_detected['detected'] = True
        
        watcher.on_config_change(on_change)
        
        # 启动监视
        watcher.start()
        time.sleep(0.5)
        
        # 修改文件
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write('version: 2\ntest: false\nchanged: true\n')
        
        # 等待检测
        time.sleep(2)
        
        watcher.stop()
        
        self.assertTrue(change_detected['detected'])
    
    def test_check_now_no_change(self):
        """测试立即检查无变更"""
        from core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        watcher.add_watch(self.test_file)
        
        initial_mtime = watcher.watch_files[self.test_file]
        
        watcher.check_now()
        
        self.assertEqual(watcher.watch_files[self.test_file], initial_mtime)
    
    def test_multiple_watch_files(self):
        """测试监视多个文件"""
        from core.config_watcher import ConfigWatcher
        
        file1 = os.path.join(self.test_dir, 'config1.yaml')
        file2 = os.path.join(self.test_dir, 'config2.yaml')
        
        with open(file1, 'w') as f:
            f.write('config: 1')
        with open(file2, 'w') as f:
            f.write('config: 2')
        
        watcher = ConfigWatcher()
        watcher.add_watch(file1)
        watcher.add_watch(file2)
        
        self.assertEqual(len(watcher.watch_files), 2)
        
        os.remove(file1)
        os.remove(file2)


class TestConfigWatcherIntegration(unittest.TestCase):
    """配置监视器集成测试"""
    
    def test_with_config_manager(self):
        """测试与配置管理器集成"""
        from core.config_watcher import ConfigWatcher
        
        with patch('config.config_manager.ConfigManager') as MockConfigManager:
            mock_manager = MockConfigManager.return_value
            mock_manager.get_app_categories = MagicMock(return_value={'categories': {}})
            mock_manager.get_scoring_rules = MagicMock(return_value={'weights': {}})
            
            watcher = ConfigWatcher(mock_manager)
            watcher.set_config_manager(mock_manager)
            
            self.assertIsNotNone(watcher.config_manager)


if __name__ == '__main__':
    unittest.main()