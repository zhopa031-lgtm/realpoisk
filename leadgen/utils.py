# -*- coding: utf-8 -*-
"""Мелкие утилиты: нормализация телефонов, ссылки, экранирование HTML."""
from __future__ import annotations

import html
import re
from urllib.parse import quote


def normalize_phone(raw: str | None) -> str:
    """Приводит телефон к виду +7XXXXXXXXXX (или оставляет международный)."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    if raw.strip().startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    return ""


def first_phone(raw: str | None) -> str:
    """В OSM телефон бывает списком через ';' или ',' — берём первый."""
    if not raw:
        return ""
    for part in re.split(r"[;,]", raw):
        norm = normalize_phone(part)
        if norm:
            return norm
    return ""


def tg_link(phone: str) -> str:
    """Ссылка, открывающая чат в Telegram по номеру телефона.

    Работает, если номер привязан к аккаунту TG и настройки приватности позволяют.
    Если нет — номер всё равно остаётся в карточке, добавь контакт вручную.
    """
    return f"tg://resolve?phone={phone}"


def tel_link(phone: str) -> str:
    return f"tel:{phone}"


def yandex_map_url(name: str, city: str, address: str = "") -> str:
    """Ссылка на поиск организации в Яндекс.Картах (открывается в браузере/приложении)."""
    q = ", ".join(x for x in [name, city, address] if x)
    return "https://yandex.ru/maps/search/" + quote(q)


def esc(s) -> str:
    """Экранирование для HTML parse_mode в Telegram."""
    return html.escape(str(s if s is not None else ""), quote=False)
