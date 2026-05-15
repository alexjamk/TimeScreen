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
REM Using python -m PyInstaller as requested
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
    echo ❌ Ошибка сборки!
    pause
    exit /b 1
)

echo.
echo ✅ Сборка завершена успешно!
echo.
echo Исполняемый файл: dist\TimeScreenControl.exe
echo.

REM Create distribution package for end users
echo Подготовка пакета для распространения...
if not exist "dist\Release" mkdir "dist\Release"

REM Copy EXE to Release folder
copy "dist\TimeScreenControl.exe" "dist\Release\" >nul

REM Copy install scripts to Release folder
copy "install\install.bat" "dist\Release\" >nul
copy "install\uninstall.bat" "dist\Release\" >nul

REM Copy README
copy "README.md" "dist\Release\" >nul

echo.
echo ✅ Пакет для распространения готов в dist\Release\
echo.
echo ════════════════════════════════════════════
echo   Готово к распространению!
echo ════════════════════════════════════════════
echo.
echo Для установки на компьютере пользователя:
echo   1. Скопируйте ВСЁ содержимое папки dist\Release
echo   2. На целевом компьютере запустите install.bat
echo      ОТ ИМЕНИ АДМИНИСТРАТОРА
echo.
echo Содержимое пакета:
echo   - TimeScreenControl.exe  (программа)
echo   - install.bat            (установка)
echo   - uninstall.bat          (удаление)
echo   - README.md              (документация)
echo.

pause
