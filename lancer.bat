@echo off
setlocal
cd /d "%~dp0"
python lancer.py %*
if errorlevel 1 pause
