"""
简单的托盘测试脚本
"""
import pystray
from PIL import Image, ImageDraw
import sys

def on_click(icon, item):
    print(f"点击: {item}")
    if str(item) == "退出":
        icon.stop()
        sys.exit(0)

# 创建一个简单的图标
image = Image.new('RGB', (64, 64), color=(80, 150, 220))
draw = ImageDraw.Draw(image)
draw.ellipse([10, 10, 54, 54], fill=(120, 180, 240))
draw.rectangle([25, 20, 39, 44], fill=(80, 150, 220))

# 创建菜单
menu = pystray.Menu(
    pystray.MenuItem("测试", on_click),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("退出", on_click)
)

# 创建图标
icon = pystray.Icon(
    name="TestTray",
    icon=image,
    title="测试托盘"
)
icon.menu = menu

print("托盘图标启动中...")
icon.run()