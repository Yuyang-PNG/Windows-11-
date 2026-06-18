@echo off
chcp 65001 >nul
title Smart Process Priority Manager Installer

setlocal enabledelayedexpansion

echo ================================================
echo      智优进程管理器 - 自解压安装程序
echo ================================================
echo.

set "TARGET_DIR=%ProgramFiles%\智优进程管理器"
set "SOURCE_DIR=dist\智优进程管理器"

echo 目标目录: %TARGET_DIR%
echo.

if exist "%TARGET_DIR%" (
    echo 检测到已安装，正在更新...
) else (
    echo 创建安装目录...
    mkdir "%TARGET_DIR%"
)

echo 正在复制文件...
xcopy /E /I /Y "%SOURCE_DIR%" "%TARGET_DIR%"

if %errorlevel% equ 0 (
    echo.
    echo 安装成功！
    echo.
    echo 已安装到: %TARGET_DIR%
    echo.
    echo 创建快捷方式...
    
    set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\智优进程管理器.lnk"
    powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%TARGET_DIR%\智优进程管理器.exe'; $Shortcut.WorkingDirectory = '%TARGET_DIR%'; $Shortcut.Save()"
    
    echo.
    echo 快捷方式已创建到开始菜单
    echo.
    echo 启动程序？[Y/N]
    set "CHOICE="
    set /P CHOICE=输入选择: 
    if /I "!CHOICE!"=="Y" (
        start "" "%TARGET_DIR%\智优进程管理器.exe"
    )
) else (
    echo 安装失败！
    pause
    exit /b 1
)