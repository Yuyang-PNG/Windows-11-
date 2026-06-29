import threading
import sys
import traceback
import os
from datetime import datetime
from typing import Callable, Any, Optional


def log_crash(exc_type, exc_value, exc_traceback, context: str = ""):
    """记录崩溃日志到文件"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f'crash_{timestamp}.log')
    
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"崩溃时间: {datetime.now()}\n")
            f.write(f"Python版本: {sys.version}\n")
            f.write(f"操作系统: {sys.platform}\n")
            f.write(f"线程: {threading.current_thread().name}\n")
            f.write(f"上下文: {context}\n")
            f.write("\n" + "="*80 + "\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
        
        try:
            from core.gui_manager import show_quick_message
            show_quick_message("程序崩溃", f"程序遇到问题已自动保存日志\n\n日志文件: {log_file}", "error")
        except Exception:
            pass
            
    except Exception:
        pass


def thread_exception_handler(args):
    """线程未捕获异常处理器"""
    exc_type, exc_value, exc_traceback = args
    if issubclass(exc_type, SystemExit):
        return
    
    log_crash(exc_type, exc_value, exc_traceback, f"线程: {threading.current_thread().name}")


def setup_thread_exception_handler():
    """设置线程未捕获异常处理"""
    threading.excepthook = thread_exception_handler


def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    log_crash(exc_type, exc_value, exc_traceback, "主线程")
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def setup_global_exception_handler():
    """设置全局异常处理"""
    sys.excepthook = handle_exception
    setup_thread_exception_handler()


def safe_thread(func: Callable) -> Callable:
    """装饰器：捕获线程中的异常并记录日志"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_crash(type(e), e, sys.exc_info()[2], f"函数: {func.__name__}")
            raise
    return wrapper


class SafeThread(threading.Thread):
    """安全线程类：自动捕获异常"""
    
    def __init__(self, target=None, name=None, args=(), kwargs=None, *, daemon=None):
        if kwargs is None:
            kwargs = {}
        
        def safe_target():
            try:
                if target:
                    return target(*args, **kwargs)
            except Exception as e:
                log_crash(type(e), e, sys.exc_info()[2], f"线程: {name or 'Unknown'}")
                raise
        
        super().__init__(target=safe_target, name=name, daemon=daemon)


def run_in_safe_thread(target: Callable, name: str = None, *args, **kwargs) -> threading.Thread:
    """在安全线程中运行函数"""
    thread = SafeThread(target=target, name=name, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread