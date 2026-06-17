@echo off
chcp 65001 >nul
echo 正在启动智优进程管理器...
echo 提示: 如果遇到安全警告，请在Windows安全中心添加排除项
echo.

cd /d "%~dp0"

python "%~dp0process_priority_manager.py" --console

pause