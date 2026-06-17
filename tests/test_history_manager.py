import os
import sys
import tempfile
import csv
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitoring.history_manager import HistoryManager
import unittest


class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        """每个测试方法前创建临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.history_manager = HistoryManager(data_dir=self.temp_dir, max_history_days=7)

    def tearDown(self):
        """清理临时文件"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _create_test_csv(self, date_str, rows):
        """创建测试用的CSV文件"""
        filepath = os.path.join(self.temp_dir, f'history_{date_str}.csv')
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'pid', 'name', 'cpu_percent', 'memory_percent',
                           'memory_rss', 'num_threads', 'priority', 'score', 'category'])
            for row in rows:
                writer.writerow(row)
        return filepath

    def test_get_process_history(self):
        """测试 get_process_history 方法"""
        today = datetime.now().strftime('%Y%m%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

        self._create_test_csv(today, [
            ['2024-01-01 10:00:00', '100', 'chrome.exe', '10.5', '2.5', '100', '1', 'NORMAL', '50', 'browser'],
            ['2024-01-01 11:00:00', '101', 'chrome.exe', '15.0', '3.0', '120', '1', 'BELOW_NORMAL', '60', 'browser'],
            ['2024-01-01 12:00:00', '102', 'firefox.exe', '5.0', '1.0', '80', '1', 'NORMAL', '30', 'browser'],
        ])

        self._create_test_csv(yesterday, [
            ['2024-01-02 10:00:00', '100', 'chrome.exe', '12.0', '2.8', '110', '1', 'NORMAL', '55', 'browser'],
        ])

        result = self.history_manager.get_process_history('chrome.exe', days=7)
        assert len(result) == 3
        assert result[0]['cpu_percent'] == 10.5
        assert result[1]['priority'] == 'BELOW_NORMAL'
        assert result[2]['pid'] == 100

    def test_get_priority_changes(self):
        """测试 get_priority_changes 方法"""
        today = datetime.now().strftime('%Y%m%d')
        self._create_test_csv(today, [
            ['2024-01-01 10:00:00', '100', 'test.exe', '10.0', '2.0', '100', '1', 'NORMAL', '50', 'test'],
            ['2024-01-01 11:00:00', '100', 'test.exe', '15.0', '2.5', '100', '1', 'HIGH', '70', 'test'],
            ['2024-01-01 12:00:00', '100', 'test.exe', '20.0', '3.0', '100', '1', 'LOW', '30', 'test'],
        ])

        changes = self.history_manager.get_priority_changes('test.exe', days=7)
        assert len(changes) == 2
        assert changes[0]['from'] == 'NORMAL'
        assert changes[0]['to'] == 'HIGH'
        assert changes[1]['from'] == 'HIGH'
        assert changes[1]['to'] == 'LOW'

    def test_get_process_appearance_count(self):
        """测试 get_process_appearance_count 方法"""
        today = datetime.now().strftime('%Y%m%d')
        self._create_test_csv(today, [
            ['2024-01-01 10:00:00', '100', 'chrome.exe', '10.0', '2.0', '100', '1', 'NORMAL', '50', 'browser'],
            ['2024-01-01 11:00:00', '101', 'chrome.exe', '15.0', '2.5', '100', '1', 'NORMAL', '50', 'browser'],
            ['2024-01-01 12:00:00', '102', 'firefox.exe', '5.0', '1.0', '80', '1', 'NORMAL', '30', 'browser'],
        ])

        count = self.history_manager.get_process_appearance_count('chrome.exe', days=7)
        assert count == 2

        count_nonexistent = self.history_manager.get_process_appearance_count('nonexistent.exe', days=7)
        assert count_nonexistent == 0

    def test_get_process_avg_stats(self):
        """测试 get_process_avg_stats 方法"""
        today = datetime.now().strftime('%Y%m%d')
        self._create_test_csv(today, [
            ['2024-01-01 10:00:00', '100', 'test.exe', '10.0', '2.0', '100', '1', 'NORMAL', '50', 'test'],
            ['2024-01-01 11:00:00', '101', 'test.exe', '20.0', '4.0', '100', '1', 'NORMAL', '100', 'test'],
            ['2024-01-01 12:00:00', '102', 'test.exe', '30.0', '6.0', '100', '1', 'NORMAL', '150', 'test'],
        ])

        stats = self.history_manager.get_process_avg_stats('test.exe', days=7)
        assert stats['avg_cpu'] == 20.0
        assert stats['avg_memory'] == 4.0
        assert stats['avg_score'] == 100.0
        assert stats['count'] == 3

    def test_get_process_avg_stats_empty(self):
        """测试空结果的 get_process_avg_stats"""
        stats = self.history_manager.get_process_avg_stats('nonexistent.exe', days=7)
        assert stats['avg_cpu'] == 0
        assert stats['avg_memory'] == 0
        assert stats['avg_score'] == 0
        assert stats['count'] == 0

    def test_get_process_history_case_insensitive(self):
        """测试进程名大小写不敏感"""
        today = datetime.now().strftime('%Y%m%d')
        self._create_test_csv(today, [
            ['2024-01-01 10:00:00', '100', 'Chrome.exe', '10.0', '2.0', '100', '1', 'NORMAL', '50', 'browser'],
        ])

        result_lower = self.history_manager.get_process_history('chrome.exe', days=7)
        result_upper = self.history_manager.get_process_history('CHROME.EXE', days=7)
        result_mixed = self.history_manager.get_process_history('Chrome.exe', days=7)

        assert len(result_lower) == 1
        assert len(result_upper) == 1
        assert len(result_mixed) == 1

    def test_get_process_history_sorted_by_timestamp(self):
        """测试结果按时间戳排序"""
        today = datetime.now().strftime('%Y%m%d')
        self._create_test_csv(today, [
            ['2024-01-01 12:00:00', '100', 'test.exe', '30.0', '3.0', '100', '1', 'NORMAL', '30', 'test'],
            ['2024-01-01 10:00:00', '100', 'test.exe', '10.0', '1.0', '100', '1', 'NORMAL', '10', 'test'],
            ['2024-01-01 11:00:00', '100', 'test.exe', '20.0', '2.0', '100', '1', 'NORMAL', '20', 'test'],
        ])

        result = self.history_manager.get_process_history('test.exe', days=7)
        assert len(result) == 3
        assert result[0]['timestamp'] == '2024-01-01 10:00:00'
        assert result[1]['timestamp'] == '2024-01-01 11:00:00'
        assert result[2]['timestamp'] == '2024-01-01 12:00:00'


if __name__ == '__main__':
    import unittest
    unittest.main()