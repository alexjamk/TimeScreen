@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM TimeScreen Control - Installation Script
REM Must be run as Administrator

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

REM Copy files
echo Копирование файлов...
xcopy /E /Y /I "%~dp0..\src" "%INSTALL_DIR%\src" >nul
xcopy /Y "%~dp0..\requirements.txt" "%INSTALL_DIR\" >nul
if errorlevel 1 (
    echo ❌ Ошибка копирования файлов
    pause
    exit /b 1
)
echo ✅ Файлы скопированы
echo.

REM Install Python dependencies
echo Установка зависимостей Python...
cd /d "%INSTALL_DIR%"
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo ⚠️ Предупреждение: Не удалось установить зависимости
    echo Проверьте, что Python установлен и доступен в PATH
)
echo.

REM Create start menu shortcut
echo Создание ярлыка в меню Пуск...
set "STARTMENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\TimeScreen Control"
mkdir "%STARTMENU_DIR%" 2>nul

REM Create settings shortcut
echo Set WshShell = CreateObject("WScript.Shell") > "%TEMP%\create_shortcut.vbs"
echo Set oLink = WshShell.CreateShortcut("%STARTMENU_DIR%\Настройки.lnk") >> "%TEMP%\create_shortcut.vbs"
echo oLink.TargetPath = "%INSTALL_DIR%\src\main.py" >> "%TEMP%\create_shortcut.vbs"
echo oLink.WorkingDirectory = "%INSTALL_DIR%\src" >> "%TEMP%\create_shortcut.vbs"
echo oLink.IconLocation = "%INSTALL_DIR%\src\resources\icon.ico" >> "%TEMP%\create_shortcut.vbs"
echo oLink.Description = "Настройки TimeScreen Control" >> "%TEMP%\create_shortcut.vbs"
echo oLink.Save >> "%TEMP%\create_shortcut.vbs"
cscript //nologo "%TEMP%\create_shortcut.vbs"
del "%TEMP%\create_shortcut.vbs"
echo ✅ Ярлык создан
echo.

REM Register Windows Service
echo Регистрация службы Windows...
sc create TimeScreenService binPath= "\"%INSTALL_DIR%\src\python.exe\" \"%INSTALL_DIR%\src\main.py\" --service" start= auto DisplayName= "TimeScreen Control Service"
if errorlevel 1 (
    echo ⚠️ Служба не зарегистрирована (возможно Python не найден)
    echo Попытка регистрации с использованием python из PATH...
    sc create TimeScreenService binPath= "python \"%INSTALL_DIR%\src\main.py\" --service" start= auto DisplayName= "TimeScreen Control Service"
    if errorlevel 1 (
        echo ⚠️ Не удалось зарегистрировать службу
        echo Зарегистрируйте службу вручную после установки Python
    ) else (
        echo ✅ Служба зарегистрирована (через PATH)
    )
) else (
    echo ✅ Служба зарегистрирована
)

REM Start the service
echo Запуск службы...
sc start TimeScreenService
if errorlevel 1 (
    echo ⚠️ Не удалось запустить службу автоматически
    echo Запустите службу вручную через services.msc
) else (
    echo ✅ Служба запущена
)
echo.

REM Create initial config if not exists
if not exist "%CONFIG_DIR%\pc_config.json" (
    echo Создание начальной конфигурации...
    echo {"enabled": true, "show_timer": true, "controlled_users": []} > "%CONFIG_DIR%\pc_config.json"
    echo ✅ Конфигурация создана
)
echo.

echo ════════════════════════════════════════════
echo   ✅ Установка завершена успешно!
echo ════════════════════════════════════════════
echo.
echo Для запуска настроек:
echo   - Используйте ярлык в меню Пуск
echo   - Или запустите "%INSTALL_DIR%\src\main.py"
echo.
echo Служба запущена и активна.
echo Активность защиты настраивается в настройках программы.
echo.
pause
