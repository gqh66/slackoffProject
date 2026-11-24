@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
) else (
    python main.py %*
)

if errorlevel 1 (
    echo.
    echo 启动失败。如果提示缺少模块，请先运行 install.bat 安装依赖。
    pause
)
