# -*- coding: utf-8 -*-
"""Источник №2: Поиск организаций Яндекса (официальный API).

Опционально: нужен apikey с developer.tech.yandex.ru («Поиск организаций», есть
пробный период). Бот работает и без него — по OpenStreetMap. С ключом данные
точнее и свежее (рейтинг, часы, точные адреса с Яндекс.Карт).

Без ключа модуль всё равно полезен: generate_map_link() строит ссылку на
поиск организации в Яндекс.Картах — она идёт в каждую карточку лида.
"""
from __future__ import annotations

import hashlib

import httpx

API_URL = "https://search-maps.yandex.ru/v1/"
UA = "vibe-leadgen-bot/1.0"


def generate_map_link(name: str, city: str, address: str = "") -> str:
    from .utils import yandex_map_url
    return yandex_map_url(name, city, address)


def fetch_yandex_leads(api_key: str, city: str, niche: str, queries: list[str],
                       per_query: int = 50) -> list[dict]:
    """Ищет организации через официальный API, отдаёт те, у кого нет сайта.

    У организаций Яндекса поле сайта часто заполнено; пропускаем тех, у кого
    сайт есть. Если сайт не указан в API — лида берём (проверка по ссылке
    на карточку остаётся на пользователе, кнопка «Карты» есть в карточке).
    """
    leads = []
    for q in queries:
        try:
            r = httpx.get(
                API_URL,
                params={
                    "apikey": api_key,
                    "text": f"{q}, {city}",
                    "type": "biz",
                    "lang": "ru_RU",
                    "results": per_query,
                },
                headers={"User-Agent": UA},
                timeout=40,
            )
        except httpx.HTTPError as e:
            raise RuntimeError(f"Яндекс API недоступен: {e}") from e
        if r.status_code != 200:
            raise RuntimeError(
                f"Яндекс API ответил HTTP {r.status_code}: {r.text[:200]} "
                f"(проверь ключ yandex_api_key)"
            )
        for feature in r.json().get("features", []):
            props = feature.get("properties", {})
            meta = props.get("CompanyMetadata", {}) or {}

            name = meta.get("name") or props.get("name")
            if not name:
                continue

            # собираем любые ссылки на сайт из ответа
            urls = []
            for container in (meta, props):
                for k, v in container.items():
                    if k.lower() in ("url", "urls", "site") and isinstance(v, str) and v:
                        urls.append(v)
            links = props.get("Links") or []
            if isinstance(links, list):
                for l in links:
                    if isinstance(l, dict):
                        h = l.get("Href") or l.get("href") or ""
                        if h and "yandex" not in h:
                            urls.append(h)
            if urls:
                continue  # сайт есть — не наш клиент

            phones = meta.get("Phones") or []
            phone = ""
            if phones and isinstance(phones, list):
                raw = phones[0].get("formatted") or phones[0].get("FormattedNumber") or ""
                from .utils import normalize_phone
                phone = normalize_phone(raw)

            address = meta.get("address") or meta.get("formattedAddress") or ""
            feature_id = props.get("featureId") or meta.get("id") or f"{name}|{address}"
            source_id = "ym:" + hashlib.md5(f"{feature_id}".encode()).hexdigest()[:12]

            leads.append({
                "source": "yandex",
                "source_id": source_id,
                "name": name,
                "niche": niche,
                "city": city,
                "address": address,
                "phone": phone,
                "email": "",
                "socials": [],
                "hours": "",
                "url": "",
                "snippet": f"найдено по запросу «{q}»",
                "lat": (props.get("geometry", {}).get("coordinates") or [None, None])[1],
                "lon": (props.get("geometry", {}).get("coordinates") or [None, None])[0],
            })
    return leads
