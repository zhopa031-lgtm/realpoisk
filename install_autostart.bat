@echo off
chcp 65001 >nul
echo === Устанавливаю автозапуск при включении Windows ===
echo (сайт и поиски будут стартовать сами при каждом входе в систему)
echo.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "DIR=%~dp0"

>"%TEMP%\leadgen_autostart.vbs" echo CreateObject("WScript.Shell").Run """%DIR%auto.bat""", 7, False
move /y "%TEMP%\leadgen_autostart.vbs" "%STARTUP%\leadgen_autostart.vbs" >nul
if errorlevel 1 (
    echo [ОШИБКА] Не получилось записать файл в автозагрузку.
    pause
    exit /b 1
)

echo Готово! Теперь при каждом входе в Windows автоматически запускается:
echo   %DIR%auto.bat
echo.
echo Убрать автозапуск можно в любой момент: remove_autostart.bat
echo.
pause
