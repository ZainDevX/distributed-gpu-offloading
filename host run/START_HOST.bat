@echo off
REM ============================================================================
REM One-Click Colorful Launcher for Distributed GPU Offloading - Host Server
REM Course: CSC-334 Parallel and Distributed Computing
REM ============================================================================

title Distributed GPU Offloading - Host Worker Server
cd /d "%~dp0"

REM Enable ANSI VT100 Escape sequences in Windows Command Prompt
reg query HKCU\Console /v VirtualTerminalLevel >nul 2>&1
if %errorlevel% neq 0 (
    reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1
)

echo.
echo ============================================================================
echo   DISTRIBUTED GPU TASK OFFLOADING - HOST WORKER DAEMON BOOTSTRAP
echo ============================================================================
echo.

REM Verify Python is installed and available in PATH
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in your system PATH!
    echo.
    echo Please install Python 3.9+ from https://www.python.org/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

REM Run the colorful automated host server launcher
python run_host.py %*

if %errorlevel% neq 0 (
    echo.
    echo [!] Host Server encountered an error or exited with code: %errorlevel%
    pause
)
