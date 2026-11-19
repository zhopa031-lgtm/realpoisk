# -*- coding: utf-8 -*-
"""Связка бота с сайтом leadradar.html: сборка JSON лидов и вшивание их прямо в файл сайта.

Сайт размечен маркерами /*__LEADRADAR_DATA:start__*/ ... /*__LEADRADAR_DATA:end__*/.
update_html() заменяет содержимое между маркерами на актуальную базу. После этого
сайту не нужен отдельный leads.json — данные уже внутри HTML: открыл файл, и всё.

Используется из двух мест:
  cli.py update-site   — разовый запуск (update_site.bat)
  bot.py               — после каждого утреннего авто-поиска
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from . import niches

# ключ ниши в базе → название ниши для сайта
NICHE_TO_SITE = {
    "beauty": "Салоны красоты", "auto": "Автосервисы", "food": "Кафе и рестораны",
    "health": "Медцентры", "sport": "Фитнес", "edu": "Учебные центры",
    "services": "Сервисные бизнесы", "web_request": "Заказы из интернета",
}

MARK_START = "/*__LEADRADAR_DATA:start__*/"
MARK_END = "/*__LEADRADAR_DATA:end__*/"


def build_leads(rows) -> list:
    """Строки Storage.export_rows() → список лидов в формате сайта leadradar.html."""
    now = datetime.datetime.now()
    out = []
    for r in rows:
        try:
            socials = json.loads(r["socials"] or "[]")
        except Exception:
            socials = []
        reasons = [x.strip() for x in (r["reasons"] or "").split(";") if x.strip()]

        # контакт: заявка из веба → ссылка; телефон → звонок; соцсети → TG или профиль
        if r["source"] == "web" and r["url"]:
            contact, ct = r["url"], "url"
        elif r["phone"]:
            contact, ct = r["phone"], "tel"
        elif socials:
            soc = socials[0]
            if "t.me/" in soc:
                contact, ct = "@" + soc.split("t.me/")[1].strip("/").lstrip("@"), "tg"
            elif soc.startswith("@"):
                contact, ct = soc, "tg"
            else:
                contact, ct = soc, "url"
        else:
            contact, ct = "", "tel"

        try:
            created = datetime.datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
            t = max(0, int((now - created).total_seconds() // 60))
        except Exception:
            t = 0

        score = r["score"] or 0
        prio = "hot" if score >= 70 else "warm" if score >= 45 else "cold"
        desc = (r["snippet"] or "").strip()
        if not desc:
            parts = []
            if r["address"]:
                parts.append("Адрес: " + r["address"])
            if r["hours"]:
                parts.append("Часы работы: " + r["hours"])
            desc = ". ".join(parts) or (
                niches.NICHE_LABELS.get(r["niche"], "бизнес")
                + f" в {r['city']}; сайта нет."
            )

        out.append({
            "id": r["id"],  # внутренний id базы — сайт по нему отличает новые лиды от старых
            "n": r["name"] or "(без названия)",
            "c": r["city"] or "—",
            "niche": NICHE_TO_SITE.get(r["niche"], r["niche"]),
            "src": "web" if r["source"] in ("web", "yandex") else "osm",
            "prio": prio,
            "t": t,
            "ct": ct,
            "contact": contact,
            "bud": "б/д",
            "br": None,
            "d": desc,
            "sig": reasons[:4] or ["Есть контакт для связи"],
            "srcd": (r["url"] if r["source"] == "web" and r["url"]
                     else f"OpenStreetMap · выгрузка бота {str(r['created_at'])[:10]}"),
        })
    return out


def find_site_file(bot_dir: Path) -> Path | None:
    """Где лежит сайт (leadradar.html или index.html): рядом с папкой бота или внутри неё."""
    bot_dir = Path(bot_dir)
    for name in ("leadradar.html", "index.html"):
        for cand in (bot_dir.parent / name, bot_dir / name):
            if cand.exists():
                return cand
    return None


def update_html(html_path: Path, data: list) -> None:
    """Вписывает лиды между маркерами в файл сайта (идемпотентно)."""
    html_path = Path(html_path)
    text = html_path.read_text(encoding="utf-8")
    if MARK_START not in text or MARK_END not in text:
        raise SystemExit(
            f"В {html_path.name} нет маркеров данных — файл сайта старой версии.\n"
            "Скачай свежий leadradar.html (где кнопка «📥 Загрузить данные бота») и повтори."
        )
    block = (MARK_START + "\nconst BUILT_IN = "
             + json.dumps(data, ensure_ascii=False) + ";\n" + MARK_END)
    pattern = re.escape(MARK_START) + r"[\s\S]*?" + re.escape(MARK_END)
    text = re.sub(pattern, lambda m: block, text, count=1)
    html_path.write_text(text, encoding="utf-8")


def write_json(json_path: Path, data: list) -> None:
    """Выгрузка в leads.json рядом с сайтом — для живого обновления (опрос каждые 20 с)."""
    Path(json_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
