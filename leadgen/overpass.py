# -*- coding: utf-8 -*-
"""Источник лидов №1: OpenStreetMap через Overpass API.

Логика «бизнес без сайта» проверяется прямо в запросе: [!"website"][!"contact:website"][!"url"].
Бесплатно, без ключа, легально (данные OSM под ODbL). Полнота зависит от региона,
но по городам России данные приличные, зеркала mail.ru работают быстро.
"""
from __future__ import annotations

import time

import httpx

from .utils import first_phone

UA = "vibe-leadgen-bot/1.0 (personal one-to-one outreach research; contact: local user)"

# Первым стоит российское зеркало — самое быстрое из РФ и стабильное.
DEFAULT_MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

_ABSENCE = '[!"website"][!"contact:website"][!"url"]'


def build_query(area_ids: list[int], key: str, value: str, limit: int = 300) -> str:
    """Overpass QL для ОДНОГО точного значения тега («без сайта» проверяется в запросе).

    Практика показала: зеркала стабильно отвечают на простые запросы
    [key="value"][!website][!contact:website][!url] (~20-30 с), а тяжёлые
    regex/объединения отбрасывают при нагрузке (504). Поэтому конвейер
    обходит пары key=value отдельными лёгкими запросами.
    """
    if len(area_ids) == 1:
        area_stmt = f"area({area_ids[0]})->.a;"
    else:
        area_stmt = "(" + ";".join(f"area({a})" for a in area_ids) + ";)->.a;"
    return (
        f"[out:json][timeout:120];\n{area_stmt}\n"
        f'nwr(area.a)["{key}"="{value}"]{_ABSENCE};\n'
        f"out center {limit};"
    )


def fetch_raw(query: str, extra_mirrors: list[str] | None = None, timeout: float = 200.0,
              rounds: int = 2) -> dict:
    """POST запроса в Overpass с перебором зеркал; при перегрузке — второй круг.

    Зеркала иногда отдают 504 «на ровном месте» (перегруз), через минуту
    отвечают нормально — поэтому попытки идут в два круга с паузой.
    """
    mirrors = list(DEFAULT_MIRRORS) + list(extra_mirrors or [])
    last_err = "неизвестная ошибка"
    for attempt in range(rounds):
        for mirror in mirrors:
            try:
                r = httpx.post(mirror, data={"data": query}, timeout=timeout,
                               headers={"User-Agent": UA})
                if r.status_code == 200:
                    return r.json()
                last_err = f"{mirror}: HTTP {r.status_code}"
            except Exception as e:  # зеркало недоступно — идём к следующему
                last_err = f"{mirror}: {type(e).__name__}"
            time.sleep(1.0)
        if attempt < rounds - 1:
            time.sleep(20.0)
    raise RuntimeError(
        f"Overpass недоступен ({last_err}). Проверь интернет или добавь зеркало "
        f"overpass_mirrors в config.json"
    )


def parse_elements(raw: dict, niche: str, city: str) -> list[dict]:
    """Overpass JSON → список лидов (dict) в общем формате pipeline."""
    leads = []
    for el in raw.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:ru")
        if not name:
            continue
        # страховка: вдруг сайт проскочил через другой тег
        if any(tags.get(t) for t in ("website", "url", "contact:website", "contact:url")):
            continue

        center = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        phone = first_phone(
            tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile")
        )
        email = (tags.get("email") or tags.get("contact:email") or "").strip()
        socials = []
        for key in ("contact:vk", "contact:instagram", "contact:telegram",
                    "contact:whatsapp", "contact:ok", "contact:facebook", "contact:tiktok"):
            if tags.get(key):
                socials.append(f"{key.split(':')[1]}: {tags[key]}")

        address = ", ".join(
            x for x in (tags.get("addr:city"), tags.get("addr:street"),
                        tags.get("addr:housenumber")) if x
        )
        leads.append({
            "source": "osm",
            "source_id": f"osm:{el.get('type')}/{el.get('id')}",
            "name": name,
            "niche": niche,
            "city": tags.get("addr:city") or city,
            "address": address,
            "phone": phone,
            "email": email,
            "socials": socials,
            "hours": tags.get("opening_hours", ""),
            "url": "",
            "snippet": "",
            "lat": center.get("lat"),
            "lon": center.get("lon"),
        })
    return leads
