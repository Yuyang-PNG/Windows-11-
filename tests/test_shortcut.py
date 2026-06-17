"""快捷键模块测试"""
import unittest
from core.shortcut import GlobalShortcutManager


class TestGlobalShortcutManager(unittest.TestCase):
    """GlobalShortcutManager 测试类"""
    
    def test_init(self):
        """测试初始化"""
        manager = GlobalShortcutManager()
        self.assertIsNotNone(manager)
        self.assertEqual(manager.enabled, True)
        self.assertEqual(len(manager.registered_shortcuts), 0)
    
    def test_default_shortcuts_exist(self):
        """测试默认快捷键配置存在"""
        defaults = GlobalShortcutManager.DEFAULT_SHORTCUTS
        self.assertIn('ctrl+shift+o', defaults)
        self.assertIn('ctrl+shift+s', defaults)
        self.assertIn('ctrl+shift+g', defaults)
        self.assertIn('ctrl+shift+r', defaults)
        self.assertIn('ctrl+shift+q', defaults)
    
    def test_register_without_keyboard(self):
        """测试无keyboard库时的注册"""
        manager = GlobalShortcutManager()
        # 模拟没有keyboard库的情况
        manager._keyboard = None
        
        result = manager.register('ctrl+shift+t', lambda: None, "测试")
        self.assertFalse(result)
    
    def test_get_registered_shortcuts(self):
        """测试获取已注册快捷键列表"""
        manager = GlobalShortcutManager()
        shortcuts = manager.get_registered_shortcuts()
        self.assertIsInstance(shortcuts, list)
        self.assertEqual(len(shortcuts), 0)
    
    def test_set_enabled(self):
        """测试启用/禁用快捷键"""
        manager = GlobalShortcutManager()
        
        manager.set_enabled(False)
        self.assertFalse(manager.is_enabled())
        
        manager.set_enabled(True)
        self.assertTrue(manager.is_enabled())
    
    def test_unregister_all(self):
        """测试注销所有快捷键"""
        manager = GlobalShortcutManager()
        # 即使没有keyboard库，unregister_all也不应该报错
        manager.unregister_all()
        self.assertEqual(len(manager.registered_shortcuts), 0)


if __name__ == '__main__':
    unittest.main()
