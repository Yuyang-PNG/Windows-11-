"""
托盘图标测试脚本
"""
import pystray
from PIL import Image, ImageDraw
import sys

def on_click(icon, item):
    print(f"点击: {item}")
    if str(item) == "退出":
        icon.stop()
        sys.exit(0)

# 创建图标
width = 64
height = 64
image = Image.new('RGB', (width, height), color=(80, 150, 220))
draw = ImageDraw.Draw(image)

# 绘制CPU图标
draw.ellipse([8, 8, 56, 56], fill=(60, 120, 200))
draw.rectangle([12, 12, 18, 52], fill=(100, 160, 230))
draw.rectangle([28, 16, 36, 48], fill=(100, 160, 230))
draw.rectangle([46, 12, 52, 52], fill=(100, 160, 230))
draw.ellipse([26, 26, 38, 38], fill=(160, 200, 250))

# 创建菜单
menu = pystray.Menu(
    pystray.MenuItem("测试", on_click),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("退出", on_click)
)

# 创建托盘图标
icon = pystray.Icon(
    name="TestTray",
    icon=image,
    title="智优进程管理器 v1.1.0"
)
icon.menu = menu

print("托盘图标启动中...")
icon.run()