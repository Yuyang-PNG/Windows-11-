import os
import time
from datetime import datetime
from core.subprocess_utils import run_typeperf


class PerformanceCounter:
    def __init__(self):
        self._counters = {
            'cpu_total': '\\Processor(_Total)\\% Processor Time',
            'cpu_idle': '\\Processor(_Total)\\% Idle Time',
            'memory_usage': '\\Memory\\% Committed Bytes In Use',
            'memory_available': '\\Memory\\Available MBytes',
            'memory_committed': '\\Memory\\Committed Bytes',
            'disk_read': '\\PhysicalDisk(_Total)\\Disk Read Bytes/sec',
            'disk_write': '\\PhysicalDisk(_Total)\\Disk Write Bytes/sec',
            'disk_queue': '\\PhysicalDisk(_Total)\\Current Disk Queue Length',
            'network_receive': '\\Network Interface(*)\\Bytes Received/sec',
            'network_send': '\\Network Interface(*)\\Bytes Sent/sec',
            'page_file_usage': '\\Paging File(_Total)\\% Usage',
            'system_up_time': '\\System\\System Up Time',
            'context_switches': '\\System\\Context Switches/sec',
            'processes': '\\System\\Processes',
            'threads': '\\System\\Threads'
        }
    
    def _get_counter_value(self, counter_path):
        try:
            return run_typeperf(counter_path, samples=1, timeout=5)
        except Exception:
            return None
    
    def get_cpu_metrics(self):
        return {
            'total_usage': self._get_counter_value(self._counters['cpu_total']),
            'idle_time': self._get_counter_value(self._counters['cpu_idle']),
            'active_usage': None
        }
    
    def get_memory_metrics(self):
        usage = self._get_counter_value(self._counters['memory_usage'])
        available = self._get_counter_value(self._counters['memory_available'])
        committed = self._get_counter_value(self._counters['memory_committed'])
        
        return {
            'usage_percent': usage,
            'available_mb': available,
            'committed_bytes': committed,
            'committed_gb': committed / (1024 ** 3) if committed else None
        }
    
    def get_disk_metrics(self):
        return {
            'read_bytes_sec': self._get_counter_value(self._counters['disk_read']),
            'write_bytes_sec': self._get_counter_value(self._counters['disk_write']),
            'queue_length': self._get_counter_value(self._counters['disk_queue'])
        }
    
    def get_network_metrics(self):
        return {
            'receive_bytes_sec': self._get_counter_value(self._counters['network_receive']),
            'send_bytes_sec': self._get_counter_value(self._counters['network_send'])
        }
    
    def get_system_metrics(self):
        return {
            'page_file_usage': self._get_counter_value(self._counters['page_file_usage']),
            'up_time_seconds': self._get_counter_value(self._counters['system_up_time']),
            'context_switches_sec': self._get_counter_value(self._counters['context_switches']),
            'process_count': self._get_counter_value(self._counters['processes']),
            'thread_count': self._get_counter_value(self._counters['threads'])
        }
    
    def get_all_metrics(self):
        return {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cpu': self.get_cpu_metrics(),
            'memory': self.get_memory_metrics(),
            'disk': self.get_disk_metrics(),
            'network': self.get_network_metrics(),
            'system': self.get_system_metrics()
        }
    
    def get_formatted_metrics(self):
        metrics = self.get_all_metrics()
        lines = []
        
        lines.append("=" * 70)
        lines.append(f"Windows 性能计数器数据 - {metrics['timestamp']}")
        lines.append("=" * 70)
        
        lines.append("\n[CPU]")
        if metrics['cpu']['total_usage'] is not None:
            lines.append(f"  总使用率: {metrics['cpu']['total_usage']:.1f}%")
        if metrics['cpu']['idle_time'] is not None:
            lines.append(f"  空闲时间: {metrics['cpu']['idle_time']:.1f}%")
        
        lines.append("\n[内存]")
        if metrics['memory']['usage_percent'] is not None:
            lines.append(f"  使用百分比: {metrics['memory']['usage_percent']:.1f}%")
        if metrics['memory']['available_mb'] is not None:
            lines.append(f"  可用内存: {metrics['memory']['available_mb']:.0f} MB")
        if metrics['memory']['committed_gb'] is not None:
            lines.append(f"  已提交内存: {metrics['memory']['committed_gb']:.2f} GB")
        
        lines.append("\n[磁盘]")
        if metrics['disk']['read_bytes_sec'] is not None:
            lines.append(f"  读取速度: {self._format_bytes(metrics['disk']['read_bytes_sec'])}/sec")
        if metrics['disk']['write_bytes_sec'] is not None:
            lines.append(f"  写入速度: {self._format_bytes(metrics['disk']['write_bytes_sec'])}/sec")
        if metrics['disk']['queue_length'] is not None:
            lines.append(f"  队列长度: {metrics['disk']['queue_length']:.0f}")
        
        lines.append("\n[网络]")
        if metrics['network']['receive_bytes_sec'] is not None:
            lines.append(f"  接收速度: {self._format_bytes(metrics['network']['receive_bytes_sec'])}/sec")
        if metrics['network']['send_bytes_sec'] is not None:
            lines.append(f"  发送速度: {self._format_bytes(metrics['network']['send_bytes_sec'])}/sec")
        
        lines.append("\n[系统]")
        if metrics['system']['page_file_usage'] is not None:
            lines.append(f"  页面文件使用率: {metrics['system']['page_file_usage']:.1f}%")
        if metrics['system']['up_time_seconds'] is not None:
            lines.append(f"  系统运行时间: {self._format_uptime(metrics['system']['up_time_seconds'])}")
        if metrics['system']['process_count'] is not None:
            lines.append(f"  进程数量: {metrics['system']['process_count']:.0f}")
        if metrics['system']['thread_count'] is not None:
            lines.append(f"  线程数量: {metrics['system']['thread_count']:.0f}")
        if metrics['system']['context_switches_sec'] is not None:
            lines.append(f"  上下文切换: {metrics['system']['context_switches_sec']:.0f}/sec")
        
        lines.append("\n" + "=" * 70)
        
        return '\n'.join(lines)
    
    def _format_bytes(self, bytes_value):
        if bytes_value is None:
            return "N/A"
        
        if bytes_value < 1024:
            return f"{bytes_value:.0f} B"
        elif bytes_value < 1024 ** 2:
            return f"{bytes_value / 1024:.1f} KB"
        elif bytes_value < 1024 ** 3:
            return f"{bytes_value / (1024 ** 2):.1f} MB"
        else:
            return f"{bytes_value / (1024 ** 3):.2f} GB"
    
    def _format_uptime(self, seconds):
        if seconds is None:
            return "N/A"
        
        days = int(seconds // (24 * 3600))
        hours = int((seconds % (24 * 3600)) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        parts.append(f"{secs}秒")
        
        return ' '.join(parts)
    
    def get_process_metrics(self, process_name):
        counters = [
            f"\\Process({process_name})\\% Processor Time",
            f"\\Process({process_name})\\Private Bytes",
            f"\\Process({process_name})\\Working Set",
            f"\\Process({process_name})\\Thread Count",
            f"\\Process({process_name})\\Handle Count",
            f"\\Process({process_name})\\IO Read Bytes/sec",
            f"\\Process({process_name})\\IO Write Bytes/sec"
        ]
        
        results = {}
        for counter in counters:
            value = self._get_counter_value(counter)
            counter_name = counter.split('\\')[-1]
            results[counter_name] = value
        
        return results
    
    def get_process_metrics_formatted(self, process_name):
        metrics = self.get_process_metrics(process_name)
        lines = []
        
        lines.append(f"进程: {process_name}")
        lines.append("-" * 50)
        
        if metrics.get('% Processor Time') is not None:
            lines.append(f"CPU使用率: {metrics['% Processor Time']:.1f}%")
        
        private_bytes = metrics.get('Private Bytes')
        if private_bytes is not None:
            lines.append(f"私有字节: {self._format_bytes(private_bytes)}")
        
        working_set = metrics.get('Working Set')
        if working_set is not None:
            lines.append(f"工作集: {self._format_bytes(working_set)}")
        
        if metrics.get('Thread Count') is not None:
            lines.append(f"线程数: {metrics['Thread Count']:.0f}")
        
        if metrics.get('Handle Count') is not None:
            lines.append(f"句柄数: {metrics['Handle Count']:.0f}")
        
        io_read = metrics.get('IO Read Bytes/sec')
        if io_read is not None:
            lines.append(f"IO读取: {self._format_bytes(io_read)}/sec")
        
        io_write = metrics.get('IO Write Bytes/sec')
        if io_write is not None:
            lines.append(f"IO写入: {self._format_bytes(io_write)}/sec")
        
        return '\n'.join(lines)