@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ════════════════════════════════════════════
echo   TimeScreen Control - Сборка в EXE
echo ════════════════════════════════════════════
echo.

REM Check if PyInstaller is installed
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Установка PyInstaller...
    python -m pip install pyinstaller
)

echo.
echo 📦 Сборка исполняемого файла...
echo.

REM Create dist directory
if not exist "dist" mkdir dist

REM Run PyInstaller with all necessary options
pyinstaller --noconfirm --clean ^
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
    echo ❌ Ошибка сборки!
    pause
    exit /b 1
)

echo.
echo ✅ Сборка завершена успешно!
echo.
echo Исполняемый файл: dist\TimeScreenControl.exe
echo.

REM Copy install scripts to dist
echo Копирование скриптов установки...
copy "install\install.bat" "dist\" >nul
copy "install\uninstall.bat" "dist\" >nul
echo ✅ Скрипты скопированы в dist\

echo.
echo ════════════════════════════════════════════
echo   Готово к распространению!
echo ════════════════════════════════════════════
echo.
echo Для установки:
echo   1. Скопируйте папку dist на целевой компьютер
echo   2. Запустите install.bat от имени администратора
echo.

pause
