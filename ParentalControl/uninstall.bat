@echo off
echo ============================================
echo   РОДИТЕЛЬСКИЙ КОНТРОЛЬ - УДАЛЕНИЕ
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

echo [1/3] Остановка службы...
net stop ParentalControlService >nul 2>&1
echo OK
echo.

echo [2/3] Удаление службы...
python "%~dp0parental_control.py" uninstall
echo.

echo [3/3] Очистка файлов...
if exist "C:\ProgramData\ParentalControl" (
    set /p confirm="Удалить все файлы конфигурации? (y/n): "
    if /i "%confirm%"=="y" (
        rmdir /s /q "C:\ProgramData\ParentalControl"
        echo Файлы удалены
    )
)
echo.

echo ============================================
echo   УДАЛЕНИЕ ЗАВЕРШЕНО!
echo ============================================
echo.
pause
