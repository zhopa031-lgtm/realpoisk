# -*- coding: utf-8 -*-
"""Определения ниш: теги OpenStreetMap, запросы для Яндекса, веса скоринга и формулировки.

Ниши отсортированы по «жирности» (потенциальный чек за сайт): стоматология/клиники
и автосервисы платят больше всего, салоны красоты — самый массовый вход.
"""
from __future__ import annotations

# Базовый вес ниши в скоринге (0-100 шкала целиком)
NICHE_WEIGHTS = {
    "health": 42,   # стоматологии, клиники, ветеринария — дорогие сайты, больная боль
    "auto": 36,     # автосервисы, шиномонтаж, мойки — клиент ищет «рядом» и звонит
    "beauty": 32,   # салоны, барбершопы, массаж — массовая ниша с онлайн-записью
    "food": 30,     # кафе, рестораны, фастфуд — меню и бронь
    "sport": 28,    # фитнес, спортзалы, студии — расписание и абонементы
    "edu": 26,      # языковые/музыкальные/танцевальные школы — частные центры без сайтов
    "services": 24, # химчистки, ателье, груминг, фотостудии — мелкий чек, но легко закрыть
}

NICHE_LABELS = {  # именительный падеж, для карточки лида
    "beauty": "салоны красоты и барбершопы",
    "auto": "автосервисы и мойки",
    "food": "кафе и рестораны",
    "health": "клиники и стоматологии",
    "sport": "фитнес и студии",
    "edu": "учебные центры",
    "services": "сервисные бизнесы",
    "web_request": "заявки из интернета",
}

NICHE_LABELS_GEN = {  # родительный падеж: «делаю сайты для …»
    "beauty": "салонов красоты и барбершопов",
    "auto": "автосервисов и автомоек",
    "food": "кафе и ресторанов",
    "health": "клиник и стоматологий",
    "sport": "фитнес-клубов и студий",
    "edu": "учебных центров",
    "services": "сервисных бизнесов",
}

NICHE_BENEFITS = {  # конкретная выгода от сайта — подставляется в текст
    "beauty": "онлайн-запись, прайс и фото работ",
    "auto": "запись на сервис, прайс и отзывы клиентов",
    "food": "меню, бронь столика и заказ доставки",
    "health": "запись на приём, врачи и цены",
    "sport": "расписание, абонементы и тренеры",
    "edu": "расписание занятий, программы и запись",
    "services": "прайс, запись и фото работ",
}

# Пары ключ=значение для Overpass (OpenStreetMap) по нише
NICHE_OSM_TAGS = {
    "beauty": ["shop=hairdresser", "shop=beauty", "shop=massage", "shop=solarium", "shop=tattoo"],
    "auto": ["shop=car_repair", "shop=car_wash", "shop=tyres", "shop=truck_repair",
             "shop=car_parts", "shop=car"],
    "food": ["amenity=restaurant", "amenity=cafe", "amenity=bar", "amenity=fast_food",
             "shop=bakery", "amenity=ice_cream"],
    "health": ["amenity=dentist", "amenity=clinic", "amenity=doctors", "amenity=veterinary"],
    "sport": ["leisure=fitness_centre", "leisure=sports_centre", "leisure=dance"],
    "edu": ["amenity=language_school", "amenity=music_school", "amenity=dancing_school"],
    "services": ["shop=dry_cleaning", "shop=laundry", "shop=pet_grooming", "shop=tailor",
                 "shop=photo", "shop=shoe_repair", "shop=electronics_repair"],
}

# Текстовые запросы для поискового API Яндекса (нужен apikey, опционально)
NICHE_YANDEX_QUERIES = {
    "beauty": ["салон красоты", "барбершоп", "парикмахерская", "массаж"],
    "auto": ["автосервис", "шиномонтаж", "автомойка"],
    "food": ["кафе", "ресторан", "пиццерия"],
    "health": ["стоматология", "медицинский центр", "ветеринарная клиника"],
    "sport": ["фитнес-клуб", "спортзал"],
    "edu": ["языковая школа", "музыкальная школа", "танцевальная студия"],
    "services": ["химчистка", "ателье", "груминг", "фотостудия"],
}

NICHE_KEYS = list(NICHE_WEIGHTS.keys())

# Псевдонимы для команды /искать на русском
NICHE_ALIASES = {
    "beauty": ["beauty", "красота", "салоны", "салон", "барбершопы", "парикмахерские"],
    "auto": ["auto", "авто", "автосервисы", "мойки", "шиномонтаж"],
    "food": ["food", "еда", "кафе", "рестораны", "общепит"],
    "health": ["health", "медицина", "клиники", "стоматологии", "стоматология"],
    "sport": ["sport", "спорт", "фитнес", "спортзалы"],
    "edu": ["edu", "школы", "учебные", "образование", "секции"],
    "services": ["services", "услуги", "сервис", "химчистки", "ателье"],
}


def resolve_niche(token: str) -> str | None:
    """Превращает слово пользователя («авто», «beauty») в ключ ниши."""
    t = token.strip().lower().lstrip("/")
    for key, aliases in NICHE_ALIASES.items():
        if t in aliases:
            return key
    return None
