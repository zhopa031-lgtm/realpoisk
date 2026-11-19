# -*- coding: utf-8 -*-
"""CLI без бота: искать в терминале, тесты, проверка источников, экспорт.

Примеры:
    python cli.py search --город Казань --ниша beauty
    python cli.py intake
    python cli.py stats
    python cli.py export
    python cli.py selftest     — проверка всего конвейера на фикстуре (без сети)
    python cli.py doctor       — какие источники доступны с этого компьютера
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from leadgen import export, messages, niches, overpass, site  # noqa: E402
from leadgen.nominatim import geocode_area  # noqa: E402
from leadgen.pipeline import Pipeline  # noqa: E402
from leadgen.scoring import score_lead  # noqa: E402
from leadgen.settings import load_settings, next_cities  # noqa: E402
from leadgen.storage import Storage  # noqa: E402
from leadgen.utils import yandex_map_url  # noqa: E402

DB = ROOT / "data" / "leads.db"


def _pipeline():
    settings = load_settings()
    return settings, Pipeline(settings, Storage(DB))


def cmd_search(args):
    settings, pipe = _pipeline()
    cities = [args.city] if args.city else [settings.city_main]
    if args.all_cities:
        cities = settings.cities
    niche_list = None
    if args.niche:
        niche_list = [niches.resolve_niche(args.niche) or args.niche]

    print(f"Ищу: {', '.join(cities)} · ниши: {', '.join(niche_list or settings.niches_active)}\n")
    result = pipe.run_search(cities, niche_list, progress=lambda m: print("  " + m, end="\r"))
    print()

    for err in result["errors"]:
        print(f"⚠️  {err}")
    top = result["new"][: args.top]
    if not top:
        print("Новых лидов нет. Непоказанных смотри: python cli.py more")
        return
    print(f"Новых: {len(result['new'])} (дубликатов пропущено: {result['duplicates']})")
    print("=" * 70)
    for lead in top:
        row = Storage(DB).get(lead["id"])
        text = messages.build_texts(lead, settings)[0]
        print(f"🔥 [{lead['score']}/100] #{lead['id']} {lead['name']} — {lead['city']}")
        print(f"   ниша: {messages.niche_label(lead['niche'])}")
        print(f"   адрес: {lead['address'] or '—'}")
        print(f"   телефон: {lead['phone'] or 'нет в данных'}")
        if lead["hours"]:
            print(f"   часы: {lead['hours']}")
        print(f"   приоритет: {lead['reasons']}")
        print(f"   карта: {yandex_map_url(lead['name'], lead['city'], lead['address'])}")
        print(f"   текст:\n   {' ' + text.replace(chr(10), chr(10) + '   ')}")
        print("-" * 70)


def cmd_more(args):
    settings, _ = _pipeline()
    storage = Storage(DB)
    rows = storage.top_unshown(args.top, settings.get("min_score", 40),
                               bool(settings.get("require_contact", True)))
    if not rows:
        print("Непоказанных нет — запусти search.")
        return
    for row in rows:
        print(f"🔥 [{row['score']}/100] #{row['id']} {row['name']} — {row['city']} "
              f"({messages.niche_label(row['niche'])})")
        print(f"   телефон: {row['phone'] or '—'}")
        print(f"   приоритет: {row['reasons']}\n")


def cmd_intake(args):
    settings, pipe = _pipeline()
    print("Ищу «нужен сайт» в интернете…")
    found, errors = pipe.run_web_intake()
    for err in errors:
        print(f"⚠️  {err}")
    if not found:
        print("Новых заявок нет (или источник недоступен — попробуй позже).")
        return
    for lead in found:
        print(f"🌐 [{lead['score']}/100] #{lead['id']} {lead['name']}")
        print(f"   {lead['url']}\n")


def cmd_stats(args):
    storage = Storage(DB)
    st = storage.stats()
    print(f"Всего лидов: {st['total']} · средний скор: {st['avg_score']}")
    print("Статусы:", ", ".join(f"{k}: {v}" for k, v in st["by_status"].items()))
    print("Ниши:", ", ".join(f"{k}: {v}" for k, v in st["by_niche"].items()))
    print("Города:", ", ".join(f"{c}: {n}" for c, n in st["by_city"].items()))


def cmd_export(args):
    storage = Storage(DB)
    rows = storage.export_rows()
    if not rows:
        print("База пуста.")
        return
    path = export.export_xlsx(rows, ROOT / "data" / "exports")
    print(f"Сохранено: {path} ({len(rows)} лидов)")


# ключ базы → название ниши для сайта
NICHE_TO_SITE = {
    "beauty": "Салоны красоты", "auto": "Автосервисы", "food": "Кафе и рестораны",
    "health": "Медцентры", "sport": "Фитнес", "edu": "Учебные центры",
    "services": "Сервисные бизнесы", "web_request": "Заказы из интернета",
}


def _site_rows():
    """Лиды из базы в формате сайта; None, если база пуста."""
    storage = Storage(DB)
    rows = storage.export_rows()
    if not rows:
        print("База пуста — сначала запусти: python cli.py search --all-cities")
        return None
    return site.build_leads(rows)


def cmd_export_json(args):
    """Выгрузка лидов в JSON для сайта leadradar.html (drag&drop или fetch)."""
    data = _site_rows()
    if data is None:
        return
    path = Path(args.path) if getattr(args, "path", None) else (ROOT / "data" / "leads.json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Сохранено: {path} ({len(data)} лидов)")
    print("Перетащи файл в окно leadradar.html или запусти update_site.bat — впишет сам.")


def cmd_update_site(args):
    """Вшивает лиды из базы прямо в leadradar.html — сайту больше ничего не нужно."""
    data = _site_rows()
    if data is None:
        return
    if args.path:
        path = Path(args.path)
        if not path.exists():
            print(f"Файл не найден: {path}")
            return
    else:
        path = site.find_site_file(ROOT)
        if not path:
            print("Не нашёл leadradar.html рядом с ботом (ищу в папке бота и на уровень выше).")
            print("Варианты: положи файл сайта рядом с папкой бота, или укажи путь:")
            print('  python cli.py update-site "C:\\путь\\leadradar.html"')
            return
    site.update_html(path, data)
    site.write_json(path.parent / "leads.json", data)
    print(f"Готово: вписал {len(data)} лидов в {path.name} (+ leads.json рядом)")
    print("Открывай сайт двойным кликом — данные уже внутри, ничего вставлять не надо.")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Без спама в консоль: опросы каждые 20 секунд не логируем."""
    def log_message(self, fmt, *args):
        pass


