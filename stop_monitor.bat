@echo off
chcp 65001 >nul
echo ========================================
echo 智谱Token监控 - 停止脚本
echo ========================================
echo.

cd /d "E:\zhipu专用地"

echo 正在查找运行中的监控进程...
echo.

REM 查找Python进程并停止
tasklist /FI "IMAGENAME eq pythonw.exe" | find "pythonw.exe" >nul
if %errorlevel% equ 0 (
    echo 找到运行中的监控进程，正在停止...
    taskkill /F /IM pythonw.exe >nul 2>&1
    echo ✓ 监控进程已停止
) else (
    echo 未找到运行中的监控进程
)

REM 也检查正常Python进程
tasklist /FI "IMAGENAME eq python.exe" | find "python.exe" >nul
if %errorlevel% equ 0 (
    REM 检查是否是监控脚本
    wmic process where "name='python.exe'" get commandline | find "zhipu_token_monitor" >nul
    if %errorlevel% equ 0 (
        echo 正在停止Python监控进程...
        for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" ^| find "python.exe"') do (
            taskkill /F /PID %%i >nul 2>&1
        )
        echo ✓ 监控进程已停止
    )
)

echo.
echo 停止操作完成
echo.
pause