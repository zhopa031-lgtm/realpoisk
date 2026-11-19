# -*- coding: utf-8 -*-
"""Экспорт лидов в Excel (xlsx)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .niches import NICHE_LABELS

HEADERS = ["ID", "Дата", "Город", "Ниша", "Название", "Адрес", "Телефон",
           "TG (номер)", "Часы работы", "Соцсети", "Скор", "Почему приоритет",
           "Статус", "Источник", "Ссылка", "Текст (вариант 1)"]

STATUS_RU = {"new": "новый", "sent": "отправлено", "skip": "пропущен",
             "client": "клиент", "junk": "мусор"}


def export_xlsx(rows, out_dir: str | Path) -> Path:
    from .messages import build_texts
    from .settings import load_settings

    settings = load_settings()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = out_dir / f"leads_{stamp}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Лиды"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4472C4")
    for col, title in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r, row in enumerate(rows, 2):
        socials = ", ".join(json.loads(row["socials"] or "[]")) if row["socials"] else ""
        ws.cell(row=r, column=1, value=row["id"])
        ws.cell(row=r, column=2, value=row["created_at"])
        ws.cell(row=r, column=3, value=row["city"])
        ws.cell(row=r, column=4, value=NICHE_LABELS.get(row["niche"], row["niche"]))
        ws.cell(row=r, column=5, value=row["name"])
        ws.cell(row=r, column=6, value=row["address"])
        ws.cell(row=r, column=7, value=row["phone"])
        ws.cell(row=r, column=8, value=row["phone"])
        ws.cell(row=r, column=9, value=row["hours"])
        ws.cell(row=r, column=10, value=socials)
        ws.cell(row=r, column=11, value=row["score"])
        ws.cell(row=r, column=12, value=row["reasons"])
        ws.cell(row=r, column=13, value=STATUS_RU.get(row["status"], row["status"]))
        ws.cell(row=r, column=14, value=row["source"])
        ws.cell(row=r, column=15, value=row["url"])
        ws.cell(row=r, column=16, value=build_texts(dict(row), settings)[0])

    widths = [6, 12, 14, 18, 24, 26, 16, 16, 22, 20, 7, 30, 11, 9, 30, 60]
    for col, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{max(len(rows) + 1, 2)}"
    for r in range(2, len(rows) + 2):
        ws.cell(row=r, column=16).alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(path)
    return path
