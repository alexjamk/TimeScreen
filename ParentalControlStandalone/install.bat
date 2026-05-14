@echo off
echo ============================================
echo   Установка Родительского контроля
echo ============================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Требуется запуск от имени администратора!
    echo Нажмите правой кнопкой на этом файле и выберите "Запуск от имени администратора"
    pause
    exit /b 1
)

echo [1/4] Проверка наличия Python...
where python >nul 2>&1
if %errorLevel% equ 0 (
    echo Python найден
    set PYTHON_CMD=python
) else (
    echo Python не найден в системе!
    echo.
    echo ВАЖНО: Для работы программы необходим Python 3.8+
    echo Скачайте установщик с официального сайта: https://www.python.org/downloads/
    echo.
    echo При установке Python обязательно отметьте галочку:
    echo   [X] Add Python to PATH
    echo.
    pause
    exit /b 1
)

echo.
echo [2/4] Копирование файлов программы...
set INSTALL_DIR=%PROGRAMFILES%\ParentalControl
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

copy /Y "parental_control.py" "%INSTALL_DIR%\" >nul
if errorlevel 1 (
    echo Ошибка копирования файлов!
    pause
    exit /b 1
)

echo.
echo [3/4] Создание ярлыков...

REM Ярлык для панели администратора
set SHORTCUT_VBS=%TEMP%\create_shortcut.vbs
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%SHORTCUT_VBS%"
echo sLinkFile = "%USERPROFILE%\Desktop\Родительский контроль - Админ.lnk" >> "%SHORTCUT_VBS%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%SHORTCUT_VBS%"
echo oLink.TargetPath = "python" >> "%SHORTCUT_VBS%"
echo oLink.Arguments = "\"%INSTALL_DIR%\parental_control.py\" admin" >> "%SHORTCUT_VBS%"
echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> "%SHORTCUT_VBS%"
echo oLink.Description = "Панель администратора" >> "%SHORTCUT_VBS%"
echo oLink.Save >> "%SHORTCUT_VBS%"
cscript //nologo "%SHORTCUT_VBS%"

REM Ярлык для запуска службы вручную
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%SHORTCUT_VBS%"
echo sLinkFile = "%USERPROFILE%\Desktop\Родительский контроль - Старт.lnk" >> "%SHORTCUT_VBS%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%SHORTCUT_VBS%"
echo oLink.TargetPath = "python" >> "%SHORTCUT_VBS%"
echo oLink.Arguments = "\"%INSTALL_DIR%\parental_control.py\" start" >> "%SHORTCUT_VBS%"
echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> "%SHORTCUT_VBS%"
echo oLink.Description = "Запустить службу" >> "%SHORTCUT_VBS%"
echo oLink.Save >> "%SHORTCUT_VBS%"
cscript //nologo "%SHORTCUT_VBS%"

del "%SHORTCUT_VBS%"

echo.
echo [4/4] Установка службы Windows...
cd /d "%INSTALL_DIR%"
python parental_control.py install

echo.
echo ============================================
echo   Установка завершена!
echo ============================================
echo.
echo На рабочем столе созданы ярлыки:
echo   - Родительский контроль - Админ (настройка)
echo   - Родительский контроль - Старт (ручной запуск)
echo.
echo СЛЕДУЮЩИЕ ШАГИ:
echo 1. Запустите "Родительский контроль - Админ"
echo 2. Установите пароль администратора
echo 3. Добавьте разрешенные временные интервалы
echo.
echo Служба автоматически запущена и работает!
echo.
pause
