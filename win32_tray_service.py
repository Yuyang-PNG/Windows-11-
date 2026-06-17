"""
Windows API 托盘服务实现
"""
import win32api
import win32con
import win32gui
import win32process
import win32security
import sys
import time

# 托盘图标常量
NIF_ICON = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_TIP = 0x00000004
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
WM_USER = 0x0400

class Win32TrayIcon:
    def __init__(self, app_name, app_version):
        self.app_name = app_name
        self.app_version = app_version
        self.hwnd = None
        self.hicon = None
        self.running = True
        
    def create_window(self):
        """创建消息窗口"""
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self.wnd_proc
        wc.lpszClassName = "PriorityManagerTrayClass"
        wc.hInstance = win32api.GetModuleHandle(None)
        
        try:
            win32gui.RegisterClass(wc)
        except:
            pass  # 类已存在
        
        self.hwnd = win32gui.CreateWindowEx(
            0,
            "PriorityManagerTrayClass",
            "PriorityManagerWindow",
            0,
            0, 0, 0, 0,
            0, 0,
            win32api.GetModuleHandle(None),
            None
        )
        
    def create_icon(self):
        """创建图标"""
        # 使用系统默认图标 - IDI_INFORMATION = 0x00000040
        IDI_INFORMATION = 64  # 0x40
        self.hicon = win32gui.LoadIcon(0, IDI_INFORMATION)
            
    def add_to_tray(self):
        """添加到系统托盘"""
        tip_text = f"{self.app_name} {self.app_version}\n智能游戏优化已启用"
        
        nid = (
            self.hwnd,
            0,
            NIF_ICON | NIF_MESSAGE | NIF_TIP,
            WM_USER + 1,
            self.hicon,
            tip_text
        )
        
        win32gui.Shell_NotifyIcon(NIM_ADD, nid)
        print(f"{self.app_name} 已添加到系统托盘")
        
    def show_menu(self):
        """显示右键菜单"""
        menu = win32gui.CreatePopupMenu()
        
        # 添加菜单项
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "查看状态")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 2, "查看游戏")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 3, "立即优化")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 4, "NVIDIA一键优化")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 5, "查看服务")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 6, "退出")

        # 获取鼠标位置
        x, y = win32api.GetCursorPos()

        # 设置前景窗口
        win32gui.SetForegroundWindow(self.hwnd)

        # 显示菜单
        selection = win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD,
            x, y,
            0,
            self.hwnd,
            None
        )

        # 处理选择
        if selection == 1:
            self.on_view_status()
        elif selection == 2:
            self.on_view_games()
        elif selection == 3:
            self.on_optimize()
        elif selection == 4:
            self.on_nvidia_optimize()
        elif selection == 5:
            self.on_view_services()
        elif selection == 6:
            self.on_exit()
            
        win32gui.DestroyMenu(menu)
        
    def on_view_status(self):
        """查看状态"""
        print("查看状态")
        try:
            from process_priority_manager import show_status
            show_status()
        except Exception as e:
            self.show_message("错误", f"查看状态失败: {e}")
            
    def on_view_games(self):
        """查看游戏"""
        print("查看游戏")
        try:
            from process_priority_manager import show_games
            show_games()
        except Exception as e:
            self.show_message("错误", f"查看游戏失败: {e}")
            
    def on_optimize(self):
        """立即优化"""
        print("立即优化")
        try:
            from process_priority_manager import run_optimization
            run_optimization()
        except Exception as e:
            self.show_message("错误", f"优化失败: {e}")

    def on_nvidia_optimize(self):
        """NVIDIA一键优化"""
        print("NVIDIA一键优化")
        try:
            from process_priority_manager import run_nvidia_optimization
            run_nvidia_optimization(preset_name="low_latency")
        except Exception as e:
            self.show_message("错误", f"NVIDIA 优化失败: {e}")

    def on_view_services(self):
        """查看服务"""
        print("查看服务")
        try:
            from process_priority_manager import show_services
            show_services()
        except Exception as e:
            self.show_message("错误", f"查看服务失败: {e}")
            
    def on_exit(self):
        """退出"""
        print("退出程序")
        self.running = False
        
    def show_message(self, title, message):
        """显示消息框"""
        win32api.MessageBox(self.hwnd, message, title, win32con.MB_OK)
        
    def wnd_proc(self, hwnd, msg, wparam, lparam):
        """窗口消息处理"""
        if msg == WM_USER + 1:
            if lparam == win32con.WM_RBUTTONUP:
                self.show_menu()
            elif lparam == win32con.WM_LBUTTONDBLCLK:
                self.on_view_status()
                
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    
    def run(self):
        """运行托盘服务"""
        self.create_window()
        self.create_icon()
        self.add_to_tray()
        
        print(f"{self.app_name} {self.app_version} 已启动")
        print("右键点击托盘图标查看菜单")
        
        # 消息循环
        msg = win32gui.MSG()
        while self.running:
            if win32gui.PeekMessage(msg, 0, 0, 0, win32con.PM_REMOVE):
                win32gui.TranslateMessage(msg)
                win32gui.DispatchMessage(msg)
            else:
                time.sleep(0.1)
        
        # 清理
        nid = (self.hwnd, 0, 0, 0, 0, "")
        win32gui.Shell_NotifyIcon(NIM_DELETE, nid)
        win32gui.DestroyWindow(self.hwnd)
        print("程序已退出")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--tray":
        tray = Win32TrayIcon("智优进程管理器", "v1.1.0")
        tray.run()

if __name__ == "__main__":
    main()