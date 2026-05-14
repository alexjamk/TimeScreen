@echo off
echo ============================================
echo   РОДИТЕЛЬСКИЙ КОНТРОЛЬ - УСТАНОВКА
echo ============================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ОШИБКА: Требуются права администратора!
    echo.
    echo Щелкните правой кнопкой мыши на этом файле
    echo и выберите "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

echo [1/4] Проверка Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ОШИБКА: Python не найден!
    echo Установите Python с python.org или из Microsoft Store
    pause
    exit /b 1
)
echo OK - Python найден
echo.

echo [2/4] Создание директории для конфигурации...
if not exist "C:\ProgramData\ParentalControl" (
    mkdir "C:\ProgramData\ParentalControl"
)
echo OK
echo.

echo [3/4] Настройка пароля и временных интервалов...
python "%~dp0parental_control.py" admin
if %errorLevel% neq 0 (
    echo ОШИБКА при настройке
    pause
    exit /b 1
)
echo.

echo [4/4] Установка службы Windows...
python "%~dp0parental_control.py" install
if %errorLevel% neq 0 (
    echo ОШИБКА при установке службы
    pause
    exit /b 1
)
echo.

echo ============================================
echo   УСТАНОВКА ЗАВЕРШЕНА!
echo ============================================
echo.
echo Служба установлена и готова к работе.
echo.
echo Для управления используйте команды:
echo   net start ParentalControlService   - запустить
echo   net stop ParentalControlService    - остановить
echo   python parental_control.py status  - статус
echo.
echo Чтобы изменить настройки, выполните:
echo   python parental_control.py admin
echo.
pause
