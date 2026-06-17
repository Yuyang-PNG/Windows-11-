import os
import json
import time
import csv
from datetime import datetime, timedelta
from collections import defaultdict
import threading

class HistoryManager:
    def __init__(self, data_dir='data', max_history_days=7):
        self.data_dir = data_dir
        self.max_history_days = max_history_days
        self._lock = threading.RLock()
        
        self._ensure_dir()
        self._history_cache = {}
    
    def _ensure_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def _get_today_file(self):
        today = datetime.now().strftime('%Y%m%d')
        return os.path.join(self.data_dir, f'history_{today}.csv')
    
    def _get_file_for_date(self, date_str):
        return os.path.join(self.data_dir, f'history_{date_str}.csv')
    
    def record_process_snapshot(self, processes):
        filepath = self._get_today_file()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with self._lock:
            file_exists = os.path.exists(filepath)
            
            with open(filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                if not file_exists:
                    writer.writerow([
                        'timestamp', 'pid', 'name', 'cpu_percent', 'memory_percent',
                        'memory_rss', 'num_threads', 'priority', 'score', 'category'
                    ])
                
                for proc in processes:
                    writer.writerow([
                        timestamp,
                        proc.get('pid', ''),
                        proc.get('name', ''),
                        proc.get('cpu_percent', 0),
                        proc.get('memory_percent', 0),
                        proc.get('memory_rss', 0),
                        proc.get('num_threads', 1),
                        proc.get('new_priority', ''),
                        proc.get('score', 0),
                        proc.get('category', 'unknown')
                    ])
    
    def get_history_for_process(self, process_name, days=7):
        results = []
        today = datetime.now()
        
        with self._lock:
            for day_offset in range(days):
                date = today - timedelta(days=day_offset)
                date_str = date.strftime('%Y%m%d')
                filepath = self._get_file_for_date(date_str)
                
                if not os.path.exists(filepath):
                    continue
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row['name'].lower() == process_name.lower():
                                results.append({
                                    'timestamp': row['timestamp'],
                                    'pid': int(row['pid']),
                                    'name': row['name'],
                                    'cpu_percent': float(row['cpu_percent']),
                                    'memory_percent': float(row['memory_percent']),
                                    'memory_rss': float(row['memory_rss']),
                                    'num_threads': int(row['num_threads']),
                                    'priority': row['priority'],
                                    'score': float(row['score']),
                                    'category': row['category']
                                })
                except Exception as e:
                    print(f"读取历史文件失败 {filepath}: {e}")
        
        return sorted(results, key=lambda x: x['timestamp'])
    
    def get_recent_snapshots(self, minutes=60, limit=10):
        results = []
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        with self._lock:
            filepath = self._get_today_file()
            if not os.path.exists(filepath):
                return results
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        row_time = datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
                        if row_time >= cutoff_time:
                            results.append({
                                'timestamp': row['timestamp'],
                                'pid': int(row['pid']),
                                'name': row['name'],
                                'cpu_percent': float(row['cpu_percent']),
                                'memory_percent': float(row['memory_percent'])
                            })
            except Exception as e:
                print(f"读取历史文件失败 {filepath}: {e}")
        
        return sorted(results, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def detect_anomalies(self, threshold_cpu=50, threshold_memory=10, spike_threshold=200):
        recent = self.get_recent_snapshots(minutes=30)
        
        if not recent:
            return []
        
        anomalies = []
        process_stats = defaultdict(list)
        
        for snap in recent:
            process_stats[snap['name']].append(snap)
        
        for process_name, snapshots in process_stats.items():
            if len(snapshots) < 3:
                continue
            
            cpu_values = [s['cpu_percent'] for s in snapshots]
            memory_values = [s['memory_percent'] for s in snapshots]
            
            avg_cpu = sum(cpu_values) / len(cpu_values)
            avg_memory = sum(memory_values) / len(memory_values)
            max_cpu = max(cpu_values)
            max_memory = max(memory_values)
            
            recent_cpu = cpu_values[-1]
            recent_memory = memory_values[-1]
            
            if len(cpu_values) >= 2:
                cpu_change = ((recent_cpu - cpu_values[-2]) / max(cpu_values[-2], 0.1)) * 100
                memory_change = ((recent_memory - memory_values[-2]) / max(memory_values[-2], 0.1)) * 100
            else:
                cpu_change = 0
                memory_change = 0
            
            is_anomaly = False
            reasons = []
            
            if recent_cpu > threshold_cpu:
                is_anomaly = True
                reasons.append(f"CPU占用过高 ({recent_cpu:.1f}%)")
            
            if recent_memory > threshold_memory:
                is_anomaly = True
                reasons.append(f"内存占用过高 ({recent_memory:.1f}%)")
            
            if cpu_change > spike_threshold:
                is_anomaly = True
                reasons.append(f"CPU突增 ({cpu_change:.0f}%)")
            
            if memory_change > spike_threshold:
                is_anomaly = True
                reasons.append(f"内存突增 ({memory_change:.0f}%)")
            
            if is_anomaly:
                anomalies.append({
                    'process_name': process_name,
                    'current_cpu': recent_cpu,
                    'current_memory': recent_memory,
                    'avg_cpu': avg_cpu,
                    'avg_memory': avg_memory,
                    'max_cpu': max_cpu,
                    'max_memory': max_memory,
                    'cpu_spike': cpu_change,
                    'memory_spike': memory_change,
                    'reasons': reasons,
                    'severity': 'high' if recent_cpu > 80 or recent_memory > 20 else 'medium'
                })
        
        return sorted(anomalies, key=lambda x: x['severity'] == 'high', reverse=True)
    
    def generate_report(self, days=7):
        report = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'period': f'{days}天',
            'summary': {},
            'top_processes': {},
            'anomalies': [],
            'recommendations': []
        }
        
        all_snapshots = []
        today = datetime.now()
        
        with self._lock:
            for day_offset in range(min(days, 7)):
                date = today - timedelta(days=day_offset)
                date_str = date.strftime('%Y%m%d')
                filepath = self._get_file_for_date(date_str)
                
                if not os.path.exists(filepath):
                    continue
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            all_snapshots.append({
                                'timestamp': row['timestamp'],
                                'name': row['name'],
                                'cpu_percent': float(row['cpu_percent']),
                                'memory_percent': float(row['memory_percent']),
                                'category': row['category'],
                                'priority': row['priority']
                            })
                except Exception as e:
                    print(f"读取历史文件失败 {filepath}: {e}")
        
        if not all_snapshots:
            report['summary']['error'] = '没有找到历史数据'
            return report
        
        process_totals = defaultdict(lambda: {'cpu_sum': 0, 'memory_sum': 0, 'count': 0})
        category_totals = defaultdict(lambda: {'cpu_sum': 0, 'memory_sum': 0, 'count': 0})
        
        for snap in all_snapshots:
            process_totals[snap['name']]['cpu_sum'] += snap['cpu_percent']
            process_totals[snap['name']]['memory_sum'] += snap['memory_percent']
            process_totals[snap['name']]['count'] += 1
            
            category_totals[snap['category']]['cpu_sum'] += snap['cpu_percent']
            category_totals[snap['category']]['memory_sum'] += snap['memory_percent']
            category_totals[snap['category']]['count'] += 1
        
        report['summary']['total_snapshots'] = len(all_snapshots)
        report['summary']['unique_processes'] = len(process_totals)
        
        top_cpu_processes = []
        top_memory_processes = []
        
        for name, totals in process_totals.items():
            avg_cpu = totals['cpu_sum'] / totals['count']
            avg_memory = totals['memory_sum'] / totals['count']
            
            top_cpu_processes.append({'name': name, 'avg_cpu': avg_cpu})
            top_memory_processes.append({'name': name, 'avg_memory': avg_memory})
        
        report['top_processes']['by_cpu'] = sorted(top_cpu_processes, key=lambda x: x['avg_cpu'], reverse=True)[:10]
        report['top_processes']['by_memory'] = sorted(top_memory_processes, key=lambda x: x['avg_memory'], reverse=True)[:10]
        
        report['category_summary'] = {}
        for category, totals in category_totals.items():
            if totals['count'] > 0:
                report['category_summary'][category] = {
                    'avg_cpu': totals['cpu_sum'] / totals['count'],
                    'avg_memory': totals['memory_sum'] / totals['count'],
                    'occurrences': totals['count']
                }
        
        report['anomalies'] = self.detect_anomalies()
        
        if report['anomalies']:
            report['recommendations'].append("检测到异常进程，建议检查相关进程是否正常运行")
        
        for proc in report['top_processes']['by_cpu'][:3]:
            if proc['avg_cpu'] > 30:
                report['recommendations'].append(f"{proc['name']} CPU占用较高，建议优化或限制")
        
        for proc in report['top_processes']['by_memory'][:3]:
            if proc['avg_memory'] > 5:
                report['recommendations'].append(f"{proc['name']} 内存占用较高，建议检查内存泄漏")
        
        return report
    
    def clean_old_data(self):
        cutoff_date = datetime.now() - timedelta(days=self.max_history_days)
        cutoff_str = cutoff_date.strftime('%Y%m%d')
        
        with self._lock:
            for filename in os.listdir(self.data_dir):
                if filename.startswith('history_') and filename.endswith('.csv'):
                    date_str = filename[8:-4]
                    if date_str < cutoff_str:
                        filepath = os.path.join(self.data_dir, filename)
                        try:
                            os.remove(filepath)
                            print(f"已清理旧数据: {filename}")
                        except Exception as e:
                            print(f"清理旧数据失败 {filename}: {e}")
    
    def export_report(self, filepath=None):
        report = self.generate_report()
        
        if filepath is None:
            filepath = os.path.join(self.data_dir, f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return filepath
        except Exception as e:
            print(f"导出报告失败: {e}")
            return None
    
    def get_report_summary_text(self):
        report = self.generate_report()
        lines = []

        lines.append("=" * 70)
        lines.append(f"进程优化报告 - {report['generated_at']}")
        lines.append("=" * 70)

        lines.append(f"\n[概览]")
        lines.append(f"  统计周期: {report['period']}")
        lines.append(f"  快照总数: {report['summary'].get('total_snapshots', 0)}")
        lines.append(f"  进程数量: {report['summary'].get('unique_processes', 0)}")

        if 'error' in report['summary']:
            lines.append(f"  错误: {report['summary']['error']}")
            return '\n'.join(lines)

        lines.append("\n[CPU占用最高的进程]")
        for i, proc in enumerate(report['top_processes']['by_cpu'], 1):
            lines.append(f"  {i}. {proc['name']:<20} 平均CPU: {proc['avg_cpu']:.1f}%")

        lines.append("\n[内存占用最高的进程]")
        for i, proc in enumerate(report['top_processes']['by_memory'], 1):
            lines.append(f"  {i}. {proc['name']:<20} 平均内存: {proc['avg_memory']:.1f}%")

        if report['anomalies']:
            lines.append(f"\n[异常检测] ({len(report['anomalies'])}个)")
            for anomaly in report['anomalies'][:5]:
                severity = "🔴" if anomaly['severity'] == 'high' else "🟡"
                lines.append(f"  {severity} {anomaly['process_name']}:")
                lines.append(f"      CPU: {anomaly['current_cpu']:.1f}% | 内存: {anomaly['current_memory']:.1f}%")
                lines.append(f"      原因: {', '.join(anomaly['reasons'])}")

        if report['recommendations']:
            lines.append("\n[优化建议]")
            for i, rec in enumerate(report['recommendations'], 1):
                lines.append(f"  {i}. {rec}")

        lines.append("\n" + "=" * 70)

        return '\n'.join(lines)

    def get_process_history(self, process_name: str, days: int = 7) -> list:
        """获取指定进程的历史记录"""
        results = []
        today = datetime.now()

        for day_offset in range(days):
            date = today - timedelta(days=day_offset)
            date_str = date.strftime('%Y%m%d')
            filepath = self._get_file_for_date(date_str)

            if not os.path.exists(filepath):
                continue

            with self._lock:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row['name'].lower() == process_name.lower():
                                results.append({
                                    'timestamp': row['timestamp'],
                                    'pid': int(row['pid']),
                                    'cpu_percent': float(row['cpu_percent']),
                                    'memory_percent': float(row['memory_percent']),
                                    'priority': row['priority'],
                                    'score': float(row['score']),
                                    'category': row['category']
                                })
                except Exception as e:
                    print(f"读取历史文件失败 {filepath}: {e}")

        return sorted(results, key=lambda x: x['timestamp'])

    def get_priority_changes(self, process_name: str, days: int = 7) -> list:
        """获取进程优先级变更历史"""
        history = self.get_process_history(process_name, days)
        changes = []

        prev_priority = None
        prev_record = None
        for record in history:
            current_priority = record['priority']
            if prev_priority and current_priority != prev_priority:
                changes.append({
                    'timestamp': record['timestamp'],
                    'from': prev_priority,
                    'to': current_priority,
                    'pid': record['pid']
                })
            prev_priority = current_priority
            prev_record = record

        return changes

    def get_process_appearance_count(self, process_name: str, days: int = 7) -> int:
        """获取进程出现的次数"""
        history = self.get_process_history(process_name, days)
        return len(history)

    def get_process_avg_stats(self, process_name: str, days: int = 7) -> dict:
        """获取进程平均统计数据"""
        history = self.get_process_history(process_name, days)
        if not history:
            return {'avg_cpu': 0, 'avg_memory': 0, 'avg_score': 0, 'count': 0}

        total_cpu = sum(h['cpu_percent'] for h in history)
        total_memory = sum(h['memory_percent'] for h in history)
        total_score = sum(h['score'] for h in history)

        return {
            'avg_cpu': total_cpu / len(history),
            'avg_memory': total_memory / len(history),
            'avg_score': total_score / len(history),
            'count': len(history)
        }