@echo off
chcp 65001 >nul
echo ========================================
echo 智谱Token监控 - 启动脚本
echo ========================================
echo.

cd /d "E:\zhipu专用地"

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未检测到Python环境，请先安装Python
    pause
    exit /b 1
)

REM 检查主脚本是否存在
if not exist "zhipu_token_monitor.py" (
    echo 错误: 找不到主脚本 zhipu_token_monitor.py
    echo 请先运行 install_monitor.py 安装脚本
    pause
    exit /b 1
)

REM 检查依赖是否安装
python -c "import playwright, plyer" >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装依赖...
    python install_monitor.py
    if %errorlevel% neq 0 (
        echo 依赖安装失败
        pause
        exit /b 1
    )
)

echo 正在启动智谱Token监控...
echo.
echo 脚本将在后台运行，可以关闭此窗口
echo.

REM 启动监控脚本（隐藏窗口）
start /min pythonw zhipu_token_monitor.py

echo ✓ 智谱Token监控已启动
echo.
echo 使用 stop_monitor.bat 可以停止监控
echo 使用 check_status.bat 可以查看运行状态
echo.
pause