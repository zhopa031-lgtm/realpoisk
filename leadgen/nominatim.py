# -*- coding: utf-8 -*-
"""Геокодинг городов через Nominatim (OpenStreetMap): название города → area_id для Overpass."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

UA = "vibe-leadgen-bot/1.0 (city geocoding for lead research)"
CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "geo_cache.json"


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def geocode_area(city: str, country_code: str = "ru") -> int:
    """Возвращает Overpass area_id города (relation → 3600…, way → 2400…)."""
    key = f"{city}|{country_code}"
    cache = _load_cache()
    if key in cache:
        return cache[key]

    r = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": city, "format": "jsonv2", "limit": 3, "countrycodes": country_code},
        headers={"User-Agent": UA},
        timeout=30,
    )
    r.raise_for_status()
    results = r.json()
    chosen = None
    for item in results:
        if item.get("osm_type") == "relation":
            chosen = item
            break
    if chosen is None and results:
        for item in results:
            if item.get("osm_type") == "way":
                chosen = item
                break
    if chosen is None:
        raise RuntimeError(f"Город «{city}» не найден в OSM. Проверь название в config.json")

    osm_id = chosen["osm_id"]
    area_id = 3600000000 + osm_id if chosen["osm_type"] == "relation" else 2400000000 + osm_id
    cache[key] = area_id
    _save_cache(cache)
    time.sleep(1.0)  # вежливость к Nominatim
    return area_id
