@echo off
chcp 65001 >nul
echo ========================================
echo 智谱Token监控 - 状态检查
echo ========================================
echo.

cd /d "E:\zhipu专用地"

set RUNNING=0

REM 检查pythonw.exe进程
tasklist /FI "IMAGENAME eq pythonw.exe" | find "pythonw.exe" >nul
if %errorlevel% equ 0 (
    set RUNNING=1
)

REM 检查python.exe监控进程
wmic process where "name='python.exe'" get commandline 2>nul | find "zhipu_token_monitor" >nul
if %errorlevel% equ 0 (
    set RUNNING=1
)

if %RUNNING% equ 1 (
    echo ✓ 监控脚本正在运行
    echo.
    echo 进程信息:
    tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find "pythonw.exe"
    tasklist /FI "IMAGENAME eq python.exe" 2>nul | find "python.exe"
    echo.
    echo 日志文件: token_monitor.log
    echo.
    echo 最近日志:
    if exist token_monitor.log (
        powershell -command "Get-Content token_monitor.log -Tail 10"
    ) else (
        echo 日志文件不存在
    )
) else (
    echo ✗ 监控脚本未运行
    echo.
    echo 使用 start_monitor.bat 启动监控
)

echo.
pause