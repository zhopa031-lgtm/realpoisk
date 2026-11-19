@echo off
chcp 65001 >nul
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%\leadgen_autostart.vbs" (
    del "%STARTUP%\leadgen_autostart.vbs"
    echo Автозапуск убран — теперь запускай auto.bat вручную.
) else (
    echo Автозапуск и не был установлен.
)
echo.
pause
