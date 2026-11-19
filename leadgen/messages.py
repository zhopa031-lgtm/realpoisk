# -*- coding: utf-8 -*-
"""Генератор персональных сообщений для заказчика.

Стиль — как пишет живой человек в личку: короткие фразы, без канцелярита
и «идеальной» структуры. Факты только честные: сайта нет, что могу сделать,
что покажу демо. Первое сообщение заканчивается ссылкой на портфолио.
"""
from __future__ import annotations

from .niches import NICHE_BENEFITS, NICHE_LABELS, NICHE_LABELS_GEN

TEMPLATES = [
    # 1 — живой, от лица человека, который реально листал карты
    (
        "Привет! Листал карты по {city}, наткнулся на «{name}» и захотел глянуть ваш сайт — "
        "а его нет. Решил написать напрямую.\n\n"
        "Смысл простой: без сайта вас находят только те, кто сам листает карты и дозванивается. "
        "Остальные уходят к тем, у кого есть сайт с ценами и записью.\n\n"
        "Я делаю такие сайты: {benefit}, нормально открываются с телефона, заявки летят "
        "сразу в телеграм или вотсап. Могу собрать демо-страницу под вас — посмотришь ещё до оплаты.\n\n"
        "Если интересно, напиши пару слов сюда. Начну отвечать не шаблонами, а по делу."
    ),
    # 2 — короткий и по делу
    (
        "Добрый день! Коротко: у «{name}» сайта нет, и клиенты из поиска уходят конкурентам.\n\n"
        "Делаю сайты для {niche_gen}: {benefit}. По срокам — около недели, цена фиксированная, "
        "правки делаю пока не понравится.\n\n"
        "Скинуть примеры и цену под вас? Тут отвечу быстрее, чем на звонок."
    ),
    # 3 — через вопрос, без давления
    (
        "Привет! А вы специально не заводили сайт для «{name}»?\n\n"
        "Спрашиваю без подвоха: делаю сайты для {niche_gen}, и в {city} почти все уже с сайтами — "
        "вы в меньшинстве, и это скорее потерянные заявки, чем осознанный выбор.\n\n"
        "Если надумаете: {benefit}, демо покажу заранее, после запуска не пропадаю.\n\n"
        "Просто скажите «да» — скину пример."
    ),
]

WEB_REPLY_TEMPLATE = (
    "Привет! Увидел ваш пост про сайт — как раз тем и занимаюсь: лендинги, каталоги, "
    "онлайн-запись, приём заявок в телеграм или вотсап.\n\n"
    "Напишите пару слов о задаче — скажу сроки и цену без «от» и вилок. "
    "Примеры работ скину сразу."
)


def build_texts(lead: dict, settings) -> list[str]:
    """3 персональных варианта текста для лида. В первом — ссылка на портфолио в конце."""
    name = lead.get("name") or "ваш бизнес"
    city = lead.get("city") or settings.city_main
    niche = lead.get("niche") or "services"
    niche_gen = NICHE_LABELS_GEN.get(niche, "сервисных бизнесов")
    benefit = NICHE_BENEFITS.get(niche, "каталог услуг и запись онлайн")

    texts = [tpl.format(name=name, city=city, niche_gen=niche_gen, benefit=benefit)
             for tpl in TEMPLATES]
    portfolio = (settings.get("portfolio_url") or "").strip()
    if portfolio:
        texts[0] = texts[0].rstrip() + f"\n\n{portfolio}"
    signature = (settings.get("sender_name") or "").strip()
    if signature:
        texts = [t + f"\n\n— {signature}" for t in texts]
    return texts


def web_reply_text(settings=None) -> str:
    """Готовый отклик на заявку «нужен сайт» из интернета (с портфолио в конце)."""
    text = WEB_REPLY_TEMPLATE
    portfolio = (settings.get("portfolio_url") or "").strip() if settings else ""
    if portfolio:
        text = text.rstrip() + f"\n\n{portfolio}"
    return text


def niche_label(niche: str) -> str:
    return NICHE_LABELS.get(niche, niche)