def _start_site_server(path: Path, port: int):
    """Локальный сервер в папке сайта. Возвращает (httpd, url) или (None, None)."""
    handler = functools.partial(_QuietHandler, directory=str(path.parent))
    for p in range(port, port + 10):
        try:
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", p), handler)
            return httpd, f"http://localhost:{httpd.server_address[1]}/{path.name}"
        except OSError:
            continue
    return None, None


def cmd_serve_site(args):
    """Живой режим: выгружает базу в leads.json, поднимает локальный сервер,
    открывает сайт в браузере. Сайт сам добавляет новые лиды каждые 20 секунд."""
    data = _site_rows()
    if data is None:
        return
    if args.path:
        path = Path(args.path)
    else:
        path = site.find_site_file(ROOT)
    if not path or not path.exists():
        print("Не нашёл leadradar.html — положи его рядом с папкой бота или укажи путь:")
        print('  python cli.py serve-site --path "C:\\путь\\leadradar.html"')
        return
    site.write_json(path.parent / "leads.json", data)
    print(f"База выгружена: {path.parent / 'leads.json'} ({len(data)} лидов)")

    httpd, url = _start_site_server(path, args.port)
    if httpd is None:
        print(f"Порты {args.port}–{args.port + 9} заняты. Запусти с другим: --port 9000")
        return
    print()
    print(f"🟢 Живой режим включён: {url}")
    print("   Сайт сам добавляет новые лиды каждые 20 секунд (старые не исчезают).")
    print("   Окно можно свернуть, но НЕ закрывать — сайт работает, пока оно открыто.")
    print("   Остановить: закрыть это окно или Ctrl+C.")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nЖивой режим остановлен.")


def cmd_auto(args):
    """Полная автоматизация без Telegram: бот сам ищет лидов каждые N минут,
    обновляет сайт и базу. Сайт открывается в браузере и пополняется сам."""
    if args.every < 15:
        print("Интервал меньше 15 минут не ставлю: источники (OpenStreetMap) забанят IP")
        print("за слишком частые запросы. Запусти с --every 15 или больше (по умолчанию 60).")
        return
    if args.path:
        path = Path(args.path)
    else:
        path = site.find_site_file(ROOT)
    if not path or not path.exists():
        print("Не нашёл leadradar.html — положи его рядом с папкой бота или укажи путь:")
        print('  python cli.py auto --path "C:\\путь\\leadradar.html"')
        return

    def refresh_files():
        """База → leadradar.html + leads.json рядом с сайтом. Возвращает кол-во лидов."""
        data = _site_rows()
        if data is None:
            return 0
        site.update_html(path, data)
        site.write_json(path.parent / "leads.json", data)
        return len(data)

    def worker():
        first = True
        while not stop.is_set():
            try:
                print(f"[{time.strftime('%H:%M:%S')}] Ищу свежих лидов…")
                settings, _ = _pipeline()
                new, dup = _auto_cycle(settings, with_web=first)
                first = False
                total = refresh_files()
                if new:
                    print(f"[{time.strftime('%H:%M:%S')}] Новых: {new} (дубликатов: {dup}) "
                          f"· на сайте: {total} лидов — сайт обновится сам")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Новых нет (дубликатов: {dup}) "
                          f"· на сайте: {total} лидов")
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Ошибка поиска (повторю в следующий раз): {e}")
            stop.wait(args.every * 60)

    stop = threading.Event()
    httpd, url = _start_site_server(path, args.port)
    if httpd is None:
        print(f"Порты {args.port}–{args.port + 9} заняты. Запусти с другим портом: --port 9000")
        return
    print("🤖 Полная автоматизация включена")
    print(f"   Поиск: каждые {args.every} мин — сам, круглосуточно, пока открыто это окно")
    print(f"   Сайт:  {url} — откроется сам; новые лиды добавляет сам каждые 20 секунд")
    print("   Остановить: закрыть окно или Ctrl+C")
    threading.Thread(target=worker, daemon=True).start()
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        stop.set()
        print("\nАвтоматизация остановлена.")


