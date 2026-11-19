# -*- coding: utf-8 -*-
"""Источник №3: «заявки из интернета» — люди, которые прямо сейчас ищут,
кто им сделает сайт. Ищем через DuckDuckGo (без ключа) по запросам из config.

Замечание честности: DDG иногда режет автоматические запросы из дата-центров,
но с домашнего/офисного IP обычно работает. Если источник недоступен, бот
просто не прикладывает этот блок к рассылке — остальное работает.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"}

RESULT_A = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
RESULT_A_REV = re.compile(r'<a[^>]*href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>', re.S)
LITE_LINK = re.compile(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
SNIPPET = re.compile(r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>', re.S)
TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return TAG.sub("", s).replace("&quot;", '"').replace("&amp;", "&").strip()


def _real_url(href: str) -> str:
    """DDG заворачивает ссылки в /l/?uddg=... — разворачиваем."""
    if "uddg=" in href:
        q = parse_qs(urlparse(href).query)
        if "uddg" in q:
            return unquote(q["uddg"][0])
    if href.startswith("//"):
        href = "https:" + href
    return href


def _dedup(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        p = urlparse(it["url"])
        key = f"{p.netloc}{p.path}".rstrip("/")
        if not key or key in seen or "duckduckgo" in p.netloc:
            continue
        seen.add(key)
        out.append(it)
    return out


def _parse_html(html: str) -> list[dict]:
    """Результаты html.duckduckgo.com — порядок атрибутов в <a> бывает разный."""
    items = []
    snippets = [_clean(s) for s in SNIPPET.findall(html)]
    for regex in (RESULT_A, RESULT_A_REV):
        for i, (href, title) in enumerate(regex.findall(html)):
            items.append({
                "title": _clean(title),
                "url": _real_url(href),
                "snippet": snippets[i] if i < len(snippets) else "",
            })
        if items:
            break
    return items


def _parse_lite(html: str) -> list[dict]:
    items = []
    for href, title in LITE_LINK.findall(html):
        items.append({"title": _clean(title), "url": _real_url(href), "snippet": ""})
    return items


def fetch_web_leads(queries: list[str], limit: int = 5) -> list[dict]:
    """Возвращает заявки (посты людей, ищущих исполнителя сайта)."""
    results: list[dict] = []
    used_endpoint = None
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=25) as client:
        for q in queries:
            html = ""
            for endpoint, parser in (
                ("https://html.duckduckgo.com/html/?q=", _parse_html),
                ("https://lite.duckduckgo.com/lite/?q=", _parse_lite),
            ):
                try:
                    r = client.get(endpoint + httpx.QueryParams({"q": q}).get("q"))
                    if r.status_code == 200 and ("result" in r.text or "result-link" in r.text):
                        parsed = parser(r.text)
                        if parsed:
                            html = "ok"
                            used_endpoint = endpoint
                            for item in parsed:
                                item["query"] = q
                            results.extend(parsed)
                            break
                except httpx.HTTPError:
                    continue
            if html != "ok":
                continue
    results = _dedup(results)
    hashed = []
    for it in results:
        it["source_id"] = "web:" + hashlib.md5(it["url"].encode()).hexdigest()[:12]
        hashed.append(it)
    if used_endpoint is None and not results:
        raise RuntimeError("DuckDuckGo не отвечает (IP заблокирован или нет сети)")
    return hashed[:limit]
