import unittest
import os
import sys
import json
import tempfile
import shutil
from datetime import datetime

# 确保可以导入 preference_learner
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.preference_learner import PreferenceLearner


class TestPreferenceLearner(unittest.TestCase):
    """PreferenceLearner 测试类"""
    
    def setUp(self):
        """测试前设置"""
        # 使用临时文件进行测试
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, 'test_preferences.json')
        
        # 临时修改类属性
        self.original_file = PreferenceLearner.PREFERENCES_FILE
        PreferenceLearner.PREFERENCES_FILE = self.test_file
        
        # 创建 PreferenceLearner 实例
        self.learner = PreferenceLearner()
    
    def tearDown(self):
        """测试后清理"""
        # 恢复原始属性
        PreferenceLearner.PREFERENCES_FILE = self.original_file
        
        # 清理临时目录
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_initial_state(self):
        """测试初始状态"""
        self.assertTrue(self.learner.learning_enabled)
        self.assertEqual(self.learner.preferences, {})
        self.assertEqual(dict(self.learner.manual_adjustments), {})
    
    def test_record_manual_adjustment(self):
        """测试记录手动调整"""
        self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        
        adjustments = self.learner.manual_adjustments.get('chrome.exe', [])
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]['from'], 'normal')
        self.assertEqual(adjustments[0]['to'], 'high')
        self.assertIn('timestamp', adjustments[0])
    
    def test_record_multiple_adjustments(self):
        """测试记录多次调整"""
        self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        self.learner.record_manual_adjustment('chrome.exe', 'high', 'idle')
        self.learner.record_manual_adjustment('chrome.exe', 'idle', 'below_normal')
        
        adjustments = self.learner.manual_adjustments.get('chrome.exe', [])
        self.assertEqual(len(adjustments), 3)
    
    def test_adjustment_limit(self):
        """测试调整记录限制（最多100条）"""
        # 记录105次调整
        for i in range(105):
            self.learner.record_manual_adjustment('test.exe', 'normal', 'high')
        
        adjustments = self.learner.manual_adjustments.get('test.exe', [])
        self.assertEqual(len(adjustments), 100)
    
    def test_get_preferred_priority(self):
        """测试获取偏好优先级"""
        # 记录多次调整，大部分偏好 high
        for _ in range(5):
            self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        for _ in range(2):
            self.learner.record_manual_adjustment('chrome.exe', 'high', 'idle')
        
        preferred = self.learner.get_preferred_priority('chrome.exe')
        self.assertEqual(preferred, 'high')
    
    def test_get_preferred_priority_no_history(self):
        """测试没有历史记录时返回 None"""
        preferred = self.learner.get_preferred_priority('nonexistent.exe')
        self.assertIsNone(preferred)
    
    def test_get_adjustment_count(self):
        """测试获取调整次数"""
        self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        self.learner.record_manual_adjustment('chrome.exe', 'high', 'idle')
        
        count = self.learner.get_adjustment_count('chrome.exe')
        self.assertEqual(count, 2)
    
    def test_get_adjustment_count_no_history(self):
        """测试没有历史记录时返回 0"""
        count = self.learner.get_adjustment_count('nonexistent.exe')
        self.assertEqual(count, 0)
    
    def test_get_all_adjusted_processes(self):
        """测试获取所有被调整过的进程"""
        self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        self.learner.record_manual_adjustment('firefox.exe', 'normal', 'idle')
        self.learner.record_manual_adjustment('notepad.exe', 'normal', 'high')
        
        processes = self.learner.get_all_adjusted_processes()
        self.assertEqual(len(processes), 3)
        self.assertIn('chrome.exe', processes)
        self.assertIn('firefox.exe', processes)
        self.assertIn('notepad.exe', processes)
    
    def test_should_adjust_score_learning_disabled(self):
        """测试学习功能禁用时返回原分数"""
        self.learner.set_learning_enabled(False)
        score = self.learner.should_adjust_score('chrome.exe', 50.0, 'browser')
        self.assertEqual(score, 50.0)
    
    def test_should_adjust_score_with_preference(self):
        """测试有偏好时调整分数"""
        # 记录用户偏好 high
        self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        
        # 默认分数50，应该被调整为 higher
        score = self.learner.should_adjust_score('chrome.exe', 50.0, 'browser')
        self.assertEqual(score, 65.0)  # 50 + 15
    
    def test_should_adjust_score_prefers_idle(self):
        """测试偏好 idle 时降低分数"""
        self.learner.record_manual_adjustment('background.exe', 'normal', 'idle')
        
        score = self.learner.should_adjust_score('background.exe', 50.0, 'background')
        self.assertEqual(score, 30.0)  # 50 - 20
    
    def test_should_adjust_score_no_preference(self):
        """测试没有偏好时返回原分数"""
        score = self.learner.should_adjust_score('unknown.exe', 50.0, 'unknown')
        self.assertEqual(score, 50.0)
    
    def test_clear_process_history(self):
        """测试清除某个进程的历史"""
        self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        self.learner.record_manual_adjustment('firefox.exe', 'normal', 'idle')
        
        self.learner.clear_process_history('chrome.exe')
        
        self.assertEqual(len(self.learner.manual_adjustments.get('chrome.exe', [])), 0)
        self.assertEqual(len(self.learner.manual_adjustments.get('firefox.exe', [])), 1)
    
    def test_set_learning_enabled(self):
        """测试设置学习功能开关"""
        self.assertTrue(self.learner.learning_enabled)
        
        self.learner.set_learning_enabled(False)
        self.assertFalse(self.learner.learning_enabled)
        
        self.learner.set_learning_enabled(True)
        self.assertTrue(self.learner.learning_enabled)
    
    def test_get_confidence_no_history(self):
        """测试没有历史记录时置信度为 0"""
        confidence = self.learner.get_confidence('unknown.exe')
        self.assertEqual(confidence, 0.0)
    
    def test_get_confidence_low(self):
        """测试低置信度 (5次以下)"""
        for _ in range(3):
            self.learner.record_manual_adjustment('test.exe', 'normal', 'high')
        
        confidence = self.learner.get_confidence('test.exe')
        self.assertEqual(confidence, 0.3)
    
    def test_get_confidence_medium(self):
        """测试中等置信度 (5-10次)"""
        for _ in range(7):
            self.learner.record_manual_adjustment('test.exe', 'normal', 'high')
        
        confidence = self.learner.get_confidence('test.exe')
        self.assertEqual(confidence, 0.6)
    
    def test_get_confidence_high(self):
        """测试高置信度 (10-20次)"""
        for _ in range(15):
            self.learner.record_manual_adjustment('test.exe', 'normal', 'high')
        
        confidence = self.learner.get_confidence('test.exe')
        self.assertEqual(confidence, 0.8)
    
    def test_get_confidence_very_high(self):
        """测试极高置信度 (20次以上)"""
        for _ in range(25):
            self.learner.record_manual_adjustment('test.exe', 'normal', 'high')
        
        confidence = self.learner.get_confidence('test.exe')
        self.assertEqual(confidence, 0.95)
    
    def test_save_and_load(self):
        """测试保存和加载"""
        self.learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        self.learner.set_learning_enabled(False)
        self.learner.save()
        
        # 创建新的实例，应该能加载之前保存的数据
        new_learner = PreferenceLearner()
        self.assertFalse(new_learner.learning_enabled)
        self.assertEqual(len(new_learner.manual_adjustments.get('chrome.exe', [])), 1)
    
    def test_save_creates_config_dir(self):
        """测试保存时创建配置目录"""
        # 确保目录不存在
        test_dir = os.path.join(self.test_dir, 'subdir')
        test_file = os.path.join(test_dir, 'test_prefs.json')
        PreferenceLearner.PREFERENCES_FILE = test_file
        
        learner = PreferenceLearner()
        learner.record_manual_adjustment('chrome.exe', 'normal', 'high')
        learner.save()
        
        self.assertTrue(os.path.exists(test_file))


