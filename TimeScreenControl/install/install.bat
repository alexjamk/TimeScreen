@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM TimeScreen Control - Installation Script
REM Must be run as Administrator
REM Works with pre-built EXE from developer

echo ════════════════════════════════════════════
echo   TimeScreen Control - Установка
echo ════════════════════════════════════════════
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ Требуется запуск от имени администратора!
    echo Нажмите правой кнопкой на install.bat и выберите "Запуск от имени администратора"
    pause
    exit /b 1
)

echo ✅ Запущено от имени администратора
echo.

REM Set installation paths
set "PROGRAMFILES=%PROGRAMFILES%"
set "INSTALL_DIR=%PROGRAMFILES%\TimeScreenControl"
set "PROGRAMDATA=%PROGRAMDATA%"
set "CONFIG_DIR=%PROGRAMDATA%\TimeScreen"

echo 📁 Каталог установки: %INSTALL_DIR%
echo 📁 Каталог данных: %CONFIG_DIR%
echo.

REM Create directories
echo Создание каталогов...
mkdir "%INSTALL_DIR%" 2>nul
mkdir "%CONFIG_DIR%" 2>nul
if errorlevel 1 (
    echo ❌ Ошибка создания каталогов
    pause
    exit /b 1
)
echo ✅ Каталоги созданы
echo.

REM Copy EXE and scripts
echo Копирование файлов программы...
copy /Y "%~dp0TimeScreenControl.exe" "%INSTALL_DIR%\" >nul
if errorlevel 1 (
    echo ❌ Ошибка копирования TimeScreenControl.exe
    echo Убедитесь, что exe-файл находится в той же папке, что и install.bat
    pause
    exit /b 1
)
echo ✅ Файлы скопированы
echo.

REM Create start menu shortcut using PowerShell (more reliable)
echo Создание ярлыка в меню Пуск...
set "STARTMENU_DIR=%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"
mkdir "%STARTMENU_DIR%" 2>nul

powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTMENU_DIR%\Настройки TimeScreen.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\TimeScreenControl.exe'; $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; $Shortcut.IconLocation = '%INSTALL_DIR%\TimeScreenControl.exe'; $Shortcut.Description = 'Настройки родительского контроля TimeScreen'; $Shortcut.Save()"
if errorlevel 1 (
    echo ⚠️ Не удалось создать ярлык через PowerShell, пробуем VBS...
    echo Set WshShell = CreateObject("WScript.Shell") > "%TEMP%\create_shortcut.vbs"
    echo Set oLink = WshShell.CreateShortcut("%STARTMENU_DIR%\Настройки TimeScreen.lnk") >> "%TEMP%\create_shortcut.vbs"
    echo oLink.TargetPath = "%INSTALL_DIR%\TimeScreenControl.exe" >> "%TEMP%\create_shortcut.vbs"
    echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> "%TEMP%\create_shortcut.vbs"
    echo oLink.IconLocation = "%INSTALL_DIR%\TimeScreenControl.exe" >> "%TEMP%\create_shortcut.vbs"
    echo oLink.Description = "Настройки родительского контроля TimeScreen" >> "%TEMP%\create_shortcut.vbs"
    echo oLink.Save >> "%TEMP%\create_shortcut.vbs"
    cscript //nologo "%TEMP%\create_shortcut.vbs"
    del "%TEMP%\create_shortcut.vbs"
)
echo ✅ Ярлык создан
echo.

REM Register Windows Service using Python module
echo Регистрация службы Windows...
"%INSTALL_DIR%\TimeScreenControl.exe" --service install
if errorlevel 1 (
    echo ⚠️ Не удалось зарегистрировать службу через exe
    echo Попробуйте переустановить программу
    pause
    exit /b 1
)
echo ✅ Служба зарегистрирована

REM Configure service to start automatically
sc config TimeScreenControl start= auto >nul
if errorlevel 1 (
    echo ⚠️ Не удалось настроить автозапуск службы
)

REM Start the service
echo Запуск службы...
sc start TimeScreenControl
if errorlevel 1 (
    echo ⚠️ Не удалось запустить службу автоматически
    echo Служба будет запущена при следующей перезагрузке
    echo Или запустите вручную через services.msc
    echo Код ошибки: %errorlevel%
) else (
    echo ✅ Служба запущена
)
echo.

REM Create initial config if not exists
if not exist "%CONFIG_DIR%\pc_config.json" (
    echo Создание начальной конфигурации...
    echo {"enabled": false, "password_hash": "", "show_timer": true, "timer_position": "top-right", "controlled_users": [], "time_limits": {}} > "%CONFIG_DIR%\pc_config.json"
    echo ✅ Конфигурация создана
    echo.
    echo ⚠️ ВНИМАНИЕ: При первом запуске настроек вам будет предложено
    echo    установить пароль администратора. Запомните его!
)
echo.

echo ════════════════════════════════════════════
echo   ✅ Установка завершена успешно!
echo ════════════════════════════════════════════
echo.
echo Для запуска настроек:
echo   - Используйте ярлык "Настройки TimeScreen" в меню Пуск
echo   - Или запустите "%INSTALL_DIR%\TimeScreenControl.exe"
echo.
echo Служба установлена и запущена.
echo Защита АКТИВНА только если включена в настройках программы.
echo.
echo Для включения защиты:
echo   1. Откройте настройки
echo   2. Установите пароль администратора (если ещё не установлен)
echo   3. На вкладке "Общие" включите "Включить защиту"
echo   4. Добавьте пользователей и настройте интервалы
echo.
pause
