@echo off
chcp 1251 >nul
setlocal enabledelayedexpansion

REM Use unique staging paths so stale/locked PyInstaller artifacts cannot break a build
set "PYI_ROOT=%TEMP%\TimeScreenBuild_%RANDOM%_%RANDOM%"
set "PYI_WORK=%PYI_ROOT%\work"
set "PYI_DIST=%PYI_ROOT%\dist"
set "PYI_SPEC=%PYI_ROOT%\spec"
mkdir "%PYI_WORK%" "%PYI_DIST%" "%PYI_SPEC%" >nul 2>&1

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

REM Create distribution directory
if not exist "dist" mkdir dist

REM --------------------------------------------------
REM [1/2] Build GUI EXE (onefile, windowed, with icon)
REM --------------------------------------------------
echo.
echo [1/2] Сборка GUI (TimeScreenControl.exe)...
python -m PyInstaller --noconfirm --clean ^
    --workpath "%PYI_WORK%" ^
    --distpath "%PYI_DIST%" ^
    --specpath "%PYI_SPEC%" ^
    --name "TimeScreenControl" ^
    --icon "%CD%\src\resources\icon.ico" ^
    --add-data "%CD%\src\config;config" ^
    --add-data "%CD%\src\gui;gui" ^
    --add-data "%CD%\src\service;service" ^
    --add-data "%CD%\src\utils;utils" ^
    --add-data "%CD%\src\resources;resources" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import bcrypt ^
    --onefile ^
    --windowed ^
    "%CD%\src\main.py"

if errorlevel 1 (
    echo [ERROR] Ошибка сборки GUI!
    pause
    exit /b 1
)
echo [OK] GUI собран

REM --------------------------------------------------
REM [2/2] Build Service EXE (onedir - REQUIRED for SCM)
REM --------------------------------------------------
echo.
echo [2/2] Сборка службы (TimeScreenService)...
python -m PyInstaller --noconfirm --clean ^
    --workpath "%PYI_WORK%" ^
    --distpath "%PYI_DIST%" ^
    --specpath "%PYI_SPEC%" ^
    --name "TimeScreenService" ^
    --add-data "%CD%\src\config;config" ^
    --add-data "%CD%\src\service;service" ^
    --add-data "%CD%\src\utils;utils" ^
    --hidden-import win32serviceutil ^
    --hidden-import win32service ^
    --hidden-import win32event ^
    --hidden-import win32ts ^
    --hidden-import win32api ^
    --hidden-import win32con ^
    --hidden-import win32process ^
    --hidden-import win32profile ^
    --hidden-import win32pipe ^
    --hidden-import win32file ^
    --hidden-import win32security ^
    --hidden-import ntsecuritycon ^
    --hidden-import pywintypes ^
    --hidden-import servicemanager ^
    --hidden-import bcrypt ^
    --onedir ^
    "%CD%\src\service_entry.py"

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

if exist "dist\Release" goto RELEASE_READY
mkdir "dist\Release" >nul 2>&1
if errorlevel 1 goto RELEASE_ERROR
:RELEASE_READY

REM Copy GUI EXE
copy "%PYI_DIST%\TimeScreenControl.exe" "dist\Release\" >nul

REM Copy Service onedir
xcopy /E /I /Q /Y "%PYI_DIST%\TimeScreenService" "dist\Release\TimeScreenService" >nul

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
rmdir /s /q "%PYI_ROOT%" >nul 2>&1
pause
exit /b 0

:RELEASE_ERROR
echo [ERROR] Не удалось подготовить dist\Release
exit /b 1
