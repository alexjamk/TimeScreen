@echo off
chcp 65001 >nul
title TimeScreen — Полная очистка

echo ============================================
echo   TimeScreen — ПРИНУДИТЕЛЬНАЯ ОЧИСТКА
echo   Удаляет службу, процессы, файлы, ярлыки
echo ============================================
echo.

REM ── Запуск от администратора ─────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Требуются права администратора.
    echo     Запрашиваю повышение...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo [1/7] Остановка и удаление службы...
sc stop TimeScreenControl >nul 2>&1
timeout /t 3 /nobreak >nul
sc stop TimeScreenControl >nul 2>&1
timeout /t 2 /nobreak >nul
sc delete TimeScreenControl >nul 2>&1

REM Проверяем, не помечена ли на удаление (error 1072)
sc query TimeScreenControl >nul 2>&1
if %errorLevel% equ 0 (
    echo [!] Служба всё ещё существует.
    echo     Возможно, помечена на удаление (error 1072).
    echo.
    set /p REBOOT="    Перезагрузить компьютер сейчас? (Y/N): "
    if /i "%REBOOT%"=="Y" (
        echo     Перезагрузка через 5 секунд...
        shutdown /r /t 5
        exit /b
    ) else (
        echo     Служба исчезнет после следующей перезагрузки.
    )
) else (
    echo     Служба удалена.
)

echo.
echo [2/7] Завершение процессов TimeScreen...
taskkill /f /im TimeScreenControl.exe >nul 2>&1
taskkill /f /im TimeScreenService.exe >nul 2>&1
taskkill /f /im wscript.exe /fi "IMAGENAME eq wscript.exe" >nul 2>&1
echo     Готово.

echo.
echo [3/7] Удаление scheduled tasks...
schtasks /delete /tn "TimeScreenAgentRestart" /f >nul 2>&1
echo     Готово.

echo.
echo [4/7] Удаление ярлыков с рабочего стола...
if exist "%USERPROFILE%\Desktop\TimeScreen - Настройки.lnk" del /f /q "%USERPROFILE%\Desktop\TimeScreen - Настройки.lnk" 2>nul
if exist "%USERPROFILE%\Desktop\TimeScreen - Защита.lnk" del /f /q "%USERPROFILE%\Desktop\TimeScreen - Защита.lnk" 2>nul
if exist "%USERPROFILE%\Desktop\Родительский контроль - Админ.lnk" del /f /q "%USERPROFILE%\Desktop\Родительский контроль - Админ.lnk" 2>nul
if exist "%USERPROFILE%\Desktop\Родительский контроль - Защита.lnk" del /f /q "%USERPROFILE%\Desktop\Родительский контроль - Защита.lnk" 2>nul
echo     Готово.

echo.
echo [5/7] Удаление из автозагрузки...
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\TimeScreen.lnk" del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\TimeScreen.lnk" 2>nul
echo     Готово.

echo.
echo [6/7] Удаление файлов программы...
if exist "%LOCALAPPDATA%\TimeScreen" (
    rmdir /s /q "%LOCALAPPDATA%\TimeScreen" 2>nul
    if exist "%LOCALAPPDATA%\TimeScreen" (
        echo     [!] Не удалось удалить %LOCALAPPDATA%\TimeScreen (файлы заняты).
    ) else (
        echo     %LOCALAPPDATA%\TimeScreen — удалено.
    )
)

echo.
echo [7/7] Удаление конфигурации и логов...
if exist "%PROGRAMDATA%\TimeScreen" (
    rmdir /s /q "%PROGRAMDATA%\TimeScreen" 2>nul
    if exist "%PROGRAMDATA%\TimeScreen" (
        echo     [!] Не удалось удалить %PROGRAMDATA%\TimeScreen (файлы заняты).
        echo     Перезагрузите ПК и запустите скрипт снова.
    ) else (
        echo     %PROGRAMDATA%\TimeScreen — удалено.
    )
)

echo.
echo ============================================
echo   Очистка завершена!
echo ============================================
echo.
echo Если служба была помечена на удаление (error 1072),
echo она исчезнет после перезагрузки.
echo.
pause
