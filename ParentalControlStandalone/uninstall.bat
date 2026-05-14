@echo off
echo ============================================
echo   Удаление Родительского контроля
echo ============================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Требуется запуск от имени администратора!
    pause
    exit /b 1
)

set INSTALL_DIR=%PROGRAMFILES%\ParentalControl

echo [1/3] Остановка и удаление службы...
cd /d "%INSTALL_DIR%"
if exist "parental_control.py" (
    python parental_control.py uninstall
) else (
    sc stop ParentalControlService >nul 2>&1
    timeout /t 2 >nul
    sc delete ParentalControlService >nul 2>&1
    echo Служба удалена
)

echo.
echo [2/3] Удаление файлов программы...
if exist "%INSTALL_DIR%" (
    rmdir /s /q "%INSTALL_DIR%"
    echo Файлы программы удалены из %INSTALL_DIR%
)

echo.
echo [3/3] Удаление ярлыков с рабочего стола...
del "%USERPROFILE%\Desktop\Родительский контроль - Админ.lnk" 2>nul
del "%USERPROFILE%\Desktop\Родительский контроль - Старт.lnk" 2>nul
echo Ярлыки удалены

echo.
echo ============================================
echo   Удаление завершено!
echo ============================================
echo.
pause
