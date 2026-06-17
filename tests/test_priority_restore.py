import os
import tempfile
import shutil
import unittest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.priority_restore import PriorityRestoreManager


class TestPriorityRestoreManager(unittest.TestCase):
    """PriorityRestoreManager 测试类"""
    
    def setUp(self):
        """创建临时配置目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)
        # 使用临时路径
        self.manager = PriorityRestoreManager()
        self.manager.ORIGINAL_PRIORITY_FILE = 'config/original_priorities.json'
    
    def tearDown(self):
        """清理临时目录"""
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_record_original_priority(self):
        """测试记录进程原始优先级"""
        self.manager.record_original_priority('chrome.exe', 32)
        self.assertEqual(self.manager.get_original_priority('chrome.exe'), 32)
    
    def test_record_original_priority_does_not_overwrite(self):
        """测试已记录的优先级不会被覆盖"""
        self.manager.record_original_priority('chrome.exe', 32)
        self.manager.record_original_priority('chrome.exe', 64)
        self.assertEqual(self.manager.get_original_priority('chrome.exe'), 32)
    
    def test_add_to_blacklist(self):
        """测试添加进程到黑名单"""
        self.manager.add_to_blacklist('chrome.exe')
        self.assertTrue(self.manager.is_blacklisted('chrome.exe'))
    
    def test_add_to_blacklist_case_insensitive(self):
        """测试黑名单大小写不敏感"""
        self.manager.add_to_blacklist('Chrome.exe')
        self.assertTrue(self.manager.is_blacklisted('chrome.exe'))
        self.assertTrue(self.manager.is_blacklisted('CHROME.EXE'))
    
    def test_add_to_blacklist_no_duplicate(self):
        """测试黑名单不会添加重复进程"""
        self.manager.add_to_blacklist('chrome.exe')
        self.manager.add_to_blacklist('Chrome.exe')
        blacklist = self.manager.get_blacklist()
        # 只有一个（去重后）
        lower_names = [x.lower() for x in blacklist]
        self.assertEqual(lower_names.count('chrome.exe'), 1)
    
    def test_remove_from_blacklist(self):
        """测试从黑名单移除进程"""
        self.manager.add_to_blacklist('chrome.exe')
        self.manager.remove_from_blacklist('chrome.exe')
        self.assertFalse(self.manager.is_blacklisted('chrome.exe'))
    
    def test_remove_from_blacklist_case_insensitive(self):
        """测试移除黑名单大小写不敏感"""
        self.manager.add_to_blacklist('Chrome.exe')
        self.manager.remove_from_blacklist('CHROME.EXE')
        self.assertFalse(self.manager.is_blacklisted('chrome.exe'))
    
    def test_get_blacklist(self):
        """测试获取黑名单副本"""
        self.manager.add_to_blacklist('chrome.exe')
        self.manager.add_to_blacklist('firefox.exe')
        blacklist = self.manager.get_blacklist()
        self.assertEqual(len(blacklist), 2)
        self.assertIn('chrome.exe', [x.lower() for x in blacklist])
        self.assertIn('firefox.exe', [x.lower() for x in blacklist])
    
    def test_get_blacklist_returns_copy(self):
        """测试get_blacklist返回副本，修改不影响原数据"""
        self.manager.add_to_blacklist('chrome.exe')
        blacklist = self.manager.get_blacklist()
        blacklist.append('test.exe')
        self.assertFalse(self.manager.is_blacklisted('test.exe'))
    
    def test_save_and_load(self):
        """测试保存和加载功能"""
        self.manager.record_original_priority('chrome.exe', 32)
        self.manager.add_to_blacklist('firefox.exe')
        
        # 创建新实例，应该能加载到数据
        new_manager = PriorityRestoreManager()
        new_manager.ORIGINAL_PRIORITY_FILE = 'config/original_priorities.json'
        
        self.assertEqual(new_manager.get_original_priority('chrome.exe'), 32)
        self.assertTrue(new_manager.is_blacklisted('firefox.exe'))


if __name__ == '__main__':
    unittest.main()