def _auto_cycle(settings, with_web=False, k_cities=None):
    """Один цикл поиска: ротация городов → поиск → (опц.) заявки из интернета.
    Возвращает (новых, дубликатов)."""
    _, pipe = _pipeline()
    cities = next_cities(settings, k_cities)
    print("  города: " + ", ".join(cities))
    res = pipe.run_search(cities, None, progress=lambda m: print("  " + m, end="\r"))
    print()
    for err in res["errors"]:
        print("  ⚠️", err)
    if with_web and settings.get("web_intake"):
        try:
            web, werr = pipe.run_web_intake()
            for err in werr:
                print("  ⚠️", err)
            print(f"  заявки из интернета: {len(web)}")
        except Exception as e:
            print("  web-поиск не удался:", e)
    return len(res["new"]), res["duplicates"]


def cmd_once(args):
    """Один цикл: поиск (ротация городов) → выгрузка leads.json → выход.
    Именно так обновляет лиды GitHub Actions; можно запускать и вручную."""
    settings = load_settings()
    try:
        new, dup = _auto_cycle(settings, with_web=True, k_cities=args.cities)
    except Exception as e:
        print(f"Поиск не удался (источник недоступен?): {e}")
        print("Существующие данные не тронуты — повтори позже.")
        return
    data = _site_rows()
    if data is None:
        return
    path = Path(args.path) if args.path else site.find_site_file(ROOT)
    out = (path.parent / "leads.json") if (path and path.exists()) else (ROOT / "leads.json")
    site.write_json(out, data)
    print(f"Готово: новых {new} (дубликатов: {dup}) · в базе {len(data)} лидов → {out}")


def cmd_selftest(args):
    """Полный конвейер на фикстуре: парсинг → скоринг → дедуп → тексты → база."""
    fixture = ROOT / "fixtures" / "overpass_sample.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    settings, _ = _pipeline()
    test_db = ROOT / "data" / "selftest.db"
    if test_db.exists():
        test_db.unlink()
    storage = Storage(test_db)

    groups = {}
    for el in raw["elements"]:
        niche = (el.get("tags") or {}).get("_fixture_niche", "beauty")
        groups.setdefault(niche, []).append(el)

    leads = []
    for niche, elements in groups.items():
        leads += overpass.parse_elements({"elements": elements}, niche, settings.city_main)
    assert len(leads) >= 7, f"ожидали ≥7 лидов, получили {len(leads)}"

    for lead in leads:
        lead["score"], lead["reasons"] = score_lead(lead, settings)
        lead_id, is_new = storage.add_lead(lead)
        assert is_new, "дедуп не сработал"
        lead["id"] = lead_id

    dup_id, is_new = storage.add_lead(leads[0])
    assert not is_new, "повторная вставка не задедуплировалась"

    phones = [l for l in leads if l["phone"]]
    assert phones, "телефоны не нормализовались"
    assert all(p.startswith("+7") or p.startswith("+") for p in (l["phone"] for l in phones))

    best = sorted(leads, key=lambda l: l["score"], reverse=True)[0]
    text = messages.build_texts(best, settings)[0]
    assert best["name"][:6] in text, "текст не персонализирован"
    st = storage.stats()
    assert st["total"] == len(leads)

    path = export.export_xlsx(storage.export_rows(), ROOT / "data" / "selftest_exports")
    assert path.exists() and path.stat().st_size > 5000

    print(f"Лидов в selftest: {len(leads)}")
    for lead in sorted(leads, key=lambda l: l['score'], reverse=True):
        print(f"  [{lead['score']:3d}] {lead['name']} — {lead['city']} "
              f"({messages.niche_label(lead['niche'])}) tel={lead['phone'] or '—'}")
    print(f"Топ-скор: {best['score']} у «{best['name']}» · причины: {best['reasons']}")
    print(f"Excel: {path.name}, {path.stat().st_size} байт")
    print("SELFTEST PASS ✅")


