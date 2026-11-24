@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" dev.py %*
) else (
    python dev.py %*
)

if errorlevel 1 (
    echo.
    echo 热重载启动失败，请先运行 install.bat 安装依赖。
    pause
)
