# -*- coding: utf-8 -*-
"""SQLite-хранилище лидов: дедупликация между запусками, статусы, статистика."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,             -- osm | yandex | web
    source_id   TEXT NOT NULL UNIQUE,      -- osm:node/123 | ym:456 | web:<hash>
    name        TEXT NOT NULL DEFAULT '',
    niche       TEXT NOT NULL DEFAULT '',
    city        TEXT NOT NULL DEFAULT '',
    address     TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    socials     TEXT NOT NULL DEFAULT '[]',
    hours       TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',  -- для заявок из интернета
    snippet     TEXT NOT NULL DEFAULT '',
    lat         REAL,
    lon         REAL,
    score       INTEGER NOT NULL DEFAULT 0,
    reasons     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'new',   -- new | sent | skip | client | junk
    shown       INTEGER NOT NULL DEFAULT 0,    -- попадал ли в рассылку/просмотр
    text_variant INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status, shown, score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
"""


class Storage:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(SCHEMA)

    # ---------- запись ----------
    def add_lead(self, lead: dict) -> tuple[int, bool]:
        """Возвращает (id, новый_ли_лид). Дедуп по source_id и по телефону."""
        with self._lock:
            conn = self._conn
            phone = lead.get("phone") or ""
            if phone:
                row = conn.execute(
                    "SELECT id FROM leads WHERE phone=? LIMIT 1", (phone,)
                ).fetchone()
                if row:
                    return row["id"], False
            try:
                cur = conn.execute(
                    """INSERT INTO leads
                       (source, source_id, name, niche, city, address, phone, email,
                        socials, hours, url, snippet, lat, lon, score, reasons)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        lead.get("source", ""), lead["source_id"], lead.get("name", ""),
                        lead.get("niche", ""), lead.get("city", ""), lead.get("address", ""),
                        phone, lead.get("email", ""),
                        json.dumps(lead.get("socials", []), ensure_ascii=False),
                        lead.get("hours", ""), lead.get("url", ""), lead.get("snippet", ""),
                        lead.get("lat"), lead.get("lon"),
                        lead.get("score", 0), "; ".join(lead.get("reasons", [])),
                    ),
                )
                conn.commit()
                return cur.lastrowid, True
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT id FROM leads WHERE source_id=?", (lead["source_id"],)
                ).fetchone()
                return (row["id"] if row else 0), False

    def mark(self, lead_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE leads SET status=?, shown=1, updated_at=datetime('now','localtime') WHERE id=?",
                (status, lead_id),
            )
            self._conn.commit()

    def set_variant(self, lead_id: int, variant: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE leads SET text_variant=? WHERE id=?", (variant % 3, lead_id)
            )
            self._conn.commit()

    def mark_shown(self, lead_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE leads SET shown=1 WHERE id=?", (lead_id,))
            self._conn.commit()

    # ---------- чтение ----------
    def get(self, lead_id: int):
        return self._conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()

    def top_unshown(self, limit: int, min_score: int = 0, require_contact: bool = True):
        contact_cond = (
            "AND (phone<>'' OR email<>'' OR socials<>'[]' OR source='web')"
            if require_contact else ""
        )
        return self._conn.execute(
            f"""SELECT * FROM leads
                WHERE status='new' AND shown=0 AND score>=? {contact_cond}
                ORDER BY score DESC, id ASC LIMIT ?""",
            (min_score, limit),
        ).fetchall()

    def export_rows(self):
        return self._conn.execute(
            "SELECT * FROM leads ORDER BY score DESC, city, name"
        ).fetchall()

    def stats(self) -> dict:
        conn = self._conn
        by_status = {
            r["status"]: r["n"]
            for r in conn.execute("SELECT status, COUNT(*) n FROM leads GROUP BY status")
        }
        by_niche = {
            r["niche"]: r["n"]
            for r in conn.execute("SELECT niche, COUNT(*) n FROM leads GROUP BY niche ORDER BY n DESC")
        }
        by_city = {
            r["city"]: r["n"]
            for r in conn.execute("SELECT city, COUNT(*) n FROM leads GROUP BY city ORDER BY n DESC LIMIT 5")
        }
        total = conn.execute("SELECT COUNT(*) n FROM leads").fetchone()["n"]
        avg = conn.execute("SELECT AVG(score) a FROM leads").fetchone()["a"]
        return {
            "total": total, "by_status": by_status,
            "by_niche": by_niche, "by_city": by_city, "avg_score": round(avg or 0),
        }
