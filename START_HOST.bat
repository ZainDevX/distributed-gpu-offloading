@echo off
REM Root shortcut launcher for Host
cd /d "%~dp0host run"
call START_HOST.bat %*
