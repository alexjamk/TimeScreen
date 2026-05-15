@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM TimeScreen Control - Uninstallation Script
REM Must be run as Administrator

echo ════════════════════════════════════════════
echo   TimeScreen Control - Удаление
echo ════════════════════════════════════════════
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ Требуется запуск от имени администратора!
    pause
    exit /b 1
)

echo ✅ Запущено от имени администратора
echo.

REM Kill any running instances first
echo Завершение работающих процессов...
taskkill /F /IM TimeScreenControl.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Процессы завершены
) else (
    echo ℹ️ Активных процессов не найдено
)
timeout /t 1 /nobreak >nul
echo.

REM Stop and remove service - try both service names
echo Остановка и удаление службы...

REM Try TimeScreenControl first (correct name)
sc query TimeScreenControl >nul 2>&1
if %errorlevel% equ 0 (
    echo ℹ️ Найдена служба TimeScreenControl, остановка...
    sc stop TimeScreenControl >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete TimeScreenControl >nul 2>&1
    if errorlevel 1 (
        echo ⚠️ Не удалось удалить службу TimeScreenControl
    ) else (
        timeout /t 2 /nobreak >nul
        echo ✅ Служба TimeScreenControl удалена
    )
) else (
    echo ℹ️ Служба TimeScreenControl не найдена
)

REM Also try old name TimeScreenService for compatibility
sc query TimeScreenService >nul 2>&1
if %errorlevel% equ 0 (
    echo ℹ️ Найдена служба TimeScreenService, остановка...
    sc stop TimeScreenService >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete TimeScreenService >nul 2>&1
    if errorlevel 1 (
        echo ⚠️ Не удалось удалить службу TimeScreenService
    ) else (
        timeout /t 2 /nobreak >nul
        echo ✅ Служба TimeScreenService удалена
    )
) else (
    echo ℹ️ Служба TimeScreenService не найдена
)
echo.

REM Set paths
set "PROGRAMFILES=%PROGRAMFILES%"
set "INSTALL_DIR=%PROGRAMFILES%\TimeScreenControl"
set "PROGRAMDATA=%PROGRAMDATA%"
set "CONFIG_DIR=%PROGRAMDATA%\TimeScreen"

REM Remove start menu shortcuts - both locations
echo Удаление ярлыков...
set "STARTMENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"
set "STARTMENU_DIR_ALL=%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"

if exist "%STARTMENU_DIR%" (
    rmdir /s /q "%STARTMENU_DIR%"
    echo ✅ Ярлыки пользователя удалены
) else (
    echo ℹ️ Ярлыки пользователя не найдены
)

if exist "%STARTMENU_DIR_ALL%" (
    rmdir /s /q "%STARTMENU_DIR_ALL%"
    echo ✅ Общие ярлыки удалены
) else (
    echo ℹ️ Общие ярлыки не найдены
)
echo.

REM Remove installation directory
echo Удаление файлов программы...
if exist "%INSTALL_DIR%" (
    rmdir /s /q "%INSTALL_DIR%"
    echo ✅ Файлы программы удалены
) else (
    echo ℹ️ Каталог программы не найден
)
echo.

REM Ask about config preservation - default to N for clean uninstall
echo ════════════════════════════════════════════
echo.
set /p preserve="Сохранить конфигурацию (настройки пользователей)? (Y/N): "
if /i "!preserve!"=="Y" (
    echo ℹ️ Конфигурация сохранена в %CONFIG_DIR%
    echo    При следующей установке настройки будут восстановлены
) else (
    if exist "%CONFIG_DIR%" (
        REM Try to delete, but don't fail if in use
        rmdir /s /q "%CONFIG_DIR%" 2>nul
        if errorlevel 1 (
            echo ⚠️ Не удалось удалить конфигурацию (файл может быть открыт)
            echo    Удалите вручную: %CONFIG_DIR%
        ) else (
            echo ✅ Конфигурация удалена
        )
    ) else (
        echo ℹ️ Конфигурация не найдена
    )
)
echo.

echo ════════════════════════════════════════════
echo   ✅ Удаление завершено!
echo ════════════════════════════════════════════
echo.
echo Если вы планируете переустановку:
echo   - Выберите Y для сохранения настроек
echo   - Выберите N для полного сброса
echo.
pause
