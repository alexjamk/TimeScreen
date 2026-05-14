@echo off
echo ============================================
echo   Создание полного установочного пакета
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

echo [1/4] Проверка наличия Python...
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo ОШИБКА: Python не найден!
    echo Для создания .exe файла необходим Python
    echo.
    echo Установите Python с https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Python найден

echo.
echo [2/4] Установка PyInstaller...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo Ошибка установки PyInstaller!
    pause
    exit /b 1
)

echo.
echo [3/4] Создание .exe файла...
pyinstaller --onefile ^
    --name "ParentalControl" ^
    --icon=NONE ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.messagebox ^
    parental_control.py

if errorlevel 1 (
    echo Ошибка создания .exe файла!
    pause
    exit /b 1
)

echo.
echo [4/4] Создание установочного пакета...

set PACKAGE_DIR=ParentalControl_Installer
if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"

REM Копируем .exe файл
copy /Y "dist\ParentalControl.exe" "%PACKAGE_DIR%\"

REM Создаем упрощенный install.bat для .exe версии
(
echo @echo off
echo echo ============================================
echo echo   Установка Родительского контроля
echo echo ============================================
echo echo.
echo.
echo REM Проверка прав администратора
echo net session ^>nul 2^>^&^1
echo if %%errorLevel%% neq 0 ^(
echo     echo Требуется запуск от имени администратора!
echo     echo Нажмите правой кнопкой на этом файле и выберите "Запуск от имени администратора"
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo [1/2] Копирование файлов программы...
echo set INSTALL_DIR=%%PROGRAMFILES%%\\ParentalControl
echo if not exist "%%INSTALL_DIR%%" mkdir "%%INSTALL_DIR%%"
echo.
echo copy /Y "ParentalControl.exe" "%%INSTALL_DIR%%\\" ^>nul
echo copy /Y "README.md" "%%INSTALL_DIR%%\\" ^>nul 2^>nul
echo if errorlevel 1 ^(
echo     echo Ошибка копирования файлов!
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo [2/2] Установка службы Windows...
echo cd /d "%%INSTALL_DIR%%"
echo ParentalControl.exe install
echo.
echo echo ============================================
echo echo   Установка завершена!
echo echo ============================================
echo echo.
echo echo На рабочем столе созданы ярлыки для управления.
echo echo.
echo echo СЛЕДУЮЩИЕ ШАГИ:
echo echo 1. Запустите ParentalControl.exe admin
echo echo 2. Установите пароль администратора
echo echo 3. Добавьте разрешенные временные интервалы
echo echo.
echo pause
) > "%PACKAGE_DIR%\install.bat"

REM Создаем uninstall.bat для .exe версии
(
echo @echo off
echo echo ============================================
echo echo   Удаление Родительского контроля
echo echo ============================================
echo echo.
echo net session ^>nul 2^>^&^1
echo if %%errorLevel%% neq 0 ^(
echo     echo Требуется запуск от имени администратора!
echo     pause
echo     exit /b 1
echo ^)
echo.
echo set INSTALL_DIR=%%PROGRAMFILES%%\\ParentalControl
echo.
echo echo [1/2] Удаление службы...
echo cd /d "%%INSTALL_DIR%%"
echo if exist "ParentalControl.exe" ^(
echo     ParentalControl.exe uninstall
echo ^) else ^(
echo     sc stop ParentalControlService ^>nul 2^>^&^1
echo     timeout /t 2 ^>nul
echo     sc delete ParentalControlService ^>nul 2^>^&^1
echo ^)
echo.
echo echo [2/2] Удаление файлов...
echo if exist "%%INSTALL_DIR%%" ^(
echo     rmdir /s /q "%%INSTALL_DIR%%"
echo     echo Файлы удалены
echo ^)
echo.
echo del "%%USERPROFILE%%\\Desktop\\Родительский контроль*.lnk" 2^>nul
echo.
echo echo ============================================
echo echo   Удаление завершено!
echo echo ============================================
echo pause
) > "%PACKAGE_DIR%\uninstall.bat"

REM Копируем README
copy /Y "README.md" "%PACKAGE_DIR%\" 2>nul

echo.
echo ============================================
echo   Готово!
echo ============================================
echo.
echo Установочный пакет создан в папке:
echo   %PACKAGE_DIR%\
echo.
echo Содержимое:
echo   - ParentalControl.exe (главная программа)
echo   - install.bat (установка)
echo   - uninstall.bat (удаление)
echo   - README.md (инструкция)
echo.
echo Скопируйте всю папку %PACKAGE_DIR% на целевой компьютер
echo и запустите install.bat от имени администратора.
echo.
echo На целевом компьютере НЕ ТРЕБУЕТСЯ установленный Python!
echo.
pause
