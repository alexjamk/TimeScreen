@echo off
chcp 1251 >nul
setlocal enabledelayedexpansion

REM TimeScreen Control - Installation Script
REM Must be run as Administrator

echo ============================================
echo   TimeScreen Control - Установка
echo ============================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Требуется запуск от имени администратора!
    echo Нажмите правой кнопкой на install.bat и выберите "Запуск от имени администратора"
    pause
    exit /b 1
)

echo [OK] Запущено от имени администратора
echo.

REM Set installation paths
set "INSTALL_DIR=%PROGRAMFILES%\TimeScreenControl"
set "CONFIG_DIR=%PROGRAMDATA%\TimeScreen"

echo Каталог установки: %INSTALL_DIR%
echo Каталог данных:    %CONFIG_DIR%
echo.

REM Check for existing service
echo Проверка существующей службы...
sc query TimeScreenControl >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Найдена существующая служба, остановка...
    sc stop TimeScreenControl >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete TimeScreenControl >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo [OK] Старая служба удалена
) else (
    echo [INFO] Существующая служба не найдена
)
echo.

REM Kill running instances
echo Завершение работающих процессов...
taskkill /F /IM TimeScreenControl.exe >nul 2>&1
taskkill /F /IM TimeScreenService.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Процессы завершены
) else (
    echo [INFO] Активных процессов не найдено
)
timeout /t 1 /nobreak >nul
echo.

REM Create directories
echo Создание каталогов...
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    if errorlevel 1 (
        echo [ERROR] Ошибка создания: %INSTALL_DIR%
        pause
        exit /b 1
    )
)
if not exist "%CONFIG_DIR%" (
    mkdir "%CONFIG_DIR%"
    if errorlevel 1 (
        echo [ERROR] Ошибка создания: %CONFIG_DIR%
        pause
        exit /b 1
    )
)
echo [OK] Каталоги созданы
echo.

REM Copy GUI EXE
echo Копирование TimeScreenControl.exe...
set COPY_RETRY=0
:COPY_LOOP
copy /Y "%~dp0TimeScreenControl.exe" "%INSTALL_DIR%\" >nul 2>&1
if errorlevel 1 (
    set /a COPY_RETRY+=1
    if !COPY_RETRY! leq 3 (
        echo [WARN] Файл заблокирован, попытка !COPY_RETRY!/3...
        timeout /t 2 /nobreak >nul
        taskkill /F /IM TimeScreenControl.exe >nul 2>&1
        goto COPY_LOOP
    ) else (
        echo [ERROR] Не удалось скопировать TimeScreenControl.exe
        pause
        exit /b 1
    )
)
echo [OK] TimeScreenControl.exe скопирован

REM Copy Service onedir
if exist "%~dp0TimeScreenService" (
    echo Копирование службы TimeScreenService...
    if exist "%INSTALL_DIR%\TimeScreenService" rmdir /s /q "%INSTALL_DIR%\TimeScreenService" 2>nul
    xcopy /E /I /Q /Y "%~dp0TimeScreenService" "%INSTALL_DIR%\TimeScreenService" >nul
    echo [OK] Служба скопирована
) else (
    echo [WARN] Папка TimeScreenService не найдена рядом с install.bat
    echo Служба НЕ будет установлена. Повторите сборку проекта.
)
echo.

REM Create start menu shortcut
echo Создание ярлыка в меню Пуск...
set "STARTMENU_DIR=%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"
mkdir "%STARTMENU_DIR%" 2>nul

echo Set WshShell = CreateObject^("WScript.Shell"^) > "%TEMP%\create_shortcut.vbs"
echo Set oLink = WshShell.CreateShortcut^("%STARTMENU_DIR%\Настройки TimeScreen.lnk"^) >> "%TEMP%\create_shortcut.vbs"
echo oLink.TargetPath = "%INSTALL_DIR%\TimeScreenControl.exe" >> "%TEMP%\create_shortcut.vbs"
echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> "%TEMP%\create_shortcut.vbs"
echo oLink.IconLocation = "%INSTALL_DIR%\TimeScreenControl.exe" >> "%TEMP%\create_shortcut.vbs"
echo oLink.Description = "Настройки родительского контроля TimeScreen" >> "%TEMP%\create_shortcut.vbs"
echo oLink.Save >> "%TEMP%\create_shortcut.vbs"
cscript //nologo "%TEMP%\create_shortcut.vbs" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Не удалось создать ярлык
)
del "%TEMP%\create_shortcut.vbs" 2>nul
echo [OK] Ярлык создан
echo.

REM Register Windows Service (onedir EXE - no PID change)
echo Регистрация службы Windows...
if exist "%INSTALL_DIR%\TimeScreenService\TimeScreenService.exe" (
    sc query TimeScreenControl >nul 2>&1
    if %errorlevel% equ 0 (
        echo [INFO] Служба уже существует, удаляем...
        sc stop TimeScreenControl >nul 2>&1
        timeout /t 2 /nobreak >nul
        sc delete TimeScreenControl >nul 2>&1
        timeout /t 2 /nobreak >nul
    )
    sc create TimeScreenControl binPath= "\"%INSTALL_DIR%\TimeScreenService\TimeScreenService.exe\"" start= auto DisplayName= "TimeScreen Control Service"
    if errorlevel 1 (
        echo [ERROR] Не удалось зарегистрировать службу
        pause
        exit /b 1
    )
    echo [OK] Служба зарегистрирована

    REM Start the service
    echo Запуск службы...
    sc start TimeScreenControl
    if errorlevel 1 (
        echo [WARN] Не удалось запустить службу автоматически
        echo Служба будет запущена при следующей перезагрузке
    ) else (
        echo [OK] Служба запущена
    )
) else (
    echo [WARN] TimeScreenService.exe не найден - служба не установлена
)
echo.

REM Create initial config
if not exist "%CONFIG_DIR%\pc_config.json" (
    echo Создание начальной конфигурации...
    echo {"enabled": false, "password_hash": "", "show_timer": true, "timer_position": "top-right", "controlled_users": [], "time_limits": {}} > "%CONFIG_DIR%\pc_config.json"
    echo [OK] Конфигурация создана
    echo.
    echo [INFO] При первом запуске настроек вам будет предложено
    echo       установить пароль администратора. Запомните его!
)
echo.

echo ============================================
echo   [OK] Установка завершена успешно!
echo ============================================
echo.
echo Для запуска настроек:
echo   - Используйте ярлык "Настройки TimeScreen" в меню Пуск
echo   - Или запустите "%INSTALL_DIR%\TimeScreenControl.exe"
echo.
echo Для включения защиты:
echo   1. Откройте настройки
echo   2. Установите пароль администратора (вкладка "Система")
echo   3. Добавьте пользователей и интервалы (вкладка "Настройки")
echo   4. Включите защиту
echo.
pause