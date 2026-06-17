import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.notification import NotificationManager, get_notification_manager


class TestNotificationManager(unittest.TestCase):
    """NotificationManager 测试类"""
    
    def setUp(self):
        """创建通知管理器实例"""
        self.notification_manager = NotificationManager()
    
    def test_initial_state(self):
        """测试初始状态"""
        self.assertTrue(self.notification_manager.is_enabled())
        self.assertTrue(self.notification_manager.enabled)
    
    def test_set_enabled(self):
        """测试设置启用状态"""
        self.notification_manager.set_enabled(False)
        self.assertFalse(self.notification_manager.is_enabled())
        
        self.notification_manager.set_enabled(True)
        self.assertTrue(self.notification_manager.is_enabled())
    
    def test_notify_disabled(self):
        """测试通知被禁用时不输出"""
        self.notification_manager.set_enabled(False)
        # 不应抛出异常
        self.notification_manager.notify("Test", "Message", "info")
    
    def test_notify_enabled(self):
        """测试通知启用时可正常调用"""
        self.notification_manager.set_enabled(True)
        # 不应抛出异常
        self.notification_manager.notify("Test", "Message", "info")
    
    def test_game_detected(self):
        """测试游戏检测通知"""
        self.notification_manager.set_enabled(True)
        # 不应抛出异常
        self.notification_manager.game_detected("GTA5.exe")
    
    def test_optimization_complete(self):
        """测试优化完成通知"""
        self.notification_manager.set_enabled(True)
        # 不应抛出异常
        self.notification_manager.optimization_complete(10, 2)
        self.notification_manager.optimization_complete(5)
    
    def test_anomaly_detected(self):
        """测试异常检测通知"""
        self.notification_manager.set_enabled(True)
        # 不应抛出异常
        self.notification_manager.anomaly_detected("chrome.exe", "High CPU usage")
    
    def test_priority_restored(self):
        """测试优先级恢复通知"""
        self.notification_manager.set_enabled(True)
        # 不应抛出异常
        self.notification_manager.priority_restored("chrome.exe")
    
    def test_error_occurred(self):
        """测试错误通知"""
        self.notification_manager.set_enabled(True)
        # 不应抛出异常
        self.notification_manager.error_occurred("Something went wrong")
    
    def test_get_notification_manager_singleton(self):
        """测试全局通知管理器实例"""
        manager1 = get_notification_manager()
        manager2 = get_notification_manager()
        self.assertIs(manager1, manager2)


class TestNotificationManagerEdgeCases(unittest.TestCase):
    """NotificationManager 边界情况测试"""
    
    def setUp(self):
        self.notification_manager = NotificationManager()
    
    def test_empty_game_name(self):
        """测试空游戏名"""
        self.notification_manager.game_detected("")
    
    def test_empty_process_name(self):
        """测试空进程名"""
        self.notification_manager.anomaly_detected("", "reason")
    
    def test_priority_restored_empty(self):
        """测试空进程名恢复"""
        self.notification_manager.priority_restored("")
    
    def test_optimization_complete_zero(self):
        """测试优化数量为0"""
        self.notification_manager.optimization_complete(0, 0)
    
    def test_optimization_complete_zero_denied(self):
        """测试优化数量为0但有拒绝数"""
        self.notification_manager.optimization_complete(0, 5)


if __name__ == '__main__':
    unittest.main()
