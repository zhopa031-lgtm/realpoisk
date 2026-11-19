#!/usr/bin/env bash
# Запуск бота на Linux/macOS: ./start.sh
# Ты на Windows? Этот файл тебе не нужен — запускай start.bat двойным кликом.
cd "$(dirname "$0")"
if [ ! -d venv ]; then
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt -q
fi
exec ./venv/bin/python bot.py
