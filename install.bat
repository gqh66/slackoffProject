@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   摸鱼神器 - 安装依赖
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo 没有找到 python，请先安装 Python 3.10+ 并勾选 Add to PATH。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo 创建虚拟环境失败。
        pause
        exit /b 1
    )
)

echo [2/3] 升级 pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -i https://mirrors.cloud.tencent.com/pypi/simple

echo [3/3] 安装依赖（约 300MB，请耐心等待）...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple

if errorlevel 1 (
    echo.
    echo 安装失败。可以试试换源：
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

echo.
echo 安装完成！双击 run.bat 启动，或双击「摸鱼神器.vbs」无窗口启动。
pause
