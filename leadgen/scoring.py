# -*- coding: utf-8 -*-
"""Скоринг «жирности» лида: чем выше балл (0-100), тем вероятнее заказ и больше чек."""
from __future__ import annotations

from .niches import NICHE_WEIGHTS
from .settings import Settings

DEFAULT_WEIGHTS = {
    "phone": 25,          # контакт есть — можно писать сразу
    "contact_extra": 8,   # email или соцсети в дополнение
    "hours": 12,          # указаны часы работы → бизнес живой
    "address": 5,         # есть адрес → реальная точка
    "main_city": 8,       # крупный город → больше клиентов и чек
    "satellite": 4,       # сателлит
    "brand_name": 5,      # похоже на бренд/ИП с названием, а не безымянная точка
}


def score_lead(lead: dict, settings: Settings) -> tuple[int, list[str]]:
    """Возвращает (балл 0-100, причины приоритета для карточки)."""
    w = dict(DEFAULT_WEIGHTS)
    w.update(settings.get("extra_scoring", {}) or {})

    score = 0
    reasons = []

    niche = lead.get("niche", "")
    base = NICHE_WEIGHTS.get(niche, 20)
    score += base
    if base >= 36:
        reasons.append(f"жирная ниша (+{base})")
    else:
        reasons.append(f"ниша +{base}")

    if lead.get("phone"):
        score += w["phone"]
        reasons.append(f"есть телефон (+{w['phone']})")
    if lead.get("email") or lead.get("socials"):
        score += w["contact_extra"]
        reasons.append("есть доп. контакт")

    if lead.get("hours"):
        score += w["hours"]
        reasons.append("живой бизнес, часы работы указаны")

    if lead.get("address"):
        score += w["address"]

    city = (lead.get("city") or "").strip()
    if city and city == settings.city_main:
        score += w["main_city"]
    elif city:
        score += w["satellite"]

    name = lead.get("name", "")
    if name and (len(name.split()) >= 2 or "«" in name or '"' in name or name.isupper()):
        score += w["brand_name"]
        reasons.append("оформленный бренд")

    score = min(score, 100)
    if not reasons:
        reasons.append("базовое совпадение")
    return score, reasons
