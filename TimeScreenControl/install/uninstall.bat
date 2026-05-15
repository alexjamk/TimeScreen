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

REM Stop and remove service
echo Остановка и удаление службы...
sc stop TimeScreenService >nul 2>&1
timeout /t 3 /nobreak >nul
sc delete TimeScreenService >nul 2>&1
if errorlevel 1 (
    echo ℹ️ Служба не найдена или уже удалена
) else (
    timeout /t 2 /nobreak >nul
    echo ✅ Служба удалена
)
echo.

REM Set paths
set "PROGRAMFILES=%PROGRAMFILES%"
set "INSTALL_DIR=%PROGRAMFILES%\TimeScreenControl"
set "PROGRAMDATA=%PROGRAMDATA%"
set "CONFIG_DIR=%PROGRAMDATA%\TimeScreen"

REM Remove start menu shortcuts
echo Удаление ярлыков...
set "STARTMENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"
if exist "%STARTMENU_DIR%" (
    rmdir /s /q "%STARTMENU_DIR%"
    echo ✅ Ярлыки удалены
) else (
    echo ℹ️ Ярлыки не найдены
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

REM Ask about config preservation
echo ════════════════════════════════════════════
echo.
set /p preserve="Сохранить конфигурацию (настройки пользователей)? (Y/N): "
if /i "!preserve!"=="Y" (
    echo ℹ️ Конфигурация сохранена в %CONFIG_DIR%
    echo    При следующей установке настройки будут восстановлены
) else (
    if exist "%CONFIG_DIR%" (
        rmdir /s /q "%CONFIG_DIR%"
        echo ✅ Конфигурация удалена
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
