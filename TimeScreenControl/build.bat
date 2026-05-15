@echo off
chcp 1251 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   TimeScreen Control - Сборка
echo ============================================
echo.

REM Check if PyInstaller is installed
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Установка PyInstaller...
    python -m pip install pyinstaller
)

REM Create dist directory
if not exist "dist" mkdir dist
if not exist "dist\Release" mkdir "dist\Release"

REM --------------------------------------------------
REM [1/2] Build GUI EXE (onefile, windowed, with icon)
REM --------------------------------------------------
echo.
echo [1/2] Сборка GUI (TimeScreenControl.exe)...
python -m PyInstaller --noconfirm --clean ^
    --name "TimeScreenControl" ^
    --icon "src/resources/icon.ico" ^
    --add-data "src/config;config" ^
    --add-data "src/gui;gui" ^
    --add-data "src/service;service" ^
    --add-data "src/utils;utils" ^
    --add-data "src/resources;resources" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import bcrypt ^
    --onefile ^
    --windowed ^
    src/main.py

if errorlevel 1 (
    echo [ERROR] Ошибка сборки GUI!
    pause
    exit /b 1
)
echo [OK] GUI собран

REM Fix spec for windowed (PyInstaller may overwrite)
python -c "import re; f=open('TimeScreenControl.spec','r+'); c=f.read(); f.seek(0); f.write(c.replace('console=True','console=False')); f.close()"

REM --------------------------------------------------
REM [2/2] Build Service EXE (onedir - REQUIRED for SCM)
REM --------------------------------------------------
echo.
echo [2/2] Сборка службы (TimeScreenService)...
python -m PyInstaller --noconfirm --clean ^
    --name "TimeScreenService" ^
    --add-data "src/config;config" ^
    --add-data "src/service;service" ^
    --add-data "src/utils;utils" ^
    --hidden-import win32serviceutil ^
    --hidden-import win32service ^
    --hidden-import win32event ^
    --hidden-import servicemanager ^
    --hidden-import bcrypt ^
    --onedir ^
    src/service_entry.py

if errorlevel 1 (
    echo [ERROR] Ошибка сборки службы!
    pause
    exit /b 1
)
echo [OK] Служба собрана

REM --------------------------------------------------
REM Prepare Release package
REM --------------------------------------------------
echo.
echo Подготовка пакета для распространения...

REM Copy GUI EXE
copy "dist\TimeScreenControl.exe" "dist\Release\" >nul

REM Copy Service onedir
if exist "dist\Release\TimeScreenService" rmdir /s /q "dist\Release\TimeScreenService" 2>nul
xcopy /E /I /Q /Y "dist\TimeScreenService" "dist\Release\TimeScreenService" >nul

REM Copy install scripts and README
copy "install\install.bat" "dist\Release\" >nul
copy "install\uninstall.bat" "dist\Release\" >nul
copy "README.md" "dist\Release\" >nul

echo [OK] Пакет готов

echo.
echo ============================================
echo   Сборка завершена!
echo ============================================
echo.
echo Состав пакета (dist\Release\):
echo   - TimeScreenControl.exe     (GUI, onefile)
echo   - TimeScreenService\        (Служба, onedir)
echo   - install.bat               (Установка)
echo   - uninstall.bat             (Удаление)
echo   - README.md                 (Документация)
echo.
echo Для установки:
echo   1. Скопируйте ВСЮ папку dist\Release на целевой ПК
echo   2. Запустите install.bat от имени Администратора
echo.
pause
