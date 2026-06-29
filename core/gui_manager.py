"""
GUI 管理模块 - 智优进程管理器主窗口
提供可视化界面，替代控制台输出，在无控制台模式下正常工作。
"""

import os
import sys
import time
import threading
import logging
from queue import Queue
from typing import Optional, Dict, Any, Callable

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
    """主窗口类 - 使用 tkinter 实现专业级界面"""

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
        self._is_running = False
        self._callbacks: Dict[str, Callable] = {}
        self._current_panel = None
        self._panels = {}
        self._nav_buttons = {}
        self._after_ids = []
        
        # 后台刷新相关
        self._refresh_queue = Queue(maxsize=10)
        self._refresh_thread = None
        self._refresh_counter = 0

    def is_available(self) -> bool:
        """检查 tkinter 是否可用"""
        try:
            import tkinter
            return True
        except ImportError:
            return False

    def show(self, title: str = "智优进程管理器", on_close: Optional[Callable] = None) -> None:
        """显示主窗口"""
        import tkinter as tk
        from tkinter import ttk, messagebox
        import traceback

        if self._is_running and self.root is not None:
            self._bring_to_front()
            return

        def _run_window():
            try:
                try:
                    from ctypes import windll
                    windll.shcore.SetProcessDpiAwareness(1)
                except Exception:
                    pass

                self.root = tk.Tk()
                self.root.title(title)
                self.root.geometry("900x650")
                self.root.resizable(True, True)
                self.root.minsize(700, 450)

                try:
                    if hasattr(sys, '_MEIPASS'):
                        icon_path = os.path.join(sys._MEIPASS, 'icon.ico')
                    else:
                        icon_path = os.path.join(os.path.dirname(__file__), '..', 'icon.ico')
                    if os.path.exists(icon_path):
                        self.root.iconbitmap(icon_path)
                except Exception:
                    pass

                self._colors = self._get_theme_colors('dark')
                self.root.configure(bg=self._colors['bg'])

                self._create_main_layout()

                if on_close:
                    self.root.protocol("WM_DELETE_WINDOW", on_close)
                else:
                    self.root.protocol("WM_DELETE_WINDOW", self.hide)

                self._is_running = True
                self._start_background_refresher()
                self._schedule_ui_update()

                self.root.mainloop()

            except Exception as e:
                error_msg = f"GUI启动失败: {str(e)}\n\n{traceback.format_exc()}"
                logger.error(error_msg)
                try:
                    temp_root = tk.Tk()
                    temp_root.withdraw()
                    messagebox.showerror("GUI错误", error_msg)
                    temp_root.destroy()
                except:
                    safe_print(f"GUI错误: {error_msg}")
            finally:
                self._is_running = False
                self.root = None

        if threading.current_thread() is threading.main_thread():
            _run_window()
        else:
            try:
                import tkinter as tk
                temp_root = tk.Tk()
                temp_root.withdraw()
                temp_root.after(0, _run_window)
                temp_root.mainloop()
            except Exception as e:
                safe_print(f"无法在主线程运行GUI: {e}")
                _run_window()

    def _start_background_refresher(self):
        """启动后台刷新线程"""
        def _refresh_worker():
            while self._is_running:
                try:
                    import psutil
                    
                    self._refresh_counter += 1
                    metrics = {
                        'type': 'status',
                        'cpu': psutil.cpu_percent(interval=None),
                        'memory': psutil.virtual_memory(),
                        'counter': self._refresh_counter,
                        'timestamp': time.time()
                    }
                    
                    if not self._refresh_queue.full():
                        try:
                            self._refresh_queue.put_nowait(metrics)
                        except:
                            pass
                    
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"后台刷新失败: {e}")
                    time.sleep(1)
        
        self._refresh_thread = threading.Thread(target=_refresh_worker, daemon=True)
        self._refresh_thread.start()

    def _schedule_ui_update(self):
        """调度UI更新"""
        def _update_ui():
            if not self._is_running:
                return
            
            while not self._refresh_queue.empty():
                try:
                    metrics = self._refresh_queue.get_nowait()
                    if metrics.get('type') == 'status' and self._current_panel == 'system':
                        self._update_status_display(metrics)
                except Exception as e:
                    logger.debug(f"处理更新队列失败: {e}")
            
            if self._is_running:
                after_id = self.root.after(100, _update_ui)
                self._after_ids.append(after_id)
        
        _update_ui()

    def _update_status_display(self, metrics):
        """更新状态显示"""
        try:
            cpu_percent = metrics.get('cpu', 0)
            memory = metrics.get('memory')
            
            if hasattr(self, 'cpu_display') and self._safe_widget_exists(self.cpu_display):
                self.cpu_display.config(text=f"{cpu_percent:.1f}%")
                self.cpu_progress['value'] = cpu_percent
                
                if cpu_percent > 80:
                    self.cpu_display.config(foreground=self._colors['danger'])
                elif cpu_percent > 60:
                    self.cpu_display.config(foreground=self._colors['warning'])
                else:
                    self.cpu_display.config(foreground=self._colors['primary'])
            
            if memory and hasattr(self, 'mem_display') and self._safe_widget_exists(self.mem_display):
                mem_percent = memory.percent
                self.mem_display.config(text=f"{mem_percent:.1f}%")
                self.mem_progress['value'] = mem_percent
                
                if mem_percent > 85:
                    self.mem_display.config(foreground=self._colors['danger'])
                elif mem_percent > 70:
                    self.mem_display.config(foreground=self._colors['warning'])
                else:
                    self.mem_display.config(foreground=self._colors['success'])
            
            counter = metrics.get('counter', 0)
            
            if counter % 10 == 0 and hasattr(self, 'gpu_text') and self._safe_widget_exists(self.gpu_text):
                self._refresh_gpu_info()
            
            if counter % 60 == 0 and hasattr(self, 'disk_text') and self._safe_widget_exists(self.disk_text):
                self._refresh_disk_info()
                
        except Exception as e:
            logger.debug(f"更新状态显示失败: {e}")

    def _refresh_gpu_info(self):
        """刷新GPU信息"""
        try:
            import tkinter as tk
            
            gpu_text = ""
            try:
                from process_priority_manager import get_gpu_info
                gpus = get_gpu_info()
                if gpus:
                    for i, gpu in enumerate(gpus):
                        gpu_text += f"GPU {i+1}: {gpu['name']}\n"
                        gpu_text += f"  显存: {gpu.get('memory_used', 0)}/{gpu.get('memory_total', 0)} MB\n"
                        gpu_text += f"  使用率: {gpu.get('utilization', 0)}%\n"
                else:
                    gpu_text = "未检测到 GPU 信息"
            except Exception:
                gpu_text = "GPU检测不可用"
            
            self.gpu_text.config(state=tk.NORMAL)
            self.gpu_text.delete(1.0, tk.END)
            self.gpu_text.insert(tk.END, gpu_text)
            self.gpu_text.config(state=tk.DISABLED)
        except Exception as e:
            logger.debug(f"刷新GPU信息失败: {e}")

    def _refresh_disk_info(self):
        """刷新磁盘信息"""
        try:
            import tkinter as tk
            import psutil
            
            disk_text = ""
            try:
                for part in psutil.disk_partitions(all=False):
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        disk_text += f"{part.device} ({part.mountpoint}):\n"
                        disk_text += f"  已用: {usage.percent:.1f}%  可用: {usage.free / (1024**3):.1f} GB\n"
                    except:
                        pass
            except Exception:
                pass
            
            self.disk_text.config(state=tk.NORMAL)
            self.disk_text.delete(1.0, tk.END)
            self.disk_text.insert(tk.END, disk_text if disk_text else "未检测到磁盘信息")
            self.disk_text.config(state=tk.DISABLED)
        except Exception as e:
            logger.debug(f"刷新磁盘信息失败: {e}")

    def hide(self) -> None:
        """隐藏窗口"""
        if self.root:
            try:
                self._is_running = False
                self.root.after(0, self._safe_destroy)
            except Exception as e:
                logger.error(f"隐藏窗口失败: {e}")

    def _safe_destroy(self):
        """安全销毁窗口"""
        try:
            self._cancel_all_after()
            if self.root:
                self.root.destroy()
                self.root = None
        except Exception as e:
            logger.error(f"销毁窗口失败: {e}")

    def _cancel_all_after(self):
        """取消所有已注册的定时器"""
        for after_id in self._after_ids:
            try:
                if self.root and self._safe_widget_exists(self.root):
                    self.root.after_cancel(after_id)
            except Exception:
                pass
        self._after_ids.clear()

    def _safe_widget_exists(self, widget):
        """安全检查控件是否存在"""
        try:
            return widget.winfo_exists()
        except Exception:
            return False

    def _bring_to_front(self) -> None:
        """将窗口带到前台"""
        if self.root:
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass

    def _get_theme_colors(self, theme_name='dark') -> dict:
        """获取专业级主题配色方案"""
        themes = {
            'dark': {
                'primary': '#0ea5e9',
                'primary_light': '#38bdf8',
                'success': '#10b981',
                'warning': '#f59e0b',
                'danger': '#ef4444',
                
                'bg': '#1e293b',
                'bg_card': '#334155',
                'bg_card_hover': '#475569',
                'bg_sidebar': '#0f172a',
                'bg_sidebar_item': '#1e293b',
                
                'text': '#f1f5f9',
                'text_secondary': '#94a3b8',
                'text_muted': '#64748b',
                'text_inverse': '#0f172a',
                
                'border': '#475569',
                'accent': '#0ea5e9',
            },
            'light': {
                'primary': '#3b82f6',
                'success': '#10b981',
                'warning': '#f59e0b',
                'danger': '#ef4444',
                
                'bg': '#ffffff',
                'bg_card': '#f8fafc',
                'bg_card_hover': '#f1f5f9',
                'bg_sidebar': '#f1f5f9',
                'bg_sidebar_item': '#ffffff',
                
                'text': '#1e293b',
                'text_secondary': '#64748b',
                'text_muted': '#94a3b8',
                'text_inverse': '#ffffff',
                
                'border': '#e2e8f0',
                'accent': '#3b82f6',
            }
        }
        return themes.get(theme_name, themes['dark'])

    def _create_main_layout(self) -> None:
        """创建专业级界面布局"""
        import tkinter as tk
        from tkinter import ttk

        # 主容器
        main_container = tk.Frame(self.root, bg=self._colors['bg'])
        main_container.pack(fill=tk.BOTH, expand=True)

        # ========== 左侧边栏 ==========
        sidebar_frame = tk.Frame(main_container, bg=self._colors['bg_sidebar'], width=200)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        sidebar_frame.pack_propagate(False)

        # 侧边栏顶部装饰条
        accent_bar = tk.Frame(sidebar_frame, bg=self._colors['accent'], height=3)
        accent_bar.pack(fill=tk.X)

        # Logo区域
        logo_frame = tk.Frame(sidebar_frame, bg=self._colors['bg_sidebar'])
        logo_frame.pack(fill=tk.X, pady=20, padx=15)
        
        logo_icon = tk.Label(logo_frame, text="◈", font=("Arial", 20), fg=self._colors['primary'], bg=self._colors['bg_sidebar'])
        logo_icon.pack(side=tk.LEFT)
        
        logo_text = tk.Frame(logo_frame, bg=self._colors['bg_sidebar'])
        logo_text.pack(side=tk.LEFT, padx=10)
        
        app_name = tk.Label(logo_text, text="智优进程管理器", font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_sidebar'])
        app_name.pack(anchor=tk.W)
        
        app_version = tk.Label(logo_text, text="v1.2.2", font=("Microsoft YaHei", 9), fg=self._colors['text_muted'], bg=self._colors['bg_sidebar'])
        app_version.pack(anchor=tk.W)

        # 分隔线
        separator = tk.Frame(sidebar_frame, bg=self._colors['border'], height=1)
        separator.pack(fill=tk.X, padx=15, pady=5)

        # 导航按钮
        nav_items = [
            ('system', '◉', '系统状态'),
            ('games', '▶', '游戏检测'),
            ('optimize', '⚡', '进程优化'),
            ('nvidia', '▣', 'NVIDIA'),
            ('services', '✦', '服务状态'),
            ('shortcuts', '⌘', '快捷键'),
            ('settings', '●', '设置'),
        ]

        for nav_id, icon, label in nav_items:
            btn = tk.Label(
                sidebar_frame,
                text=f"{icon}  {label}",
                font=("Microsoft YaHei", 11),
                fg=self._colors['text_secondary'],
                bg=self._colors['bg_sidebar'],
                anchor='w',
                cursor='hand2',
                padx=20,
                pady=10
            )
            btn.pack(fill=tk.X)
            btn._is_selected = False
            btn._nav_id = nav_id
            
            btn.bind('<Enter>', lambda e, b=btn: self._on_nav_hover(b, True))
            btn.bind('<Leave>', lambda e, b=btn: self._on_nav_hover(b, False))
            btn.bind('<Button-1>', lambda e, id=nav_id: self._on_nav_click(id))
            
            self._nav_buttons[nav_id] = btn

        # 底部状态指示
        bottom_frame = tk.Frame(sidebar_frame, bg=self._colors['bg_sidebar'])
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=15)
        
        status_icon = tk.Label(bottom_frame, text="●", font=("Arial", 10), fg=self._colors['success'], bg=self._colors['bg_sidebar'])
        status_icon.pack(side=tk.LEFT, padx=20)
        
        status_text = tk.Label(bottom_frame, text="运行中", font=("Microsoft YaHei", 9), fg=self._colors['success'], bg=self._colors['bg_sidebar'])
        status_text.pack(side=tk.LEFT)

        # ========== 右侧主内容区 ==========
        content_frame = tk.Frame(main_container, bg=self._colors['bg'])
        content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._content_container = content_frame

        # 创建面板
        self._create_system_panel()
        self._create_games_panel()
        self._create_optimize_panel()
        self._create_nvidia_panel()
        self._create_services_panel()
        self._create_shortcuts_panel()
        self._create_settings_panel()

        # 默认显示系统状态
        self._switch_panel('system')

    def _on_nav_hover(self, btn, entering):
        """导航按钮悬停效果"""
        if btn._is_selected:
            return
        if entering:
            btn.config(bg=self._colors['bg_sidebar_item'], fg=self._colors['text'])
        else:
            btn.config(bg=self._colors['bg_sidebar'], fg=self._colors['text_secondary'])

    def _on_nav_click(self, nav_id):
        """导航按钮点击"""
        for id, btn in self._nav_buttons.items():
            btn._is_selected = (id == nav_id)
            if id == nav_id:
                btn.config(bg=self._colors['primary'], fg=self._colors['text_inverse'])
            else:
                btn.config(bg=self._colors['bg_sidebar'], fg=self._colors['text_secondary'])
        self._switch_panel(nav_id)

    def _switch_panel(self, panel_id):
        """切换面板"""
        for pid, panel in self._panels.items():
            if self._safe_widget_exists(panel):
                panel.pack_forget()
        
        if panel_id in self._panels and self._safe_widget_exists(self._panels[panel_id]):
            self._current_panel = panel_id
            self._panels[panel_id].pack(fill='both', expand=True)

    def _create_system_panel(self):
        """创建系统状态面板"""
        import tkinter as tk
        from tkinter import ttk

        panel = tk.Frame(self._content_container, bg=self._colors['bg'])

        # 标题
        title_frame = tk.Frame(panel, bg=self._colors['bg'])
        title_frame.pack(fill=tk.X, padx=25, pady=20)
        
        title = tk.Label(title_frame, text="系统状态", font=("Microsoft YaHei", 18, "bold"), fg=self._colors['text'], bg=self._colors['bg'])
        title.pack(anchor=tk.W)
        
        subtitle = tk.Label(title_frame, text="实时监控计算机性能指标", font=("Microsoft YaHei", 11), fg=self._colors['text_muted'], bg=self._colors['bg'])
        subtitle.pack(anchor=tk.W, pady=5)

        # 卡片网格
        grid_frame = tk.Frame(panel, bg=self._colors['bg'])
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 25))
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)

        # CPU卡片
        cpu_card = self._create_info_card(grid_frame, 0, 0, "CPU 使用率", "#0ea5e9")
        self.cpu_display = cpu_card['value_label']
        self.cpu_progress = cpu_card['progress']

        # 内存卡片
        mem_card = self._create_info_card(grid_frame, 0, 1, "内存使用率", "#10b981")
        self.mem_display = mem_card['value_label']
        self.mem_progress = mem_card['progress']

        # GPU卡片
        gpu_card = self._create_text_card(grid_frame, 1, 0, "GPU 信息", "#f59e0b")
        self.gpu_text = gpu_card['text_widget']

        # 磁盘卡片
        disk_card = self._create_text_card(grid_frame, 1, 1, "磁盘状态", "#ef4444")
        self.disk_text = disk_card['text_widget']

        self._panels['system'] = panel

    def _create_info_card(self, parent, row, col, title, accent_color):
        """创建数值信息卡片"""
        import tkinter as tk
        from tkinter import ttk

        card = tk.Frame(parent, bg=self._colors['bg_card'])
        card.grid(row=row, column=col, padx=12, pady=12, sticky='nsew')

        accent_bar = tk.Frame(card, bg=accent_color, height=3)
        accent_bar.pack(fill=tk.X)

        content = tk.Frame(card, bg=self._colors['bg_card'])
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        title_label = tk.Label(content, text=title, font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_card'])
        title_label.pack(anchor=tk.W)

        value_label = tk.Label(content, text="--%", font=("Consolas", 32, "bold"), fg=accent_color, bg=self._colors['bg_card'])
        value_label.pack(anchor=tk.W, pady=(10, 15))

        progress_frame = tk.Frame(content, bg=self._colors['bg_card'])
        progress_frame.pack(fill=tk.X)
        
        progress_bg = tk.Frame(progress_frame, bg=self._colors['bg'], height=6)
        progress_bg.pack(fill=tk.X)
        
        progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, length=200, mode='determinate')
        progress.pack(fill=tk.X)

        def on_enter(e):
            card.config(bg=self._colors['bg_card_hover'])
            content.config(bg=self._colors['bg_card_hover'])
            title_label.config(bg=self._colors['bg_card_hover'])
            value_label.config(bg=self._colors['bg_card_hover'])
            progress_frame.config(bg=self._colors['bg_card_hover'])

        def on_leave(e):
            card.config(bg=self._colors['bg_card'])
            content.config(bg=self._colors['bg_card'])
            title_label.config(bg=self._colors['bg_card'])
            value_label.config(bg=self._colors['bg_card'])
            progress_frame.config(bg=self._colors['bg_card'])

        card.bind('<Enter>', on_enter)
        card.bind('<Leave>', on_leave)

        return {'card': card, 'value_label': value_label, 'progress': progress}

    def _create_text_card(self, parent, row, col, title, accent_color):
        """创建文本信息卡片"""
        import tkinter as tk

        card = tk.Frame(parent, bg=self._colors['bg_card'])
        card.grid(row=row, column=col, padx=12, pady=12, sticky='nsew')

        accent_bar = tk.Frame(card, bg=accent_color, height=3)
        accent_bar.pack(fill=tk.X)

        content = tk.Frame(card, bg=self._colors['bg_card'])
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        title_label = tk.Label(content, text=title, font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_card'])
        title_label.pack(anchor=tk.W)

        text_widget = tk.Text(content, height=5, wrap='word', font=("Consolas", 10), 
                              bg=self._colors['bg_card'], fg=self._colors['text_secondary'],
                              borderwidth=0)
        text_widget.pack(fill=tk.BOTH, expand=True, pady=10)
        text_widget.config(state='disabled')

        def on_enter(e):
            card.config(bg=self._colors['bg_card_hover'])
            content.config(bg=self._colors['bg_card_hover'])
            title_label.config(bg=self._colors['bg_card_hover'])
            text_widget.config(bg=self._colors['bg_card_hover'])

        def on_leave(e):
            card.config(bg=self._colors['bg_card'])
            content.config(bg=self._colors['bg_card'])
            title_label.config(bg=self._colors['bg_card'])
            text_widget.config(bg=self._colors['bg_card'])

        card.bind('<Enter>', on_enter)
        card.bind('<Leave>', on_leave)

        return {'card': card, 'text_widget': text_widget}

    def _create_games_panel(self):
        """创建游戏检测面板"""
        import tkinter as tk

        panel = tk.Frame(self._content_container, bg=self._colors['bg'])

        title_frame = tk.Frame(panel, bg=self._colors['bg'])
        title_frame.pack(fill=tk.X, padx=25, pady=20)
        
        title = tk.Label(title_frame, text="游戏检测", font=("Microsoft YaHei", 18, "bold"), fg=self._colors['text'], bg=self._colors['bg'])
        title.pack(anchor=tk.W)
        
        subtitle = tk.Label(title_frame, text="自动识别并优化游戏进程", font=("Microsoft YaHei", 11), fg=self._colors['text_muted'], bg=self._colors['bg'])
        subtitle.pack(anchor=tk.W, pady=5)

        # 状态卡片
        status_card = tk.Frame(panel, bg=self._colors['bg_card'])
        status_card.pack(fill=tk.X, padx=25, pady=(0, 15))
        
        status_bar = tk.Frame(status_card, bg=self._colors['primary'], height=3)
        status_bar.pack(fill=tk.X)
        
        status_content = tk.Frame(status_card, bg=self._colors['bg_card'])
        status_content.pack(fill=tk.X, padx=16, pady=14)
        
        self.game_status_label = tk.Label(status_content, text="检测中...", font=("Microsoft YaHei", 14), fg=self._colors['text'], bg=self._colors['bg_card'])
        self.game_status_label.pack()

        # 游戏列表卡片
        list_card = tk.Frame(panel, bg=self._colors['bg_card'])
        list_card.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 15))
        
        list_bar = tk.Frame(list_card, bg=self._colors['success'], height=3)
        list_bar.pack(fill=tk.X)
        
        list_content = tk.Frame(list_card, bg=self._colors['bg_card'])
        list_content.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
        
        list_title = tk.Label(list_content, text="已检测游戏", font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_card'])
        list_title.pack(anchor=tk.W)
        
        self.game_list_text = tk.Text(list_content, height=8, wrap='word', font=("Consolas", 10),
                                      bg=self._colors['bg_card'], fg=self._colors['text_secondary'],
                                      borderwidth=0)
        self.game_list_text.pack(fill=tk.BOTH, expand=True, pady=10)
        self.game_list_text.config(state='disabled')

        # 按钮区域
        btn_frame = tk.Frame(panel, bg=self._colors['bg'])
        btn_frame.pack(fill=tk.X, padx=25, pady=15)

        opt_btn = self._create_button(btn_frame, "⚡ 优化游戏进程", "primary")
        opt_btn.pack(side=tk.LEFT, padx=5)
        opt_btn.bind('<Button-1>', lambda e: self._on_optimize_games())

        refresh_btn = self._create_button(btn_frame, "🔄 重新检测", "secondary")
        refresh_btn.pack(side=tk.LEFT, padx=5)
        refresh_btn.bind('<Button-1>', lambda e: self._refresh_games_status())

        self._panels['games'] = panel
        self._refresh_games_status()

    def _create_button(self, parent, text, style):
        """创建按钮"""
        import tkinter as tk

        colors = {
            'primary': {'bg': self._colors['primary'], 'hover': self._colors['primary_light'], 'fg': self._colors['text_inverse']},
            'secondary': {'bg': self._colors['bg_card'], 'hover': self._colors['bg_card_hover'], 'fg': self._colors['text']},
            'success': {'bg': self._colors['success'], 'hover': '#34d399', 'fg': self._colors['text_inverse']},
            'warning': {'bg': self._colors['warning'], 'hover': '#fbbf24', 'fg': self._colors['text_inverse']},
        }

        btn = tk.Label(
            parent,
            text=text,
            font=("Microsoft YaHei", 11),
            fg=colors[style]['fg'],
            bg=colors[style]['bg'],
            cursor='hand2',
            padx=20,
            pady=10
        )

        def on_enter(e):
            btn.config(bg=colors[style]['hover'])

        def on_leave(e):
            btn.config(bg=colors[style]['bg'])

        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)

        return btn

    def _refresh_games_status(self):
        """刷新游戏检测状态"""
        try:
            has_games = False
            game_list = []
            
            try:
                from process_priority_manager import APP
                if hasattr(APP, 'detect_games'):
                    has_games, game_list = APP.detect_games()
            except Exception:
                pass

            if has_games:
                self.game_status_label.config(text="🎮 检测到游戏运行", fg=self._colors['success'])
                game_text = "\n".join(f"✓ {game}" for game in game_list)
            else:
                self.game_status_label.config(text="⏳ 等待游戏启动", fg=self._colors['text_muted'])
                game_text = "暂无运行中的游戏"

            self.game_list_text.config(state='normal')
            self.game_list_text.delete(1.0, 'end')
            self.game_list_text.insert('end', game_text)
            self.game_list_text.config(state='disabled')

        except Exception as e:
            logger.error(f"刷新游戏状态失败: {e}")
            self.game_status_label.config(text="⚠️ 检测失败", fg=self._colors['danger'])
            self.game_list_text.config(state='normal')
            self.game_list_text.delete(1.0, 'end')
            self.game_list_text.insert('end', f"错误: {str(e)}")
            self.game_list_text.config(state='disabled')

    def _create_optimize_panel(self):
        """创建进程优化面板"""
        import tkinter as tk

        panel = tk.Frame(self._content_container, bg=self._colors['bg'])

        title_frame = tk.Frame(panel, bg=self._colors['bg'])
        title_frame.pack(fill=tk.X, padx=25, pady=20)
        
        title = tk.Label(title_frame, text="进程优化", font=("Microsoft YaHei", 18, "bold"), fg=self._colors['text'], bg=self._colors['bg'])
        title.pack(anchor=tk.W)
        
        subtitle = tk.Label(title_frame, text="智能调整进程优先级以提升性能", font=("Microsoft YaHei", 11), fg=self._colors['text_muted'], bg=self._colors['bg'])
        subtitle.pack(anchor=tk.W, pady=5)

        # 优化模式卡片
        mode_card = tk.Frame(panel, bg=self._colors['bg_card'])
        mode_card.pack(fill=tk.X, padx=25, pady=(0, 15))
        
        mode_bar = tk.Frame(mode_card, bg=self._colors['primary'], height=3)
        mode_bar.pack(fill=tk.X)
        
        mode_content = tk.Frame(mode_card, bg=self._colors['bg_card'])
        mode_content.pack(fill=tk.X, padx=16, pady=14)
        
        mode_title = tk.Label(mode_content, text="优化模式", font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_card'])
        mode_title.pack(anchor=tk.W, pady=(0, 12))

        self.optimize_mode = tk.StringVar(value='balanced')

        modes = [
            ('fast', '⚡ 快速优化', '适合游戏时使用'),
            ('balanced', '◈ 平衡优化', '综合优化，兼顾性能与稳定性'),
            ('thorough', '▣ 深度优化', '全面分析并优化所有进程')
        ]

        for mode_id, name, desc in modes:
            rb = tk.Radiobutton(
                mode_content,
                text=f"{name}  —  {desc}",
                variable=self.optimize_mode,
                value=mode_id,
                font=("Microsoft YaHei", 11),
                fg=self._colors['text'],
                bg=self._colors['bg_card'],
                selectcolor=self._colors['primary'],
                indicatoron=0,
                padx=15,
                pady=8
            )
            rb.pack(anchor=tk.W, pady=5)

        # 优化结果卡片
        result_card = tk.Frame(panel, bg=self._colors['bg_card'])
        result_card.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 15))
        
        result_bar = tk.Frame(result_card, bg=self._colors['success'], height=3)
        result_bar.pack(fill=tk.X)
        
        result_content = tk.Frame(result_card, bg=self._colors['bg_card'])
        result_content.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
        
        result_title = tk.Label(result_content, text="优化结果", font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_card'])
        result_title.pack(anchor=tk.W)
        
        self.optimize_log = tk.Text(result_content, height=8, wrap='word', font=("Consolas", 10),
                                    bg=self._colors['bg_card'], fg=self._colors['text_secondary'],
                                    borderwidth=0)
        self.optimize_log.pack(fill=tk.BOTH, expand=True, pady=10)

        # 按钮区域
        btn_frame = tk.Frame(panel, bg=self._colors['bg'])
        btn_frame.pack(fill=tk.X, padx=25, pady=15)

        run_btn = self._create_button(btn_frame, "⚡ 执行优化", "success")
        run_btn.pack(side=tk.LEFT, padx=5)
        run_btn.bind('<Button-1>', lambda e: self._on_run_optimize())

        restore_btn = self._create_button(btn_frame, "↩️ 恢复默认", "warning")
        restore_btn.pack(side=tk.LEFT, padx=5)
        restore_btn.bind('<Button-1>', lambda e: self._on_restore_priority())

        self._panels['optimize'] = panel

    def _on_run_optimize(self):
        """执行优化"""
        mode = self.optimize_mode.get()
        self.optimize_log.delete(1.0, 'end')
        self.optimize_log.insert('end', f"[{time.strftime('%H:%M:%S')}] 开始优化 (模式: {mode})...\n")
        
        if 'optimize' in self._callbacks:
            self._callbacks['optimize']()
        
        self.optimize_log.insert('end', f"[{time.strftime('%H:%M:%S')}] 优化完成\n")

    def _on_restore_priority(self):
        """恢复优先级"""
        if 'restore' in self._callbacks:
            self._callbacks['restore']()

    def _on_optimize_games(self):
        """优化游戏进程"""
        if 'optimize' in self._callbacks:
            self._callbacks['optimize']()
        self._refresh_games_status()

    def _create_nvidia_panel(self):
        """创建NVIDIA优化面板"""
        import tkinter as tk

        panel = tk.Frame(self._content_container, bg=self._colors['bg'])

        title_frame = tk.Frame(panel, bg=self._colors['bg'])
        title_frame.pack(fill=tk.X, padx=25, pady=20)
        
        title = tk.Label(title_frame, text="NVIDIA 优化", font=("Microsoft YaHei", 18, "bold"), fg=self._colors['text'], bg=self._colors['bg'])
        title.pack(anchor=tk.W)
        
        subtitle = tk.Label(title_frame, text="调整NVIDIA显卡设置以优化游戏性能", font=("Microsoft YaHei", 11), fg=self._colors['text_muted'], bg=self._colors['bg'])
        subtitle.pack(anchor=tk.W, pady=5)

        # 状态卡片
        status_card = tk.Frame(panel, bg=self._colors['bg_card'])
        status_card.pack(fill=tk.X, padx=25, pady=(0, 15))
        
        status_bar = tk.Frame(status_card, bg=self._colors['primary'], height=3)
        status_bar.pack(fill=tk.X)
        
        status_content = tk.Frame(status_card, bg=self._colors['bg_card'])
        status_content.pack(fill=tk.X, padx=16, pady=14)
        
        self.nvidia_status = tk.Label(status_content, text="检测中...", font=("Microsoft YaHei", 12), fg=self._colors['text'], bg=self._colors['bg_card'])
        self.nvidia_status.pack()

        # 预设卡片
        preset_card = tk.Frame(panel, bg=self._colors['bg_card'])
        preset_card.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 15))
        
        preset_bar = tk.Frame(preset_card, bg=self._colors['warning'], height=3)
        preset_bar.pack(fill=tk.X)
        
        preset_content = tk.Frame(preset_card, bg=self._colors['bg_card'])
        preset_content.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
        
        preset_title = tk.Label(preset_content, text="优化预设", font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_card'])
        preset_title.pack(anchor=tk.W, pady=(0, 12))

        presets = [
            ('low_latency', '⚡ 竞技低延迟', '最小化输入延迟'),
            ('balanced', '◈ 3A画质平衡', '平衡性能与画质'),
            ('quality', '▣ 画质优先', '最大化画质设置'),
            ('default', '↻ 恢复默认', '恢复NVIDIA默认设置')
        ]

        preset_frame = tk.Frame(preset_content, bg=self._colors['bg_card'])
        preset_frame.pack(fill=tk.X)

        for preset_id, name, desc in presets:
            btn = tk.Label(
                preset_frame,
                text=f"{name}\n{desc}",
                font=("Microsoft YaHei", 10),
                fg=self._colors['text'],
                bg=self._colors['bg'],
                cursor='hand2',
                padx=15,
                pady=12,
                anchor='w',
                justify='left'
            )
            btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
            btn.bind('<Button-1>', lambda e, p=preset_id: self._on_nvidia_preset(p))

        note_label = tk.Label(panel, text="⚠️ 优化前请关闭所有游戏程序", font=("Microsoft YaHei", 10), fg=self._colors['warning'], bg=self._colors['bg'])
        note_label.pack(pady=10, padx=25)

        self._panels['nvidia'] = panel

    def _on_nvidia_preset(self, preset):
        """NVIDIA预设优化"""
        if 'nvidia_optimize' in self._callbacks:
            self._callbacks['nvidia_optimize'](preset)

    def _create_services_panel(self):
        """创建服务状态面板"""
        import tkinter as tk
        from tkinter import ttk

        panel = tk.Frame(self._content_container, bg=self._colors['bg'])

        title_frame = tk.Frame(panel, bg=self._colors['bg'])
        title_frame.pack(fill=tk.X, padx=25, pady=20)
        
        title = tk.Label(title_frame, text="服务状态", font=("Microsoft YaHei", 18, "bold"), fg=self._colors['text'], bg=self._colors['bg'])
        title.pack(anchor=tk.W)
        
        subtitle = tk.Label(title_frame, text="查看和管理Windows系统服务", font=("Microsoft YaHei", 11), fg=self._colors['text_muted'], bg=self._colors['bg'])
        subtitle.pack(anchor=tk.W, pady=5)

        # 服务列表卡片
        list_card = tk.Frame(panel, bg=self._colors['bg_card'])
        list_card.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 15))
        
        list_bar = tk.Frame(list_card, bg=self._colors['primary'], height=3)
        list_bar.pack(fill=tk.X)
        
        list_content = tk.Frame(list_card, bg=self._colors['bg_card'])
        list_content.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        tree_frame = tk.Frame(list_content, bg=self._colors['bg_card'])
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.service_tree = ttk.Treeview(
            tree_frame,
            columns=('name', 'status', 'pid'),
            show='tree headings'
        )
        self.service_tree.heading('#0', text='显示名称')
        self.service_tree.heading('name', text='服务名称')
        self.service_tree.heading('status', text='状态')
        self.service_tree.heading('pid', text='PID')

        self.service_tree.column('#0', width=200)
        self.service_tree.column('name', width=150)
        self.service_tree.column('status', width=80, anchor='center')
        self.service_tree.column('pid', width=60, anchor='center')

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.service_tree.yview)
        self.service_tree.configure(yscrollcommand=scrollbar.set)

        self.service_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = tk.Frame(panel, bg=self._colors['bg'])
        btn_frame.pack(fill=tk.X, padx=25, pady=15)

        refresh_btn = self._create_button(btn_frame, "🔄 刷新服务", "secondary")
        refresh_btn.pack(side=tk.LEFT, padx=5)
        refresh_btn.bind('<Button-1>', lambda e: self._refresh_services_status_async())

        self._panels['services'] = panel
        self._refresh_services_status_async()

    def _refresh_services_status_async(self):
        """异步刷新服务状态"""
        def _fetch_services():
            try:
                from process_priority_manager import get_all_windows_services
                return get_all_windows_services()
            except Exception as e:
                logger.error(f"获取服务列表失败: {e}")
                return []

        def _update_service_tree(services):
            for item in self.service_tree.get_children():
                self.service_tree.delete(item)

            running = [s for s in services if s.get('status') == 'Running']
            stopped = [s for s in services if s.get('status') != 'Running']

            for svc in running[:20]:
                self.service_tree.insert('', 'end', 
                                        text=svc.get('display_name', ''),
                                        values=(svc.get('name', ''), '运行中', svc.get('pid', '-')),
                                        tags=('running',))

            for svc in stopped[:15]:
                self.service_tree.insert('', 'end',
                                        text=svc.get('display_name', ''),
                                        values=(svc.get('name', ''), '已停止', '-'),
                                        tags=('stopped',))

            self.service_tree.tag_configure('running', foreground=self._colors['success'])
            self.service_tree.tag_configure('stopped', foreground=self._colors['text_muted'])

        thread = threading.Thread(target=lambda: self.root.after(0, _update_service_tree, _fetch_services()), daemon=True)
        thread.start()

    def _create_shortcuts_panel(self):
        """创建快捷键面板"""
        import tkinter as tk

        panel = tk.Frame(self._content_container, bg=self._colors['bg'])

        title_frame = tk.Frame(panel, bg=self._colors['bg'])
        title_frame.pack(fill=tk.X, padx=25, pady=20)
        
        title = tk.Label(title_frame, text="快捷键", font=("Microsoft YaHei", 18, "bold"), fg=self._colors['text'], bg=self._colors['bg'])
        title.pack(anchor=tk.W)
        
        subtitle = tk.Label(title_frame, text="全局键盘快捷键，快速访问功能", font=("Microsoft YaHei", 11), fg=self._colors['text_muted'], bg=self._colors['bg'])
        subtitle.pack(anchor=tk.W, pady=5)

        shortcuts_card = tk.Frame(panel, bg=self._colors['bg_card'])
        shortcuts_card.pack(fill=tk.X, padx=25, pady=(0, 15))
        
        shortcuts_bar = tk.Frame(shortcuts_card, bg=self._colors['primary'], height=3)
        shortcuts_bar.pack(fill=tk.X)
        
        shortcuts_content = tk.Frame(shortcuts_card, bg=self._colors['bg_card'])
        shortcuts_content.pack(fill=tk.X, padx=16, pady=14)

        shortcuts = [
            ('Ctrl + Shift + O', '立即优化所有进程'),
            ('Ctrl + Shift + S', '显示系统状态'),
            ('Ctrl + Shift + G', '显示游戏进程'),
            ('Ctrl + Shift + R', '一键恢复优先级'),
            ('Ctrl + Shift + Q', '退出程序')
        ]

        for keys, desc in shortcuts:
            row = tk.Frame(shortcuts_content, bg=self._colors['bg_card'])
            row.pack(fill=tk.X, pady=8)
            
            key_label = tk.Label(row, text=keys, font=("Consolas", 11, "bold"), fg=self._colors['primary'], bg=self._colors['bg_card'])
            key_label.pack(side=tk.LEFT)
            
            arrow = tk.Label(row, text="→", fg=self._colors['text_muted'], bg=self._colors['bg_card'])
            arrow.pack(side=tk.LEFT, padx=15)
            
            desc_label = tk.Label(row, text=desc, font=("Microsoft YaHei", 11), fg=self._colors['text'], bg=self._colors['bg_card'])
            desc_label.pack(side=tk.LEFT)

        try:
            import keyboard
            available = True
        except ImportError:
            available = False

        status_frame = tk.Frame(panel, bg=self._colors['bg'])
        status_frame.pack(fill=tk.X, padx=25)

        if available:
            status_label = tk.Label(status_frame, text="✓ 快捷键功能已启用", font=("Microsoft YaHei", 11), fg=self._colors['success'], bg=self._colors['bg'])
        else:
            status_label = tk.Label(status_frame, text="⚠️ 快捷键功能未启用", font=("Microsoft YaHei", 11), fg=self._colors['warning'], bg=self._colors['bg'])
        status_label.pack(anchor=tk.W)

        install_hint = tk.Label(status_frame, text="安装命令: pip install keyboard", font=("Microsoft YaHei", 9), fg=self._colors['text_muted'], bg=self._colors['bg'])
        install_hint.pack(anchor=tk.W)

        self._panels['shortcuts'] = panel

    def _create_settings_panel(self):
        """创建设置面板"""
        import tkinter as tk
        from tkinter import ttk

        panel = tk.Frame(self._content_container, bg=self._colors['bg'])

        title_frame = tk.Frame(panel, bg=self._colors['bg'])
        title_frame.pack(fill=tk.X, padx=25, pady=20)
        
        title = tk.Label(title_frame, text="设置", font=("Microsoft YaHei", 18, "bold"), fg=self._colors['text'], bg=self._colors['bg'])
        title.pack(anchor=tk.W)
        
        subtitle = tk.Label(title_frame, text="自定义应用程序行为和外观", font=("Microsoft YaHei", 11), fg=self._colors['text_muted'], bg=self._colors['bg'])
        subtitle.pack(anchor=tk.W, pady=5)

        opt_card = tk.Frame(panel, bg=self._colors['bg_card'])
        opt_card.pack(fill=tk.X, padx=25, pady=(0, 15))
        
        opt_bar = tk.Frame(opt_card, bg=self._colors['primary'], height=3)
        opt_bar.pack(fill=tk.X)
        
        opt_content = tk.Frame(opt_card, bg=self._colors['bg_card'])
        opt_content.pack(fill=tk.X, padx=16, pady=14)
        
        opt_title = tk.Label(opt_content, text="优化设置", font=("Microsoft YaHei", 12, "bold"), fg=self._colors['text'], bg=self._colors['bg_card'])
        opt_title.pack(anchor=tk.W, pady=(0, 12))

        self.auto_optimize_var = tk.BooleanVar(value=True)
        auto_opt_check = tk.Checkbutton(
            opt_content,
            text="启用游戏自动优化",
            variable=self.auto_optimize_var,
            font=("Microsoft YaHei", 11),
            fg=self._colors['text'],
            bg=self._colors['bg_card'],
            selectcolor=self._colors['primary']
        )
        auto_opt_check.pack(anchor=tk.W, pady=5)

        cool_frame = tk.Frame(opt_content, bg=self._colors['bg_card'])
        cool_frame.pack(anchor=tk.W, pady=5)
        ttk.Label(cool_frame, text="优化冷却时间:", font=("Microsoft YaHei", 11)).pack(side=tk.LEFT)
        self.cool_time_var = tk.IntVar(value=5)
        cool_spin = ttk.Spinbox(cool_frame, from_=1, to=30, textvariable=self.cool_time_var, width=5)
        cool_spin.pack(side=tk.LEFT, padx=5)
        ttk.Label(cool_frame, text="分钟").pack(side=tk.LEFT)

        # 按钮区域
        btn_frame = tk.Frame(panel, bg=self._colors['bg'])
        btn_frame.pack(fill=tk.X, padx=25, pady=15)

        save_btn = self._create_button(btn_frame, "💾 保存设置", "primary")
        save_btn.pack(side=tk.RIGHT)
        save_btn.bind('<Button-1>', lambda e: self._on_save_settings())

        self._panels['settings'] = panel

    def _on_save_settings(self):
        """保存设置"""
        settings = {
            'auto_optimize': self.auto_optimize_var.get(),
            'cool_time': self.cool_time_var.get(),
        }

        try:
            from process_priority_manager import save_config, load_config
            config = load_config()
            config['gui_settings'] = settings
            save_config(config)
            self.show_message("设置保存成功", "设置已保存到配置文件")
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            self.show_message("保存失败", f"保存设置失败: {e}", type="error")

    def show_message(self, title, message, type="info"):
        """显示消息框"""
        try:
            from tkinter import messagebox

            if self.root:
                if type == "error":
                    messagebox.showerror(title, message, parent=self.root)
                elif type == "warning":
                    messagebox.showwarning(title, message, parent=self.root)
                else:
                    messagebox.showinfo(title, message, parent=self.root)
            else:
                import tkinter as tk
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

    def set_callback(self, name, callback):
        """设置回调函数"""
        self._callbacks[name] = callback


def show_quick_message(title, message, msg_type="info"):
    """显示快速消息提示框 - 供外部模块调用"""
    try:
        from tkinter import messagebox, Tk
        
        root = Tk()
        root.withdraw()
        
        if msg_type == "error":
            messagebox.showerror(title, message)
        elif msg_type == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showinfo(title, message)
        
        root.destroy()
    except Exception as e:
        safe_print(f"[{title}] {message}")


def get_main_window() -> MainWindow:
    """获取主窗口实例"""
    return MainWindow()