@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 setup_local.py
) else (
    python setup_local.py
)
pause
