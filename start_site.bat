@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Живой режим сайта index.html ===
echo (локальный сервер + сайт самообновляется каждые 20 секунд)
echo.

set PY=
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe
if not defined PY (
    py -3 --version >nul 2>&1 && set PY=py -3
)
if not defined PY (
    python --version >nul 2>&1 && set PY=python
)
if not defined PY (
    echo [ОШИБКА] Python не найден на этом компьютере.
    echo Скачай его с https://www.python.org/downloads/
    echo и при установке поставь галочку "Add Python to PATH".
    pause
    exit /b 1
)

%PY% cli.py serve-site
echo.
pause
