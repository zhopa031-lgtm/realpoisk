@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === vibe-leadgen: запуск бота ===
echo.

set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY (
    python --version >nul 2>&1 && set PY=python
)
if not defined PY (
    echo [ОШИБКА] Python не найден на этом компьютере.
    echo.
    echo Что делать:
    echo   1. Скачай Python: https://www.python.org/downloads/
    echo   2. При установке ОБЯЗАТЕЛЬНО поставь галочку "Add Python to PATH"
    echo   3. Закрой и снова открой это окно, запусти start.bat ещё раз
    echo.
    pause
    exit /b 1
)

if not exist venv (
    echo [1/2] Первый запуск: создаю окружение и ставлю зависимости...
    echo       (нужен интернет, занимает около минуты)
    %PY% -m venv venv
    call venv\Scripts\pip.exe install -r requirements.txt -q
    if errorlevel 1 (
        echo.
        echo [ОШИБКА] Не удалось установить зависимости.
        echo Проверь интернет и запусти start.bat ещё раз.
        pause
        exit /b 1
    )
) else (
    echo [1/2] Окружение готово.
)

echo [2/2] Запускаю бота...
echo.
call venv\Scripts\python.exe bot.py
echo.
echo Бот остановлен. Если выше есть красная ошибка — пришли её скриншот.
pause
