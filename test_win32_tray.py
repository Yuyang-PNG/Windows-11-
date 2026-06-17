"""
简化的Windows API托盘图标测试
"""
import win32api
import win32con
import win32gui

class TrayIcon:
    def __init__(self):
        self.hwnd = None
        self.hicon = None
        self.nid = None
        
    def create_icon(self):
        """创建托盘图标"""
        # 注册窗口类
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self.wnd_proc
        wc.lpszClassName = "SimpleTrayClass"
        wc.hInstance = win32api.GetModuleHandle(None)
        try:
            win32gui.RegisterClass(wc)
        except:
            pass  # 类已存在
        
        # 创建窗口
        self.hwnd = win32gui.CreateWindowEx(
            0,
            "SimpleTrayClass",
            "TrayWindow",
            0,
            0, 0, 0, 0,
            0, 0,
            win32api.GetModuleHandle(None),
            None
        )
        
        # 使用系统自带图标
        self.hicon = win32gui.LoadIcon(0, win32con.IDI_INFORMATION)
        
        # 创建NOTIFYICONDATA
        self.nid = (
            self.hwnd,
            0,
            win32con.NIF_ICON | win32con.NIF_MESSAGE | win32con.NIF_TIP,
            win32con.WM_USER + 1,
            self.hicon,
            "智优进程管理器 v1.1.0\n智能游戏优化已启用"
        )
        
        # 添加托盘图标
        win32gui.Shell_NotifyIcon(win32con.NIM_ADD, self.nid)
        print("托盘图标已创建，请检查系统托盘区域")
        
    def wnd_proc(self, hwnd, msg, wparam, lparam):
        """窗口消息处理"""
        if msg == win32con.WM_USER + 1:
            if lparam == win32con.WM_RBUTTONUP:
                self.show_menu()
            elif lparam == win32con.WM_LBUTTONDBLCLK:
                print("双击托盘")
                
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    
    def show_menu(self):
        """显示右键菜单"""
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "查看状态")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 2, "退出")
        
        x, y = win32api.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        selection = win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD,
            x, y, 0, self.hwnd, None
        )
        
        if selection == 2:
            self.destroy()
            
        win32gui.DestroyMenu(menu)
        
    def destroy(self):
        """销毁托盘图标"""
        win32gui.Shell_NotifyIcon(win32con.NIM_DELETE, self.nid)
        win32gui.DestroyWindow(self.hwnd)
        print("托盘图标已销毁")
        
    def run(self):
        """运行消息循环"""
        self.create_icon()
        msg = win32gui.MSG()
        while win32gui.GetMessage(msg, 0, 0, 0) > 0:
            win32gui.TranslateMessage(msg)
            win32gui.DispatchMessage(msg)

if __name__ == "__main__":
    try:
        tray = TrayIcon()
        tray.run()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()