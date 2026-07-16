@echo off
setlocal EnableExtensions
title ACC2019 — Build EXE
cd /d "%~dp0"

echo ============================================
echo  ACC2019 Build (PyInstaller onedir)
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [!] Chua cai Python hoac chua co trong PATH.
    pause
    exit /b 1
)

echo [1/3] Cai dependency + PyInstaller...
python -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [!] pip install that bai.
    pause
    exit /b 1
)

echo [2/3] Build ACC2019.exe ...
python -m PyInstaller ACC2019.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [!] Build that bai. Xem log o tren.
    pause
    exit /b 1
)

echo.
echo [3/3] Xong.
echo.
echo  Thu muc:  %~dp0dist\ACC2019\
echo  Chay:     %~dp0dist\ACC2019\ACC2019.exe
echo.
echo  Luu y:
echo   - Config/history luu canh file .exe
echo   - Thu muc Adobe installer / Photoshop_Imports dat canh .exe neu can cai
echo   - KHONG copy folder Adobe zip (rat nang) vao dist
echo.
explorer "%~dp0dist\ACC2019"
pause
