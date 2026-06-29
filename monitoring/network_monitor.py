import os
import time
import psutil
from core.subprocess_utils import run_typeperf


class NetworkMonitor:
    def __init__(self):
        self.process_net_io_cache = {}
        self.last_check_time = {}
    
    def get_network_io_for_process(self, process):
        try:
            pid = process.pid
            process_name = process.name().lower()
            
            if pid == 0:
                return {'read_bytes': 0, 'write_bytes': 0, 'read_bytes_sec': 0, 'write_bytes_sec': 0}
            
            io_counters = process.io_counters()
            if io_counters is None:
                return self._fallback_network_stats(pid, process_name)
            
            current_time = time.time()
            current_read = io_counters.read_bytes
            current_write = io_counters.write_bytes
            
            read_bytes_sec = 0
            write_bytes_sec = 0
            
            if pid in self.process_net_io_cache:
                last_read, last_write, last_time = self.process_net_io_cache[pid]
                time_diff = current_time - last_time
                
                if time_diff > 0:
                    read_bytes_sec = (current_read - last_read) / time_diff
                    write_bytes_sec = (current_write - last_write) / time_diff
            
            self.process_net_io_cache[pid] = (current_read, current_write, current_time)
            
            return {
                'read_bytes': current_read,
                'write_bytes': current_write,
                'read_bytes_sec': read_bytes_sec,
                'write_bytes_sec': write_bytes_sec
            }
        
        except Exception as e:
            return self._fallback_network_stats(pid, process_name)
    
    def _fallback_network_stats(self, pid, process_name):
        try:
            read_sec = run_typeperf(f"\\Process({process_name})\\IO Read Bytes/sec", samples=1, timeout=3)
            write_sec = run_typeperf(f"\\Process({process_name})\\IO Write Bytes/sec", samples=1, timeout=3)
            
            if read_sec is not None or write_sec is not None:
                return {
                    'read_bytes': 0,
                    'write_bytes': 0,
                    'read_bytes_sec': read_sec or 0,
                    'write_bytes_sec': write_sec or 0
                }
        except Exception:
            pass
        
        return {'read_bytes': 0, 'write_bytes': 0, 'read_bytes_sec': 0, 'write_bytes_sec': 0}
    
    def get_total_network_stats(self):
        try:
            net_io = psutil.net_io_counters()
            return {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'errin': net_io.errin,
                'errout': net_io.errout,
                'dropin': net_io.dropin,
                'dropout': net_io.dropout
            }
        except Exception as e:
            return {}
    
    def get_network_interfaces(self):
        interfaces = []
        try:
            for iface, addrs in psutil.net_if_addrs().items():
                interface_info = {
                    'name': iface,
                    'addresses': []
                }
                for addr in addrs:
                    interface_info['addresses'].append({
                        'family': str(addr.family),
                        'address': addr.address,
                        'netmask': addr.netmask,
                        'broadcast': addr.broadcast
                    })
                interfaces.append(interface_info)
        except Exception as e:
            pass
        
        return interfaces
    
    def get_network_connections(self, pid=None):
        connections = []
        try:
            for conn in psutil.net_connections(kind='inet'):
                if pid is not None and conn.pid != pid:
                    continue
                
                connections.append({
                    'fd': conn.fd,
                    'family': str(conn.family),
                    'type': str(conn.type),
                    'laddr': {'ip': conn.laddr.ip, 'port': conn.laddr.port} if conn.laddr else None,
                    'raddr': {'ip': conn.raddr.ip, 'port': conn.raddr.port} if conn.raddr else None,
                    'status': conn.status,
                    'pid': conn.pid
                })
        except Exception as e:
            pass
        
        return connections
    
    def format_bytes(self, bytes_value):
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
    
    def get_process_network_summary(self, process):
        io_stats = self.get_network_io_for_process(process)
        
        return {
            'pid': process.pid,
            'name': process.name(),
            'read_bytes': io_stats['read_bytes'],
            'read_bytes_formatted': self.format_bytes(io_stats['read_bytes']),
            'write_bytes': io_stats['write_bytes'],
            'write_bytes_formatted': self.format_bytes(io_stats['write_bytes']),
            'read_speed': io_stats['read_bytes_sec'],
            'read_speed_formatted': f"{self.format_bytes(io_stats['read_bytes_sec'])}/sec",
            'write_speed': io_stats['write_bytes_sec'],
            'write_speed_formatted': f"{self.format_bytes(io_stats['write_bytes_sec'])}/sec"
        }