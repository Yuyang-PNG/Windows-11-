@echo off
chcp 65001 >nul
echo ========================================
echo   智优进程管理器 v1.2.0 打包脚本
echo ========================================
echo.

echo [1/4] 清理旧的打包文件...
if exist "dist\智优进程管理器" rmdir /s /q "dist\智优进程管理器"
if exist "build" rmdir /s /q "build"

echo [2/4] 开始打包...
pyinstaller build_exe.spec --clean --noconfirm

echo [3/4] 复制额外文件...
if exist "dist\智优进程管理器" (
    copy /y "README.md" "dist\智优进程管理器\"
    copy /y "AGENTS.md" "dist\智优进程管理器\"
    echo 配置文件已包含在打包中
)

echo [4/4] 打包完成!
echo.
echo 输出目录: dist\智优进程管理器
echo 主程序: dist\智优进程管理器\智优进程管理器.exe
echo.
echo 使用方法:
echo   1. 将 dist\智优进程管理器 目录复制到目标电脑
echo   2. 以管理员身份运行 智优进程管理器.exe
echo.
pause