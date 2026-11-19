@echo off
chcp 65001 >nul
cd /d "%~dp0"
title LeadRadar - полная автоматизация
echo === ПОЛНАЯ АВТОМАТИЗАЦИЯ ===
echo Сам ищет лидов каждые 60 минут и сам обновляет сайт.
echo Ты можешь ничего не делать: сайт откроется сам и будет пополняться.
echo Окно сверни (не закрывай) — и забудь про него.
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

%PY% cli.py auto
echo.
pause
