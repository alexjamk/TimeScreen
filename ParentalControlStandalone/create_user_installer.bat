@echo off
echo ============================================
echo   Создание установочного пакета
echo   (для текущего пользователя, без прав админа)
echo ============================================
echo.

REM Проверка наличия .exe
if not exist "dist\ParentalControl.exe" (
    echo ОШИБКА: dist\ParentalControl.exe не найден!
    echo Сначала запустите build_exe.bat для сборки .exe
    pause
    exit /b 1
)

set PACKAGE_DIR=ParentalControl_Installer_User
if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"

echo [1/3] Копирование программы...
copy /Y "dist\ParentalControl.exe" "%PACKAGE_DIR%\" >nul
echo Готово

echo [2/3] Копирование скриптов...
copy /Y "install_user.bat" "%PACKAGE_DIR%\install.bat" >nul
copy /Y "uninstall_user.bat" "%PACKAGE_DIR%\uninstall.bat" >nul
copy /Y "README.md" "%PACKAGE_DIR%\" >nul 2>nul
echo Готово

echo [3/3] Создание инструкции...
(
echo ============================================
echo   Родительский контроль - Инструкция
echo ============================================
echo.
echo УСТАНОВКА (права администратора НЕ требуются):
echo   1. Запустите install.bat
echo   2. Программа установится в папку пользователя
echo   3. На рабочем столе появятся ярлыки
echo   4. Фоновый процесс добавится в автозагрузку
echo.
echo НАСТРОЙКА:
echo   - Откройте "Родительский контроль - Админ"
echo   - Установите пароль
echo   - Добавьте разрешённые интервалы (например, 08:00-22:00)
echo.
echo КОМАНДЫ:
echo   ParentalControl.exe admin          - Панель администратора
echo   ParentalControl.exe toggle         - Вкл/выкл защиту
echo   ParentalControl.exe install-user   - Переустановить
echo   ParentalControl.exe uninstall-user - Удалить
echo   ParentalControl.exe help           - Справка
echo.
echo УДАЛЕНИЕ:
echo   Запустите uninstall.bat
echo.
) > "%PACKAGE_DIR%\README.txt"

echo.
echo ============================================
echo   Готово!
echo ============================================
echo.
echo Установочный пакет создан в папке:
echo   %PACKAGE_DIR%\
echo.
echo Содержимое:
echo   - ParentalControl.exe   (главная программа ~11 МБ)
echo   - install.bat           (установка)
echo   - uninstall.bat         (удаление)
echo   - README.txt            (инструкция)
echo.
echo Скопируйте всю папку %PACKAGE_DIR% на целевой компьютер
echo и запустите install.bat (обычным двойным кликом).
echo.
echo На целевом компьютере НЕ ТРЕБУЕТСЯ:
echo   - Python
echo   - Права администратора
echo   - Подключение к интернету
echo.
pause
