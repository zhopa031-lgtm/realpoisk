# -*- coding: utf-8 -*-
"""TG-бот лидогена: авто-поиск бизнесов без сайта, скоринг, персональные тексты,
кнопки «в 1 клик» и экспорт в Excel.

Запуск: python bot.py   (токен — в config.json, ключи — в README.md)
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    FSInputFile,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    CallbackQuery,
)

LP_OFF = LinkPreviewOptions(is_disabled=True)

from leadgen import export, messages, niches, site
from leadgen.pipeline import Pipeline
from leadgen.settings import ROOT, load_settings, load_state, save_state, next_cities
from leadgen.storage import Storage
from leadgen.utils import esc, tg_link, yandex_map_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("leadgen")

SETTINGS = load_settings()
STORAGE = Storage(ROOT / "data" / "leads.db")
PIPELINE = Pipeline(SETTINGS, STORAGE)
DP = Dispatcher()

HELP_TEXT = (
    "<b>Что умею</b>\n\n"
    "/искать [ниша] [город] — найти бизнесы без сайта прямо сейчас\n"
    "  примеры: <code>/искать авто</code>, <code>/искать красота Казань</code>, <code>/искать all</code>\n"
    "/ещё — показать следующую партию непоказанных лидов\n"
    "/стата — сколько найдено, отправлено, конверсия\n"
    "/экспорт — выгрузить всё в Excel\n"
    "/настройки — текущие настройки и путь к config.json\n"
    "/помощь — этот текст\n\n"
    "Утром в {hh:02d}:{mm:02d} сам ищу свежих лидов и присылаю топ по скору."
)


# ---------- служебное ----------
def _admin_id() -> int | None:
    return load_state().get("admin_chat_id")


def _gate(msg: Message) -> bool:
    """Бот приватный: после первого /start отвечает только владельцу."""
    admin = _admin_id()
    if admin is None:
        save_state({"admin_chat_id": msg.chat.id})
        return True
    if msg.chat.id != admin:
        return False
    return True


def _business_card(row) -> tuple[str, InlineKeyboardMarkup]:
    lead = dict(row)
    variant = row["text_variant"]
    texts = messages.build_texts(lead, SETTINGS)
    text = texts[variant]

    lines = [
        f"🔥 <b>Лид #{row['id']}</b> · <b>{row['score']}/100</b> · {esc(messages.niche_label(lead['niche']))}",
        f"✅ {esc(row['reasons'])}",
        f"🏢 <b>{esc(lead['name'])}</b>",
    ]
    geo = ", ".join(x for x in (lead["city"], lead["address"]) if x)
    if geo:
        lines.append(f"📍 {esc(geo)}")
    if lead["hours"]:
        lines.append(f"⏰ {esc(lead['hours'])}")
    if lead["phone"]:
        lines.append(f"📞 <code>{esc(lead['phone'])}</code>")
    else:
        lines.append("📞 телефона нет в данных — контакт ищи на карте или в 2ГИС")
    if lead["email"]:
        lines.append(f"📧 {esc(lead['email'])}")
    import json as _json
    socials = _json.loads(lead["socials"] or "[]")
    if socials:
        lines.append(f"🔗 {esc(', '.join(socials))}")
    lines += [
        "─────────",
        f"📝 Готовый текст (вариант {variant + 1}/3):",
        f"<blockquote expandable>{esc(text)}</blockquote>",
    ]

    buttons = []
    if lead["phone"]:
        buttons.append([InlineKeyboardButton(text="✈️ Написать в Telegram", url=tg_link(lead["phone"]))])
    buttons.append([InlineKeyboardButton(
        text="🗺 Найти на Яндекс.Картах",
        url=yandex_map_url(lead["name"], lead["city"], lead["address"]),
    )])
    buttons.append([
        InlineKeyboardButton(text="📄 Текст отдельно", callback_data=f"txt:{row['id']}"),
        InlineKeyboardButton(text="🔄 Другой текст", callback_data=f"var:{row['id']}"),
    ])
    buttons.append([
        InlineKeyboardButton(text="✅ Отправил", callback_data=f"sent:{row['id']}"),
        InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip:{row['id']}"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


def _web_card(row) -> tuple[str, InlineKeyboardMarkup]:
    text = messages.web_reply_text(SETTINGS)
    lines = [
        f"🌐 <b>Заявка из интернета</b> · <b>{row['score']}/100</b>",
        f"📝 {esc(row['name'])}",
    ]
    if row["snippet"]:
        lines.append(f"👀 {esc(row['snippet'][:200])}")
    lines.append(f"🔗 {esc(row['url'])}")
    lines += ["─────────", "📝 Готовый отклик:", f"<blockquote expandable>{esc(text)}</blockquote>"]

    buttons = [
        [InlineKeyboardButton(text="🌐 Открыть пост", url=row["url"])],
        [InlineKeyboardButton(text="📄 Текст отклика отдельно", callback_data=f"txt:{row['id']}")],
        [
            InlineKeyboardButton(text="✅ Отправил", callback_data=f"sent:{row['id']}"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip:{row['id']}"),
        ],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


async def _send_lead(bot: Bot, chat_id: int, row) -> None:
    if row["source"] == "web":
        text, kb = _web_card(row)
    else:
        text, kb = _business_card(row)
    await bot.send_message(chat_id, text, reply_markup=kb, link_preview_options=LP_OFF)


# ---------- команды ----------
@DP.message(CommandStart())
async def cmd_start(msg: Message):
    if not _gate(msg):
        await msg.answer("Это приватный бот. Владелец уже назначен.")
        return
    s = SETTINGS
    await msg.answer(
        "<b>Привет! Я твой лидоген для вайбкодинга 💼</b>\n\n"
        "Ищу бизнесы без сайта (OpenStreetMap + Яндекс при ключе), сортирую «жирных»,\n"
        "готовлю персональный текст под каждого и контакт для Telegram.\n\n"
        + HELP_TEXT.format(hh=s.get("schedule_hour"), mm=s.get("schedule_minute"))
    )


@DP.message(Command("искать", "search"))
async def cmd_search(msg: Message):
    if not _gate(msg):
        return
    parts = (msg.text or "").split()[1:]
    city_list, niche_list = None, None
    for token in parts:
        token_l = token.lower()
        if token_l in ("all", "всё", "все"):
            city_list = SETTINGS.cities
            continue
        city_match = next((c for c in SETTINGS.cities if c.lower() == token_l), None)
        if city_match:
            city_list = [city_match] if city_list is None else city_list + [city_match]
            continue
        niche = niches.resolve_niche(token)
        if niche:
            niche_list = [niche] if niche_list is None else niche_list + [niche]
            continue
        await msg.answer(f"🤔 Не понял «{esc(token)}». Ниша: {', '.join(sorted(niches.NICHE_ALIASES))}. "
                         f"Город: {esc(', '.join(SETTINGS.cities))} или <code>all</code>.")
        return

    if city_list is None:
        city_list = next_cities(SETTINGS)  # ротация: за раз часть городов, все — по кругу
    status = await msg.answer("🔍 Запускаю поиск (это может занять пару минут)…")
    result = await asyncio.to_thread(
        PIPELINE.run_search, city_list, niche_list, None
    )

    web, web_errors = [], []
    if SETTINGS.get("web_intake"):
        web, web_errors = await asyncio.to_thread(PIPELINE.run_web_intake)

    lines = [
        f"✅ Проверено записей: {result['scanned']}, новых: <b>{len(result['new'])}</b>, "
        f"дубликатов: {result['duplicates']}"
    ]
    for err in result["errors"] + web_errors:
        lines.append(f"⚠️ {esc(err)}")
    await status.edit_text("\n".join(lines), link_preview_options=LP_OFF)

    await _show_batch(msg.bot, msg.chat.id, SETTINGS.get("leads_per_digest", 8))
    for lead in web[: SETTINGS.get("digest_web_max", 3)]:
        row = STORAGE.get(lead["id"])
        if row:
            STORAGE.mark_shown(row["id"])
            await _send_lead(msg.bot, msg.chat.id, row)
            await asyncio.sleep(0.4)


@DP.message(Command("ещё", "more"))
async def cmd_more(msg: Message):
    if not _gate(msg):
        return
    await _show_batch(msg.bot, msg.chat.id, SETTINGS.get("leads_per_digest", 8))


async def _show_batch(bot: Bot, chat_id: int, limit: int) -> None:
    rows = STORAGE.top_unshown(
        limit, SETTINGS.get("min_score", 40), bool(SETTINGS.get("require_contact", True))
    )
    if not rows:
        await bot.send_message(chat_id, "Непоказанных лидов с нужным скором нет.\n"
                                        "Запусти /искать — найду новых.")
        return
    for row in rows:
        STORAGE.mark_shown(row["id"])
        await _send_lead(bot, chat_id, row)
        await asyncio.sleep(0.4)


@DP.message(Command("стата", "stats"))
async def cmd_stats(msg: Message):
    if not _gate(msg):
        return
    st = STORAGE.stats()
    bs = st["by_status"]
    sent = bs.get("sent", 0)
    clients = bs.get("client", 0)
    conv = f"{clients / sent * 100:.0f}%" if sent else "—"
    niche_lines = "\n".join(
        f"  • {esc(messages.niche_label(k))}: {v}"
        for k, v in list(st["by_niche"].items())[:7]
    )
    await msg.answer(
        f"<b>📊 Статистика</b>\n"
        f"Всего лидов: <b>{st['total']}</b> · средний скор: {st['avg_score']}\n\n"
        f"🆕 новые: {bs.get('new', 0)}\n"
        f"📨 отправлено: {sent}\n"
        f"⏭ пропущено: {bs.get('skip', 0)}\n"
        f"💰 стало клиентом: {clients} (конверсия {conv})\n\n"
        f"<b>По нишам:</b>\n{niche_lines}\n\n"
        f"<b>Топ городов:</b> " + esc(", ".join(f"{c} ({n})" for c, n in st["by_city"].items()))
    )


@DP.message(Command("экспорт", "export"))
async def cmd_export(msg: Message):
    if not _gate(msg):
        return
    rows = STORAGE.export_rows()
    if not rows:
        await msg.answer("База пуста — сначала /искать.")
        return
    path = export.export_xlsx(rows, ROOT / "data" / "exports")
    await msg.answer_document(FSInputFile(path), caption=f"📊 Экспорт: {len(rows)} лидов")


@DP.message(Command("настройки", "settings"))
async def cmd_settings(msg: Message):
    if not _gate(msg):
        return
    await msg.answer(
        "<b>⚙️ Текущие настройки</b>\n\n"
        + esc(SETTINGS.summary())
        + f"\n\nФайл настроек: <code>config.json</code> рядом с bot.py.\n"
          f"Поменяй город, сателлиты, ниши, время рассылки — и перезапусти бота."
    )


@DP.message(Command("помощь", "help"))
async def cmd_help(msg: Message):
    if not _gate(msg):
        return
    await msg.answer(HELP_TEXT.format(
        hh=SETTINGS.get("schedule_hour"), mm=SETTINGS.get("schedule_minute")))


# ---------- кнопки ----------
@DP.callback_query(F.data.startswith("txt:"))
async def cb_text(cb: CallbackQuery):
    lead_id = int(cb.data.split(":")[1])
    row = STORAGE.get(lead_id)
    if not row or cb.message is None:
        await cb.answer("Лид не найден", show_alert=True)
        return
    text = (messages.web_reply_text() if row["source"] == "web"
            else messages.build_texts(dict(row), SETTINGS)[row["text_variant"]])
    header = f"📄 Вариант {row['text_variant'] + 1}/3 — выдели и скопируй:\n\n" if row["source"] != "web" else ""
    await cb.message.answer(header + text)
    await cb.answer()


@DP.callback_query(F.data.startswith("var:"))
async def cb_variant(cb: CallbackQuery):
    lead_id = int(cb.data.split(":")[1])
    row = STORAGE.get(lead_id)
    if not row or cb.message is None:
        await cb.answer("Лид не найден", show_alert=True)
        return
    next_variant = row["text_variant"] + 1
    STORAGE.set_variant(lead_id, next_variant)
    fresh = STORAGE.get(lead_id)
    text, kb = (_web_card(fresh) if fresh["source"] == "web" else _business_card(fresh))
    await cb.message.edit_text(text, reply_markup=kb, link_preview_options=LP_OFF)
    await cb.answer(f"Вариант {fresh['text_variant'] + 1}/3")


@DP.callback_query(F.data.startswith("sent:"))
async def cb_sent(cb: CallbackQuery):
    lead_id = int(cb.data.split(":")[1])
    STORAGE.mark(lead_id, "sent")
    if cb.message:
        await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("✅ Отмечено как отправленное")


@DP.callback_query(F.data.startswith("skip:"))
async def cb_skip(cb: CallbackQuery):
    lead_id = int(cb.data.split(":")[1])
    STORAGE.mark(lead_id, "skip")
    if cb.message:
        await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("⏭ Пропущен")


# ---------- синхронизация сайта leadradar.html ----------
def update_site_file() -> None:
    """Свежая база → в leadradar.html и в leads.json рядом с сайтом (если файлы есть).

    Сайт при открытии через start_site.bat сам подхватывает leads.json каждые 20 секунд
    и добавляет новые лиды к ленте.
    """
    rows = STORAGE.export_rows()
    if not rows:
        return
    path = site.find_site_file(ROOT)
    if not path:
        log.info("leadradar.html рядом с ботом не найден — сайт не обновлял")
        return
    data = site.build_leads(rows)
    site.update_html(path, data)
    site.write_json(path.parent / "leads.json", data)
    log.info("Сайт обновлён: %s + leads.json (%d лидов)", path, len(rows))


# ---------- утренний авто-поиск ----------
async def run_digest(bot: Bot) -> None:
    admin = _admin_id()
    if not admin:
        log.info("Авто-поиск пропущен: /start ещё не был вызван")
        return
    status = await bot.send_message(admin, "🌅 Доброе утро! Ищу свежих лидов…")
    result = await asyncio.to_thread(PIPELINE.run_search, next_cities(SETTINGS), None)
    web, web_errors = [], []
    if SETTINGS.get("web_intake"):
        web, web_errors = await asyncio.to_thread(PIPELINE.run_web_intake)

    lines = [f"Проверено: {result['scanned']}, новых: <b>{len(result['new'])}</b> "
             f"(дубликатов: {result['duplicates']})"]
    for err in result["errors"] + web_errors:
        lines.append(f"⚠️ {esc(err)}")
    await status.edit_text("🌅 <b>Утренняя подборка готова</b>\n" + "\n".join(lines))

    await _show_batch(bot, admin, SETTINGS.get("leads_per_digest", 8))
    for lead in web[: SETTINGS.get("digest_web_max", 3)]:
        row = STORAGE.get(lead["id"])
        if row:
            STORAGE.mark_shown(row["id"])
            await _send_lead(bot, admin, row)
            await asyncio.sleep(0.4)

    # сайт leadradar.html: вписываем свежую базу прямо в файл, чтобы сайт
    # открывался уже с новыми лидами (без ручной вставки leads.json)
    try:
        await asyncio.to_thread(update_site_file)
    except Exception:
        log.exception("Не смог обновить leadradar.html — на бота это не влияет")


async def daily_loop(bot: Bot) -> None:
    while True:
        if not SETTINGS.get("schedule_enabled"):
            await asyncio.sleep(600)
            continue
        now = datetime.datetime.now()
        target = now.replace(hour=SETTINGS.get("schedule_hour", 9),
                             minute=SETTINGS.get("schedule_minute", 0),
                             second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        wait = (target - now).total_seconds()
        log.info("Следующий авто-поиск через %.0f мин", wait / 60)
        await asyncio.sleep(wait)
        try:
            await run_digest(bot)
        except Exception:
            log.exception("Авто-поиск упал — попробую завтра")


# ---------- тихий фоновый поиск каждые N минут ----------
async def background_cycle(bot: Bot) -> None:
    """Поиск → база → сайт. В Telegram шлёт только короткую заметку о новых лидах,
    полный дайджест остаётся на утро (schedule_hour)."""
    result = await asyncio.to_thread(PIPELINE.run_search, next_cities(SETTINGS), None)
    try:
        await asyncio.to_thread(update_site_file)
    except Exception:
        log.exception("Не смог обновить сайт")
    admin = _admin_id()
    if admin and result["new"]:
        try:
            await bot.send_message(admin, f"🔁 Фоновый поиск: +{len(result['new'])} новых лидов "
                                          f"уже на сайте. Полная подборка — утром.")
        except Exception:
            pass


async def interval_loop(bot: Bot) -> None:
    while True:
        mins = SETTINGS.get("search_every_minutes", 0)
        if not mins or mins < 15:  # 0 = выключено; меньше 15 мин нельзя — забанят источники
            await asyncio.sleep(600)
            continue
        await asyncio.sleep(mins * 60)
        try:
            await background_cycle(bot)
        except Exception:
            log.exception("Фоновый поиск не удался — попробую в следующий раз")


async def main() -> None:
    token = (SETTINGS.get("bot_token") or "").strip()
    if not token or "ВСТАВЬ" in token.upper():
        print("❌ Нет токена бота!\n"
              "1) Открой @BotFather в Telegram → /newbot → получи токен вида 123456:AA...\n"
              "2) Открой config.json рядом с bot.py и вставь токен в поле bot_token\n"
              "3) Запусти бота снова (на Windows — start.bat)")
        sys.exit(1)

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
    except Exception as e:
        print("❌ Telegram не принял этот токен (неверный bot_token или нет интернета).\n"
              f"Подробности: {e}\n"
              "Проверь bot_token в config.json и запусти бота снова.")
        sys.exit(1)

    await bot.set_my_commands([
        BotCommand(command="search", description="Искать бизнесы без сайта"),
        BotCommand(command="more", description="Следующая партия лидов"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="export", description="Экспорт в Excel"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="help", description="Помощь"),
    ])
    asyncio.create_task(daily_loop(bot))
    asyncio.create_task(interval_loop(bot))
    # поиск сразу при запуске бота (не ждать утра): свежие лиды — и в Telegram, и на сайт
    async def _first_search() -> None:
        await asyncio.sleep(3)
        if not SETTINGS.get("search_on_start"):
            return
        try:
            log.info("Поиск при запуске: проверяю источники…")
            await run_digest(bot)
        except Exception:
            log.exception("Поиск при запуске не удался — расписание продолжит по плану")
    asyncio.create_task(_first_search())
    print(f"✅ Бот @{me.username} запущен и слушает сообщения.")
    print("   Не закрывай это окно — бот работает, пока окно открыто.")
    print(f"   Города: {', '.join(SETTINGS.cities)}. Теперь нажми /start в Telegram.")
    log.info("Бот запущен. Города: %s", ", ".join(SETTINGS.cities))
    await DP.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nБот остановлен.")
