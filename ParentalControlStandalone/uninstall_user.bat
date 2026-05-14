@echo off
echo ============================================
echo   Удаление Родительского контроля
echo ============================================
echo.

echo Остановка фонового процесса...
taskkill /f /im ParentalControl.exe >nul 2>&1
taskkill /f /im wscript.exe /fi "WINDOWTITLE eq ParentalControl" >nul 2>&1

echo Удаление программы...
if exist "%LOCALAPPDATA%\ParentalControl\ParentalControl.exe" (
    "%LOCALAPPDATA%\ParentalControl\ParentalControl.exe" uninstall-user
) else (
    echo Программа не найдена, выполняю очистку...
    REM Удаляем из автозагрузки
    if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ParentalControl.lnk" (
        del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ParentalControl.lnk"
        echo Удалено из автозагрузки
    )
    REM Удаляем ярлыки
    if exist "%USERPROFILE%\Desktop\Родительский контроль - Админ.lnk" (
        del "%USERPROFILE%\Desktop\Родительский контроль - Админ.lnk"
        echo Удалён ярлык "Админ"
    )
    if exist "%USERPROFILE%\Desktop\Родительский контроль - Защита.lnk" (
        del "%USERPROFILE%\Desktop\Родительский контроль - Защита.lnk"
        echo Удалён ярлык "Защита"
    )
    REM Удаляем папку
    if exist "%LOCALAPPDATA%\ParentalControl" (
        rmdir /s /q "%LOCALAPPDATA%\ParentalControl"
        echo Удалена папка программы
    )
)

echo.
echo ============================================
echo   Удаление завершено!
echo ============================================
pause