class TestPreferenceLearnerIntegration(unittest.TestCase):
    """PreferenceLearner 集成测试"""
    
    def setUp(self):
        """测试前设置"""
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, 'test_preferences.json')
        self.original_file = PreferenceLearner.PREFERENCES_FILE
        PreferenceLearner.PREFERENCES_FILE = self.test_file
    
    def tearDown(self):
        """测试后清理"""
        PreferenceLearner.PREFERENCES_FILE = self.original_file
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_priority_adjustment_values(self):
        """测试各种优先级对应的调整值"""
        learner = PreferenceLearner()
        
        base_score = 50.0
        
        # 测试 high
        learner.record_manual_adjustment('proc1', 'normal', 'high')
        self.assertEqual(learner.should_adjust_score('proc1', base_score, 'test'), 65.0)
        
        # 重置
        learner.clear_process_history('proc1')
        
        # 测试 above_normal
        learner.record_manual_adjustment('proc1', 'normal', 'above_normal')
        self.assertEqual(learner.should_adjust_score('proc1', base_score, 'test'), 55.0)
        
        # 重置
        learner.clear_process_history('proc1')
        
        # 测试 normal
        learner.record_manual_adjustment('proc1', 'high', 'normal')
        self.assertEqual(learner.should_adjust_score('proc1', base_score, 'test'), 50.0)
        
        # 重置
        learner.clear_process_history('proc1')
        
        # 测试 below_normal
        learner.record_manual_adjustment('proc1', 'normal', 'below_normal')
        self.assertEqual(learner.should_adjust_score('proc1', base_score, 'test'), 40.0)
        
        # 重置
        learner.clear_process_history('proc1')
        
        # 测试 idle
        learner.record_manual_adjustment('proc1', 'normal', 'idle')
        self.assertEqual(learner.should_adjust_score('proc1', base_score, 'test'), 30.0)


if __name__ == '__main__':
    unittest.main()