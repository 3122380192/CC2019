@echo off
title ACC2019
cd /d "%~dp0"

:: Uu tien ban exe neu da build (them --src de chay Python source)
if exist "%~dp0dist\ACC2019\ACC2019.exe" (
    if /I "%~1"=="--src" goto :run_src
    start "" "%~dp0dist\ACC2019\ACC2019.exe"
    exit /b 0
)

:run_src
python -m pip install -r requirements.txt -q 2>nul
python acc2019.py

if errorlevel 1 (
    echo.
    echo [!] Loi khoi chay. Kiem tra Python da cai chua.
    pause
)
