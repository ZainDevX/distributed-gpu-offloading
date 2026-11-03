@echo off
title Build Standalone Client and Host Packages (.exe)
cd /d "%~dp0"
python scripts\build_packages.py
pause

