@echo off
chcp 1251 >nul
setlocal enabledelayedexpansion

REM TimeScreen Control - Uninstallation Script
REM Must be run as Administrator

echo ============================================
echo   TimeScreen Control - Удаление
echo ============================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Требуется запуск от имени администратора!
    pause
    exit /b 1
)

echo [OK] Запущено от имени администратора
echo.

REM Kill any running instances first
echo Завершение работающих процессов...
taskkill /F /IM TimeScreenControl.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Процессы завершены
) else (
    echo [INFO] Активных процессов не найдено
)
timeout /t 1 /nobreak >nul
echo.

REM Stop and remove service
echo Остановка и удаление службы...
sc query TimeScreenControl >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Найдена служба TimeScreenControl, остановка...
    sc stop TimeScreenControl >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete TimeScreenControl >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Не удалось удалить службу TimeScreenControl
    ) else (
        timeout /t 2 /nobreak >nul
        echo [OK] Служба TimeScreenControl удалена
    )
) else (
    echo [INFO] Служба TimeScreenControl не найдена
)
sc query TimeScreenService >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Найдена служба TimeScreenService, остановка...
    sc stop TimeScreenService >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete TimeScreenService >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Не удалось удалить службу TimeScreenService
    ) else (
        timeout /t 2 /nobreak >nul
        echo [OK] Служба TimeScreenService удалена
    )
) else (
    echo [INFO] Служба TimeScreenService не найдена
)
echo.

REM Set paths
set "INSTALL_DIR=%PROGRAMFILES%\TimeScreenControl"
set "CONFIG_DIR=%PROGRAMDATA%\TimeScreen"

REM Remove start menu shortcuts
echo Удаление ярлыков...
set "STARTMENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"
set "STARTMENU_DIR_ALL=%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"
if exist "%STARTMENU_DIR%" (
    rmdir /s /q "%STARTMENU_DIR%"
    echo [OK] Ярлыки пользователя удалены
) else (
    echo [INFO] Ярлыки пользователя не найдены
)
if exist "%STARTMENU_DIR_ALL%" (
    rmdir /s /q "%STARTMENU_DIR_ALL%"
    echo [OK] Общие ярлыки удалены
) else (
    echo [INFO] Общие ярлыки не найдены
)
echo.

REM Remove installation directory
echo Удаление файлов программы...
if exist "%INSTALL_DIR%" (
    rmdir /s /q "%INSTALL_DIR%"
    echo [OK] Файлы программы удалены
) else (
    echo [INFO] Каталог программы не найден
)
echo.

REM Ask about config preservation
echo ============================================
echo.
set /p preserve="Сохранить конфигурацию (настройки пользователей)? (Y/N): "
if /i "!preserve!"=="Y" (
    echo [INFO] Конфигурация сохранена в %CONFIG_DIR%
    echo       При следующей установке настройки будут восстановлены
) else (
    if exist "%CONFIG_DIR%" (
        rmdir /s /q "%CONFIG_DIR%" 2>nul
        if errorlevel 1 (
            echo [WARN] Не удалось удалить конфигурацию (файл может быть открыт)
            echo       Удалите вручную: %CONFIG_DIR%
        ) else (
            echo [OK] Конфигурация удалена
        )
    ) else (
        echo [INFO] Конфигурация не найдена
    )
)
echo.

echo ============================================
echo   [OK] Удаление завершено!
echo ============================================
echo.
echo Если вы планируете переустановку:
echo   - Выберите Y для сохранения настроек
echo   - Выберите N для полного сброса
echo.
pause