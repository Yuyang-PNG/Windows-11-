import subprocess
import sys
from typing import Optional, Tuple, Dict, Any, List


def get_hidden_window_flags() -> int:
    """获取隐藏窗口的标志位"""
    if sys.platform == 'win32':
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_hidden(cmd: List[str], timeout: int = 30, **kwargs) -> subprocess.CompletedProcess:
    """
    在隐藏窗口中执行命令
    
    Args:
        cmd: 命令列表
        timeout: 超时时间（秒）
        **kwargs: 其他 subprocess.run 参数
    
    Returns:
        subprocess.CompletedProcess 对象
    """
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    kwargs.setdefault('creationflags', get_hidden_window_flags())
    
    return subprocess.run(cmd, timeout=timeout, **kwargs)


def run_powershell(command: str, timeout: int = 30) -> Tuple[bool, str]:
    """
    在隐藏窗口中执行 PowerShell 命令
    
    Args:
        command: PowerShell 命令字符串
        timeout: 超时时间（秒）
    
    Returns:
        (成功标志, 输出内容)
    """
    try:
        result = subprocess.run(
            ['powershell', '-Command', command],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=get_hidden_window_flags()
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except Exception as e:
        return False, str(e)


def run_typeperf(counter_path: str, samples: int = 1, timeout: int = 5) -> Optional[float]:
    """
    在隐藏窗口中执行 typeperf 命令获取性能计数器值
    
    Args:
        counter_path: 性能计数器路径
        samples: 采样次数
        timeout: 超时时间（秒）
    
    Returns:
        计数器值，如果失败返回 None
    """
    try:
        result = subprocess.run(
            ['typeperf', '-sc', str(samples), counter_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=get_hidden_window_flags()
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                data_line = lines[-1]
                parts = data_line.split(',')
                if len(parts) >= 2:
                    try:
                        return float(parts[-1].strip('"'))
                    except ValueError:
                        return None
        return None
    except Exception:
        return None


def run_nvidia_smi(query: str, format_type: str = 'csv,noheader,nounits', timeout: int = 5) -> Tuple[bool, str]:
    """
    在隐藏窗口中执行 nvidia-smi 命令
    
    Args:
        query: 查询参数
        format_type: 输出格式
        timeout: 超时时间（秒）
    
    Returns:
        (成功标志, 输出内容)
    """
    try:
        result = subprocess.run(
            ['nvidia-smi', f'--query-gpu={query}', f'--format={format_type}'],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=get_hidden_window_flags()
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except Exception as e:
        return False, str(e)


def run_sc_command(args: List[str], timeout: int = 30) -> Tuple[bool, str]:
    """
    在隐藏窗口中执行 sc 命令（Windows服务管理）
    
    Args:
        args: sc 命令参数列表
        timeout: 超时时间（秒）
    
    Returns:
        (成功标志, 输出内容)
    """
    try:
        result = subprocess.run(
            ['sc'] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=get_hidden_window_flags()
        )
        if result.returncode == 0 or result.stdout.strip():
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except Exception as e:
        return False, str(e)