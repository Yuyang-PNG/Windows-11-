"""
GUI 管理模块 - 智优进程管理器主窗口

提供可视化界面，替代控制台输出，在无控制台模式下正常工作。
"""

import os
import sys
import time
import threading
import logging
from typing import Optional, Dict, Any, Callable

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
        self._close_event = None

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
                self.root.geometry("700x600")
                self.root.resizable(True, True)
                self.root.minsize(600, 500)

                # 设置窗口图标（如果可用）
                try:
                    icon_path = os.path.join(os.path.dirname(__file__), '..', 'icon.ico')
                    if os.path.exists(icon_path):
                        self.root.iconbitmap(icon_path)
                except Exception:
                    pass

                # 应用现代化主题
                self._apply_modern_theme()

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
                self.root.update()
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

    def _apply_modern_theme(self) -> None:
        """应用现代化主题样式"""
        import tkinter as tk

        # 定义颜色主题
        colors = {
            'primary': '#3b82f6',
            'primary_light': '#60a5fa',
            'primary_dark': '#2563eb',
            'secondary': '#64748b',
            'success': '#10b981',
            'warning': '#f59e0b',
            'danger': '#ef4444',
            'bg': '#1e293b',
            'bg_light': '#334155',
            'bg_lighter': '#475569',
            'text': '#f8fafc',
            'text_secondary': '#94a3b8',
            'border': '#475569'
        }

        # 设置全局样式
        style = """
            * {
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }
            .title_label {
                font-size: 18px;
                font-weight: bold;
                color: #3b82f6;
            }
            .status_frame {
                background-color: #1e293b;
                border-color: #475569;
            }
            .btn-primary {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
            }
            .btn-primary:hover {
                background-color: #2563eb;
            }
            .btn-secondary {
                background-color: #475569;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
            }
        """

        try:
            self.root.tk.call('source', 'sun-valley.tcl')
        except Exception:
            # 如果没有主题文件，使用内置样式
            pass

        # 设置窗口背景
        self.root.configure(bg=colors['bg'])

    def _create_main_frame(self) -> None:
        """创建主界面框架"""
        import tkinter as tk
        from tkinter import ttk

        # 主容器 - 使用 PanedWindow 实现可调整布局
        main_paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ========== 顶部标题区域 ==========
        header_frame = ttk.Frame(main_paned, height=60)
        main_paned.add(header_frame, weight=0)

        # 标题
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(fill=tk.X, pady=10)

        title_label = ttk.Label(
            title_frame,
            text="智优进程管理器",
            font=("Microsoft YaHei", 20, "bold"),
            foreground="#3b82f6"
        )
        title_label.pack(side=tk.LEFT, padx=5)

        version_label = ttk.Label(
            title_frame,
            text="v1.2.1",
            font=("Microsoft YaHei", 12),
            foreground="#94a3b8"
        )
        version_label.pack(side=tk.LEFT, padx=5, pady=5)

        # 状态指示灯
        status_indicator = ttk.Label(title_frame, text="●", font=("Arial", 12), foreground="#10b981")
        status_indicator.pack(side=tk.RIGHT, padx=10)
        status_text = ttk.Label(title_frame, text="运行中", font=("Microsoft YaHei", 10), foreground="#10b981")
        status_text.pack(side=tk.RIGHT)

        # ========== 主内容区域 ==========
        content_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(content_paned, weight=1)

        # 左侧：系统状态
        left_frame = ttk.Frame(content_paned, width=300)
        content_paned.add(left_frame, weight=1)

        # 系统状态卡片
        status_card = ttk.LabelFrame(left_frame, text="系统状态", padding="12")
        status_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        status_card.configure(style='Card.TLabelframe')

        self.status_text = tk.Text(
            status_card,
            height=10,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#1e293b",
            fg="#f8fafc",
            insertbackground="#f8fafc",
            borderwidth=0
        )
        self.status_text.pack(fill=tk.BOTH, expand=True)
        self.status_text.config(state=tk.DISABLED)

        # 快捷操作卡片
        action_card = ttk.LabelFrame(left_frame, text="快捷操作", padding="12")
        action_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 操作按钮网格
        actions = [
            ("查看状态", self._on_view_status),
            ("查看游戏", self._on_view_games),
            ("立即优化", self._on_optimize),
            ("查看服务", self._on_view_services),
        ]

        action_btn_frame = ttk.Frame(action_card)
        action_btn_frame.pack(fill=tk.BOTH, expand=True)

        for i, (text, callback) in enumerate(actions):
            btn = ttk.Button(
                action_btn_frame,
                text=text,
                command=callback,
                style='Action.TButton',
                padding=(8, 6)
            )
            row = i // 2
            col = i % 2
            btn.grid(row=row, column=col, padx=5, pady=5, sticky=tk.NSEW)

        action_btn_frame.grid_columnconfigure(0, weight=1)
        action_btn_frame.grid_columnconfigure(1, weight=1)

        # ========== 右侧：NVIDIA 优化与日志 ==========
        right_frame = ttk.Frame(content_paned, width=300)
        content_paned.add(right_frame, weight=1)

        # NVIDIA 优化卡片
        nvidia_card = ttk.LabelFrame(right_frame, text="NVIDIA 低延迟优化", padding="12")
        nvidia_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        nvidia_buttons_frame = ttk.Frame(nvidia_card)
        nvidia_buttons_frame.pack(fill=tk.BOTH, expand=True)

        nvidia_presets = [
            ("⚡ 竞技低延迟", "low_latency", "#ef4444"),
            ("🎮 3A画质平衡", "balanced", "#f59e0b"),
            ("🔄 恢复默认", "default", "#64748b"),
        ]

        for i, (text, preset, color) in enumerate(nvidia_presets):
            btn = ttk.Button(
                nvidia_buttons_frame,
                text=text,
                command=lambda p=preset: self._on_nvidia_preset(p),
                style='Nvidia.TButton',
                padding=(10, 8)
            )
            btn.grid(row=0, column=i, padx=5, pady=5, sticky=tk.NSEW)

        nvidia_buttons_frame.grid_columnconfigure(0, weight=1)
        nvidia_buttons_frame.grid_columnconfigure(1, weight=1)
        nvidia_buttons_frame.grid_columnconfigure(2, weight=1)

        # 优化说明
        nvidia_note = ttk.Label(
            nvidia_card,
            text="优化前请关闭所有游戏程序",
            font=("Microsoft YaHei", 9),
            foreground="#f59e0b"
        )
        nvidia_note.pack(side=tk.BOTTOM, pady=5)

        # 日志卡片
        log_card = ttk.LabelFrame(right_frame, text="操作日志", padding="12")
        log_card.pack(fill=tk.BOTH, expand=True)

        log_container = ttk.Frame(log_card)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_container,
            height=12,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            borderwidth=0,
            relief=tk.FLAT
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # ========== 底部按钮区域 ==========
        bottom_frame = ttk.Frame(main_paned, height=40)
        main_paned.add(bottom_frame, weight=0)

        refresh_btn = ttk.Button(
            bottom_frame,
            text="🔄 刷新状态",
            command=self._refresh_status,
            style='Refresh.TButton'
        )
        refresh_btn.pack(side=tk.LEFT, padx=10, pady=5)

        hide_btn = ttk.Button(
            bottom_frame,
            text="✕ 隐藏窗口",
            command=self.hide,
            style='Hide.TButton'
        )
        hide_btn.pack(side=tk.RIGHT, padx=10, pady=5)

        # 配置样式
        self._configure_styles()

    def _configure_styles(self) -> None:
        """配置自定义样式"""
        from tkinter import ttk

        style = ttk.Style()

        # 卡片样式
        style.configure('Card.TLabelframe',
                        background='#1e293b',
                        bordercolor='#475569',
                        borderwidth=1,
                        relief=tk.SOLID)
        style.configure('Card.TLabelframe.Label',
                        background='#1e293b',
                        foreground='#f8fafc',
                        font=("Microsoft YaHei", 11, "bold"))

        # 按钮样式
        style.configure('Action.TButton',
                        background='#3b82f6',
                        foreground='white',
                        borderwidth=0,
                        borderradius=6,
                        padding=(8, 6))
        style.map('Action.TButton',
                  background=[('active', '#2563eb'), ('hover', '#60a5fa')])

        style.configure('Nvidia.TButton',
                        background='#475569',
                        foreground='white',
                        borderwidth=0,
                        borderradius=6,
                        padding=(10, 8),
                        font=("Microsoft YaHei", 10))
        style.map('Nvidia.TButton',
                  background=[('active', '#64748b'), ('hover', '#334155')])

        style.configure('Refresh.TButton',
                        background='#10b981',
                        foreground='white',
                        borderwidth=0,
                        borderradius=6,
                        padding=(10, 6))
        style.map('Refresh.TButton',
                  background=[('active', '#059669'), ('hover', '#34d399')])

        style.configure('Hide.TButton',
                        background='#ef4444',
                        foreground='white',
                        borderwidth=0,
                        borderradius=6,
                        padding=(10, 6))
        style.map('Hide.TButton',
                  background=[('active', '#dc2626'), ('hover', '#f87171')])

        # 标签样式
        style.configure('Header.TLabel',
                        font=("Microsoft YaHei", 14, "bold"),
                        foreground='#3b82f6')

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

        preset_names = {
            "low_latency": "竞技低延迟",
            "balanced": "3A画质平衡",
            "default": "恢复默认"
        }
        self._log(f"执行 NVIDIA 优化: {preset_names.get(preset, preset)}")

    def _on_view_services(self) -> None:
        """查看服务回调"""
        if 'view_services' in self._callbacks:
            self._callbacks['view_services']()

    def _refresh_status(self) -> None:
        """刷新状态显示"""
        try:
            from process_priority_manager import get_system_metrics, APP

            metrics = get_system_metrics()
            status = f"📊 CPU: {metrics['cpu_percent']}% ({metrics['cpu_count']}核)\n"
            status += f"💾 内存: {metrics['memory_percent']}%\n"
            status += f"🆓 可用内存: {metrics['memory_available']:.1f} GB\n"

            if metrics['gpus']:
                status += "\n🎮 GPU:\n"
                for i, gpu in enumerate(metrics['gpus']):
                    status += f"  GPU {i+1}: {gpu['name']} - {gpu['utilization']}%\n"

            if hasattr(APP, 'detect_games'):
                has_games, game_list = APP.detect_games()
                status += f"\n🎯 游戏检测: {'运行中' if has_games else '等待中'}\n"
                if has_games and game_list:
                    status += f"  检测到: {', '.join(game_list[:3])}\n"

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
                if type == "error":
                    messagebox.showerror(title, message, parent=self.root)
                elif type == "warning":
                    messagebox.showwarning(title, message, parent=self.root)
                else:
                    messagebox.showinfo(title, message, parent=self.root)
            else:
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

    thread = threading.Thread(target=_show, daemon=True)
    thread.start()