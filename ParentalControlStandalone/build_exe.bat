@echo off
echo ============================================
echo   Создание standalone .exe файла
echo   (не требует установленного Python)
echo ============================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Требуется запуск от имени администратора!
    pause
    exit /b 1
)

echo [1/3] Проверка наличия Python...
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo ОШИБКА: Python не найден!
    echo Для создания .exe файла необходим Python с установленным pip
    echo.
    echo Установите Python с https://www.python.org/downloads/
    echo Не забудьте отметить "Add Python to PATH"
    pause
    exit /b 1
)

echo Python найден
python --version

echo.
echo [2/3] Установка PyInstaller...
echo Это необходимо только для создания .exe файла
pip install pyinstaller --quiet

if errorlevel 1 (
    echo Ошибка установки PyInstaller!
    echo Попробуйте вручную: pip install pyinstaller
    pause
    exit /b 1
)

echo.
echo [3/3] Создание .exe файла...
pyinstaller --onefile ^
    --name "ParentalControl" ^
    --icon=NONE ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.messagebox ^
    --add-data "README.md;." ^
    parental_control.py

if errorlevel 1 (
    echo Ошибка создания .exe файла!
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Готово!
echo ============================================
echo.
echo Standalone файл создан:
echo   dist\ParentalControl.exe
echo.
echo Этот файл можно запускать на любом компьютере
echo с Windows БЕЗ установленного Python!
echo.
echo СЛЕДУЮЩИЕ ШАГИ:
echo 1. Скопируйте ParentalControl.exe в нужную папку
echo 2. Запустите от имени администратора с параметром admin:
echo    ParentalControl.exe admin
echo 3. Настройте пароль и расписание
echo 4. Установите службу:
echo    ParentalControl.exe install
echo.
echo Или просто запустите create_installer.bat
echo для создания полного установочного пакета.
echo.
pause
