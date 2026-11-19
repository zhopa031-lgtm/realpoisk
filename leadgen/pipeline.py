# -*- coding: utf-8 -*-
"""Конвейер: источники → дедуп → скоринг → хранилище.

run_search() — бизнесы без сайта (OSM всегда + Яндекс при наличии ключа).
run_web_intake() — «нужен сайт» из интернета (DuckDuckGo, необязательный блок).
"""
from __future__ import annotations

import time

from . import niches, overpass, web_intake, yandex
from .nominatim import geocode_area
from .scoring import score_lead
from .settings import Settings
from .storage import Storage


class Pipeline:
    def __init__(self, settings: Settings, storage: Storage):
        self.s = settings
        self.db = storage

    # ---------- поиск бизнесов без сайта ----------
    def run_search(self, city_list: list[str] | None = None,
                   niche_list: list[str] | None = None,
                   progress=None) -> dict:
        """Ищет бизнесы без сайта. progress(message) — коллбэк для статуса."""
        cities = city_list or self.s.cities
        niches_ = niche_list or self.s.niches_active
        progress = progress or (lambda msg: None)

        area_ids: dict[str, int] = {}
        errors: list[str] = []
        for city in cities:
            try:
                country = (self.s.get("city_countries") or {}).get(city) \
                    or self.s.get("country_code", "ru")
                area_ids[city] = geocode_area(city, country)
                progress(f"🗺 {city}: найден в OpenStreetMap")
            except Exception as e:
                errors.append(f"геокодинг {city}: {e}")

        new_leads, scanned, duplicates = [], 0, 0
        total_steps = len(cities) * len(niches_)
        step = 0

        for city, area_id in area_ids.items():
            for niche in niches_:
                step += 1
                label = niches.NICHE_LABELS.get(niche, niche)
                for pair in niches.NICHE_OSM_TAGS[niche]:
                    key, value = pair.split("=", 1)
                    progress(f"🔍 {city} · {label} · {value} ({step}/{total_steps})")
                    query = overpass.build_query(
                        [area_id], key, value, self.s.get("max_leads_per_niche_city", 300)
                    )
                    try:
                        raw = overpass.fetch_raw(query, self.s.get("overpass_mirrors"))
                    except Exception as e:
                        errors.append(f"Overpass {city}/{niche}/{value}: {e}")
                        continue
                    leads = overpass.parse_elements(raw, niche, city)
                    scanned += len(leads)
                    for lead in leads:
                        lead["score"], lead["reasons"] = score_lead(lead, self.s)
                        lead_id, is_new = self.db.add_lead(lead)
                        if is_new:
                            lead["id"] = lead_id
                            new_leads.append(lead)
                        else:
                            duplicates += 1
                    time.sleep(1.0)  # вежливая пауза между запросами к Overpass

        # ---------- Яндекс API (опционально) ----------
        if self.s.get("yandex_api_key"):
            progress("🗺 Поиск организаций Яндекса (по ключу)…")
            for niche in niches_:
                queries = niches.NICHE_YANDEX_QUERIES.get(niche, [])
                try:
                    leads = yandex.fetch_yandex_leads(
                        self.s.yandex_api_key, self.s.city_main, niche, queries
                    )
                except Exception as e:
                    errors.append(f"Яндекс API: {e}")
                    continue
                scanned += len(leads)
                for lead in leads:
                    lead["score"], lead["reasons"] = score_lead(lead, self.s)
                    lead_id, is_new = self.db.add_lead(lead)
                    if is_new:
                        lead["id"] = lead_id
                        new_leads.append(lead)
                    else:
                        duplicates += 1

        new_leads.sort(key=lambda l: l.get("score", 0), reverse=True)
        return {
            "new": new_leads, "scanned": scanned, "duplicates": duplicates,
            "errors": errors,
        }

    # ---------- заявки из интернета ----------
    def run_web_intake(self) -> tuple[list[dict], list[str]]:
        errors: list[str] = []
        try:
            found = web_intake.fetch_web_leads(
                self.s.get("web_queries", []), limit=40
            )
        except Exception as e:
            return [], [f"Заявки из интернета: {e}"]

        saved = []
        for item in found:
            lead = {
                "source": "web",
                "source_id": item["source_id"],
                "name": item["title"][:120],
                "niche": "web_request",
                "city": "",
                "address": "",
                "phone": "",
                "email": "",
                "socials": [],
                "hours": "",
                "url": item["url"],
                "snippet": item.get("snippet", "")[:300],
                "score": 60,
                "reasons": ["человек сам ищет, кто сделает сайт"],
            }
            lead_id, is_new = self.db.add_lead(lead)
            if is_new:
                lead["id"] = lead_id
                saved.append(lead)
        return saved, errors