def cmd_doctor(args):
    """Проверяет доступность источников с ЭТОГО компьютера."""
    settings = load_settings()
    print("Проверка источников…\n")

    try:
        area = geocode_area(settings.city_main, settings.get("country_code", "ru"))
        print(f"  ✅ Nominatim (геокодинг): {settings.city_main} → area {area}")
    except Exception as e:
        print(f"  ❌ Nominatim: {e}")

    for mirror in overpass.DEFAULT_MIRRORS + settings.get("overpass_mirrors", []):
        try:
            import httpx
            r = httpx.post(mirror, data={"data": "[out:json][timeout:25];node(1);out;"},
                           timeout=35, headers={"User-Agent": overpass.UA})
            ok = r.status_code == 200
            print(f"  {'✅' if ok else '❌'} Overpass {mirror.split('/')[2]}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  ❌ Overpass {mirror}: {type(e).__name__}")

    if settings.get("yandex_api_key"):
        print("  ✅ Ключ Яндекса указан — источник включён")
    else:
        print("  ⚪ Ключ Яндекса не указан — работаем по OpenStreetMap (это норм)")

    try:
        import httpx
        r = httpx.get("https://lite.duckduckgo.com/lite/?q=test",
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=20, follow_redirects=True)
        ok = r.status_code == 200
        print(f"  {'✅' if ok else '❌'} DuckDuckGo (заявки из интернета): HTTP {r.status_code}")
    except Exception as e:
        print(f"  ❌ DuckDuckGo: {type(e).__name__} — заявки из интернета будут недоступны с этого IP")

    token = (settings.get("bot_token") or "").strip()
    print(f"  {'✅' if token and 'ВСТАВЬ' not in token.upper() else '❌'} Токен бота "
          f"{'указан' if token and 'ВСТАВЬ' not in token.upper() else 'не указан (config.json)'}")

    if DB.exists():
        print(f"  ✅ База: {DB} ({Storage(DB).stats()['total']} лидов)")
    else:
        print("  ⚪ База ещё не создана — будет при первом поиске")


def main():
    parser = argparse.ArgumentParser(description="vibe-leadgen CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("search", help="искать бизнесы без сайта")
    p.add_argument("--city", help="город (по умолчанию city_main)")
    p.add_argument("--niche", help="ниша: beauty/auto/food/health/sport/edu/services")
    p.add_argument("--all-cities", action="store_true", help="город + сателлиты")
    p.add_argument("--top", type=int, default=10, help="сколько показать")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("more", help="показать непоказанных лидов")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_more)

    p = sub.add_parser("intake", help="«нужен сайт» из интернета")
    p.set_defaults(func=cmd_intake)

    p = sub.add_parser("stats", help="статистика базы")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("export", help="выгрузка в Excel")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("export-json", help="выгрузка лидов в JSON для сайта leadradar.html")
    p.add_argument("path", nargs="?", help="куда сохранить (по умолчанию data/leads.json)")
    p.set_defaults(func=cmd_export_json)

    p = sub.add_parser("update-site", help="вшить лиды из базы прямо в leadradar.html")
    p.add_argument("path", nargs="?", help="путь к leadradar.html (по умолчанию ищем рядом с ботом)")
    p.set_defaults(func=cmd_update_site)

    p = sub.add_parser("serve-site", help="живой режим: сервер + сайт самообновляется каждые 20 сек")
    p.add_argument("path", nargs="?", help="путь к leadradar.html (по умолчанию ищем рядом с ботом)")
    p.add_argument("--port", type=int, default=8899, help="порт сервера (по умолчанию 8899)")
    p.set_defaults(func=cmd_serve_site)

    p = sub.add_parser("auto", help="полная автоматизация: сам ищет каждые N мин + живой сайт (без Telegram)")
    p.add_argument("path", nargs="?", help="путь к leadradar.html (по умолчанию ищем рядом с ботом)")
    p.add_argument("--every", type=int, default=60, help="интервал поиска в минутах (по умолчанию 60, минимум 15)")
    p.add_argument("--port", type=int, default=8899, help="порт сервера (по умолчанию 8899)")
    p.set_defaults(func=cmd_auto)

    p = sub.add_parser("once", help="один цикл поиска + выгрузка leads.json (для GitHub Actions и вручную)")
    p.add_argument("path", nargs="?", help="путь к сайту index.html/leadradar.html (по умолчанию ищем рядом)")
    p.add_argument("--cities", type=int, default=None, help="сколько городов за раз (по умолчанию из config)")
    p.set_defaults(func=cmd_once)

    p = sub.add_parser("selftest", help="тест конвейера на фикстуре (без сети)")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("doctor", help="проверить доступность источников")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
