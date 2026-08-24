@echo off
chcp 1251 >nul
setlocal

set "ISCC_EXE="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC_EXE (
    echo [ERROR] Inno Setup 6 не найден.
    echo Установите: winget install --id JRSoftware.InnoSetup --exact
    exit /b 1
)

if not exist "%~dp0..\dist\Release\TimeScreenControl.exe" (
    echo [ERROR] Сначала соберите приложение через build.bat
    exit /b 1
)

if not exist "%~dp0..\dist\Release\TimeScreenService\TimeScreenService.exe" (
    echo [ERROR] Служба не найдена в dist\Release
    exit /b 1
)

"%ISCC_EXE%" "%~dp0TimeScreenControl.iss"
if errorlevel 1 exit /b 1

echo [OK] Графический установщик собран в dist\Installer
exit /b 0
