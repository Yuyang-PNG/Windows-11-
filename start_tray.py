"""
独立的托盘服务启动器
"""
import subprocess
import sys
import os

def run_tray_standalone():
    """在独立进程中启动托盘服务"""
    script_path = os.path.join(os.path.dirname(__file__), 'tray_standalone.py')
    
    # 创建独立的托盘脚本
    tray_script = '''
import pystray
from PIL import Image, ImageDraw
import sys
import time
import threading

APP_DISPLAY_NAME = "智优进程管理器"
APP_VERSION = "v1.1.0"

def create_tray_icon():
    """创建托盘图标"""
    width = 64
    height = 64
    image = Image.new("RGB", (width, height), color=(80, 150, 220))
    draw = ImageDraw.Draw(image)
    draw.ellipse([10, 10, 54, 54], fill=(120, 180, 240))
    draw.rectangle([25, 20, 39, 44], fill=(80, 150, 220))
    return image

def show_status():
    """显示状态"""
    def _show():
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("状态", f"{APP_DISPLAY_NAME} {APP_VERSION}\\n运行中")
            root.destroy()
        except:
            print("显示状态")
    
    t = threading.Thread(target=_show, daemon=True)
    t.start()

def on_tray_click(icon, item):
    """菜单点击处理"""
    item_str = str(item)
    if item_str == "查看状态":
        show_status()
    elif item_str == "NVIDIA一键优化":
        try:
            from process_priority_manager import run_nvidia_optimization
            run_nvidia_optimization(preset_name="low_latency")
        except Exception as e:
            print(f"NVIDIA 优化失败: {e}")
    elif item_str == "退出":
        icon.stop()
        sys.exit(0)

def main():
    # 创建图标
    icon_image = create_tray_icon()
    
    # 创建菜单
    menu = pystray.Menu(
        pystray.MenuItem("查看状态", on_tray_click),
        pystray.MenuItem("NVIDIA一键优化", on_tray_click),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_tray_click)
    )
    
    # 创建托盘图标
    icon = pystray.Icon(
        name=APP_DISPLAY_NAME,
        icon=icon_image,
        title=f"{APP_DISPLAY_NAME} {APP_VERSION}\\n智能游戏优化已启用"
    )
    icon.menu = menu
    
    print(f"{APP_DISPLAY_NAME} {APP_VERSION} 已启动")
    icon.run()

if __name__ == "__main__":
    main()
'''
    
    # 写入独立脚本
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(tray_script)
    
    # 在单独进程中运行
    subprocess.Popen([sys.executable, script_path], 
                     stdout=subprocess.PIPE, 
                     stderr=subprocess.PIPE,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    
    print("智优进程管理器 v1.1.0 托盘服务已启动")

if __name__ == "__main__":
    run_tray_standalone()