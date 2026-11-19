# -*- coding: utf-8 -*-
"""Загрузка config.json с разумными значениями по умолчанию."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "data" / "state.json"

DEFAULTS = {
    "bot_token": "",                      # токен от @BotFather
    "sender_name": "",                    # подпись в конце сообщений (необязательно)
    "country_code": "ru",                 # для геокодинга городов
    "city_main": "Казань",                # ← поменяй на свой город
    "satellites": [],                     # города-сателлиты, например ["Зеленодольск", "Волжск"]
    "niches": ["health", "auto", "beauty", "food", "sport", "edu", "services"],
    "schedule_enabled": True,             # авто-поиск по расписанию
    "schedule_hour": 9,                   # час утренней рассылки лидов
    "schedule_minute": 0,
    "search_on_start": True,              # искать лидов сразу при запуске бота (не ждать утра)
    "search_every_minutes": 15,           # фоновый поиск каждые N минут (минимум 15; 0 = выключить)
    "search_cities_per_cycle": 3,         # сколько городов проверять за один цикл (дальше по кругу)
    "portfolio_url": "",                  # ссылка на портфолио — встанет в конец первого сообщения
    "leads_per_digest": 8,                # сколько карточек присылать за раз (без спама)
    "digest_web_max": 3,                  # сколько «заявок из интернета» прикладывать
    "min_score": 40,                      # порог приоритетности (0-100)
    "require_contact": True,              # показывать только лидов, кому есть что написать
    "web_intake": True,                   # искать «нужен сайт» в интернете (DuckDuckGo)
    "web_queries": [
        '"нужен сайт" тг заказать',
        '"сделать сайт" "в лс" ищу',
        '"ищу программиста" сайт телеграм',
        '"нужен лендинг" заказать тг',
    ],
    "yandex_api_key": "",                 # опционально: ключ Поиска организаций developer.tech.yandex.ru
    "overpass_mirrors": [],               # доп. зеркала Overpass, если основные недоступны
    "max_leads_per_niche_city": 300,      # защита от слишком больших выборок
    "extra_scoring": {},                  # свои переопределения весов скоринга
}


class Settings:
    def __init__(self, data: dict):
        self.cfg = data

    def __getattr__(self, key):
        try:
            return self.cfg[key]
        except KeyError:
            raise AttributeError(key)

    def get(self, key, default=None):
        return self.cfg.get(key, default)

    @property
    def cities(self) -> list[str]:
        return [self.cfg["city_main"]] + list(self.cfg.get("satellites", []))

    @property
    def niches_active(self) -> list[str]:
        from . import niches
        return [n for n in self.cfg["niches"] if n in niches.NICHE_KEYS]

    def summary(self) -> str:
        lines = [
            f"Главный город: {self.cfg['city_main']}",
            f"Сателлиты: {', '.join(self.cfg.get('satellites', [])) or '—'}",
            f"Ниши: {', '.join(self.niches_active)}",
            f"Авто-поиск: {'включён' if self.cfg.get('schedule_enabled') else 'выключен'} "
            f"в {self.cfg.get('schedule_hour'):02d}:{self.cfg.get('schedule_minute'):02d}",
            f"Лидов за рассылку: {self.cfg.get('leads_per_digest')}, порог скоринга: {self.cfg.get('min_score')}",
            f"Заявки из интернета: {'вкл' if self.cfg.get('web_intake') else 'выкл'}",
            f"Ключ Яндекса: {'есть' if self.cfg.get('yandex_api_key') else 'нет (поиск только по OpenStreetMap)'}",
        ]
        return "\n".join(lines)


def load_settings() -> Settings:
    data = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                data.update({k: v for k, v in user.items() if v is not None})
        except (json.JSONDecodeError, OSError) as e:
            raise SystemExit(f"config.json повреждён: {e}\nИсправь файл и запусти снова.")
    else:
        CONFIG_PATH.write_text(
            json.dumps(DEFAULTS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return Settings(data)


def next_cities(cfg: "Settings", k: int | None = None) -> list[str]:
    """Ротация городов: следующие k городов по кругу.

    Позиция хранится в data/state.json, поэтому все города из config.json
    проверяются по очереди — и в фоновом поиске, и в GitHub Actions."""
    cities = list(cfg.cities)
    if not cities:
        return cities
    k = max(1, min(int(k or cfg.get("search_cities_per_cycle", 3) or 3), len(cities)))
    state = load_state()
    pos = int(state.get("city_cursor", 0)) % len(cities)
    out = [cities[(pos + i) % len(cities)] for i in range(k)]
    state["city_cursor"] = (pos + k) % len(cities)
    save_state(state)
    return out


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
