"""
GUI 管理模块 - 智优进程管理器主窗口

提供可视化界面，替代控制台输出，在无控制台模式下正常工作。
"""

import os
import sys
import time
import threading
import logging
from typing import Optional, Dict, Any, List, Callable

# 检测是否有控制台
HAS_CONSOLE = sys.stdout is not None and sys.stdout.fileno() >= 0

logger = logging.getLogger('process_priority_manager')


def safe_print(text: str) -> None:
    """安全打印 - 在无控制台模式下不执行 print"""
    if HAS_CONSOLE:
        try:
            print(text)
        except Exception:
            pass


class MainWindow:
    """主窗口类 - 使用 tkinter 实现"""

    _instance: Optional["MainWindow"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MainWindow":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.root: Optional[Any] = None
        self._window_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._callbacks: Dict[str, Callable] = {}

    def is_available(self) -> bool:
        """检查 tkinter 是否可用"""
        try:
            import tkinter
            return True
        except ImportError:
            return False

    def show(self, title: str = "智优进程管理器", on_close: Optional[Callable] = None) -> None:
        """显示主窗口"""
        if self._is_running:
            self._bring_to_front()
            return

        def _run_window():
            try:
                import tkinter as tk
                from tkinter import ttk, messagebox

                self.root = tk.Tk()
                self.root.title(title)
                self.root.geometry("600x500")
                self.root.resizable(True, True)

                # 设置窗口图标（如果可用）
                try:
                    icon_path = os.path.join(os.path.dirname(__file__), '..', 'icon.ico')
                    if os.path.exists(icon_path):
                        self.root.iconbitmap(icon_path)
                except Exception:
                    pass

                # 创建主框架
                self._create_main_frame()

                # 设置关闭回调
                if on_close:
                    self.root.protocol("WM_DELETE_WINDOW", on_close)
                else:
                    self.root.protocol("WM_DELETE_WINDOW", self.hide)

                self._is_running = True
                self.root.mainloop()
                self._is_running = False
                self.root = None

            except Exception as e:
                logger.error(f"GUI 窗口启动失败: {e}")
                self._is_running = False
                self.root = None

        self._window_thread = threading.Thread(target=_run_window, daemon=False)
        self._window_thread.start()

    def hide(self) -> None:
        """隐藏窗口"""
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
        self._is_running = False
        self.root = None

    def _bring_to_front(self) -> None:
        """将窗口带到前台"""
        if self.root:
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass

    def _create_main_frame(self) -> None:
        """创建主界面框架"""
        import tkinter as tk
        from tkinter import ttk

        # 主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题区域
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = ttk.Label(
            title_frame,
            text="智优进程管理器 v1.2.0",
            font=("Microsoft YaHei", 16, "bold")
        )
        title_label.pack(side=tk.LEFT)

        # 状态显示区域
        status_frame = ttk.LabelFrame(main_frame, text="系统状态", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_text = tk.Text(status_frame, height=8, wrap=tk.WORD, font=("Consolas", 10))
        self.status_text.pack(fill=tk.BOTH, expand=True)
        self.status_text.config(state=tk.DISABLED)

        # 操作按钮区域
        button_frame = ttk.LabelFrame(main_frame, text="快捷操作", padding="10")
        button_frame.pack(fill=tk.X, pady=(0, 10))

        buttons = [
            ("查看状态", self._on_view_status),
            ("查看游戏", self._on_view_games),
            ("立即优化", self._on_optimize),
            ("NVIDIA优化", self._on_nvidia_optimize),
            ("查看服务", self._on_view_services),
        ]

        for i, (text, callback) in enumerate(buttons):
            btn = ttk.Button(button_frame, text=text, command=callback, width=12)
            btn.grid(row=0, column=i, padx=5, pady=5)

        # NVIDIA 优化区域
        nvidia_frame = ttk.LabelFrame(main_frame, text="NVIDIA 低延迟优化", padding="10")
        nvidia_frame.pack(fill=tk.X, pady=(0, 10))

        nvidia_buttons = [
            ("竞技低延迟", "low_latency"),
            ("3A画质平衡", "balanced"),
            ("恢复默认", "default"),
        ]

        for i, (text, preset) in enumerate(nvidia_buttons):
            btn = ttk.Button(
                nvidia_frame,
                text=text,
                command=lambda p=preset: self._on_nvidia_preset(p),
                width=12
            )
            btn.grid(row=0, column=i, padx=5, pady=5)

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 底部按钮
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(bottom_frame, text="刷新状态", command=self._refresh_status, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="隐藏窗口", command=self.hide, width=12).pack(side=tk.RIGHT, padx=5)

    def _on_view_status(self) -> None:
        """查看状态回调"""
        if 'view_status' in self._callbacks:
            self._callbacks['view_status']()
        self._refresh_status()

    def _on_view_games(self) -> None:
        """查看游戏回调"""
        if 'view_games' in self._callbacks:
            self._callbacks['view_games']()

    def _on_optimize(self) -> None:
        """立即优化回调"""
        if 'optimize' in self._callbacks:
            self._callbacks['optimize']()
        self._log("执行进程优化...")

    def _on_nvidia_optimize(self) -> None:
        """NVIDIA 优化回调"""
        self._on_nvidia_preset("low_latency")

    def _on_nvidia_preset(self, preset: str) -> None:
        """NVIDIA 预设优化"""
        if 'nvidia_optimize' in self._callbacks:
            self._callbacks['nvidia_optimize'](preset)
        self._log(f"执行 NVIDIA 优化: {preset}")

    def _on_view_services(self) -> None:
        """查看服务回调"""
        if 'view_services' in self._callbacks:
            self._callbacks['view_services']()

    def _refresh_status(self) -> None:
        """刷新状态显示"""
        try:
            from process_priority_manager import get_system_metrics, APP

            metrics = get_system_metrics()
            status = f"CPU: {metrics['cpu_percent']}% ({metrics['cpu_count']}核)\n"
            status += f"内存: {metrics['memory_percent']}%\n"
            status += f"可用内存: {metrics['memory_available']:.1f} GB\n"

            if metrics['gpus']:
                status += "\nGPU:\n"
                for i, gpu in enumerate(metrics['gpus']):
                    status += f"  GPU {i+1}: {gpu['name']} - {gpu['utilization']}%\n"

            if hasattr(APP, 'detect_games'):
                has_games, game_list = APP.detect_games()
                status += f"\n游戏检测: {'运行中' if has_games else '等待中'}\n"
                if has_games and game_list:
                    status += f"检测到的游戏: {', '.join(game_list[:3])}\n"

            self._update_status(status)

        except Exception as e:
            self._log(f"刷新状态失败: {e}")

    def _update_status(self, text: str) -> None:
        """更新状态文本"""
        if self.root and self.status_text:
            try:
                self.status_text.config(state=tk.NORMAL)
                self.status_text.delete(1.0, tk.END)
                self.status_text.insert(tk.END, text)
                self.status_text.config(state=tk.DISABLED)
            except Exception:
                pass

    def _log(self, text: str) -> None:
        """添加日志"""
        safe_print(text)
        if self.root and self.log_text:
            try:
                timestamp = time.strftime("%H:%M:%S")
                self.log_text.insert(tk.END, f"[{timestamp}] {text}\n")
                self.log_text.see(tk.END)
            except Exception:
                pass

    def set_callback(self, name: str, callback: Callable) -> None:
        """设置回调函数"""
        self._callbacks[name] = callback

    def show_message(self, title: str, message: str, type: str = "info") -> None:
        """显示消息框"""
        try:
            import tkinter as tk
            from tkinter import messagebox

            if self.root:
                # 如果主窗口存在，在主线程中显示
                if type == "error":
                    messagebox.showerror(title, message, parent=self.root)
                elif type == "warning":
                    messagebox.showwarning(title, message, parent=self.root)
                else:
                    messagebox.showinfo(title, message, parent=self.root)
            else:
                # 创建临时窗口
                temp_root = tk.Tk()
                temp_root.withdraw()
                if type == "error":
                    messagebox.showerror(title, message)
                elif type == "warning":
                    messagebox.showwarning(title, message)
                else:
                    messagebox.showinfo(title, message)
                temp_root.destroy()

        except Exception as e:
            logger.error(f"显示消息框失败: {e}")
            safe_print(f"[{title}] {message}")


def get_main_window() -> MainWindow:
    """获取主窗口实例"""
    return MainWindow()


def show_quick_message(title: str, message: str, type: str = "info", timeout: int = 0) -> None:
    """快速显示消息框（不依赖主窗口）"""
    def _show():
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()

            if type == "error":
                messagebox.showerror(title, message)
            elif type == "warning":
                messagebox.showwarning(title, message)
            else:
                messagebox.showinfo(title, message)

            root.destroy()

        except Exception as e:
            logger.error(f"显示消息框失败: {e}")
            safe_print(f"[{title}] {message}")

    # 在单独线程中显示，避免阻塞
    thread = threading.Thread(target=_show, daemon=True)
    thread.start()