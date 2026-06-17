"""
托盘图标测试脚本
"""
import pystray
from PIL import Image, ImageDraw
import time

def on_click(icon, item):
    print(f"菜单点击: {item}")
    if str(item) == "退出":
        icon.stop()

# 创建一个简单的图标
image = Image.new('RGB', (64, 64), color=(80, 150, 220))
draw = ImageDraw.Draw(image)

# 绘制一个简单的图案
draw.ellipse([10, 10, 54, 54], fill=(120, 180, 240))
draw.rectangle([25, 20, 39, 44], fill=(80, 150, 220))

# 创建菜单
menu = pystray.Menu(
    pystray.MenuItem("查看状态", on_click),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("退出", on_click)
)

# 创建托盘图标
icon = pystray.Icon(
    name="测试托盘",
    icon=image,
    title="测试托盘图标\n智能游戏优化已启用"
)
icon.menu = menu

print("托盘图标启动中...")
print("请检查系统托盘区域")
print("按 Ctrl+C 退出")

# 运行托盘
try:
    icon.run()
except KeyboardInterrupt:
    icon.stop()
    print("托盘已退出")