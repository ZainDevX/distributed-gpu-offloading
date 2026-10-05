@echo off
REM Root shortcut launcher for Client
cd /d "%~dp0client run"
call START_CLIENT.bat %*
