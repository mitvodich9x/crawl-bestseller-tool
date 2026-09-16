"""SQLite storage for keywords, scan runs and scraped products.

Each method opens its own connection so the scan thread and the UI thread never share one.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.paths import data_file

PRODUCT_COLUMNS = [
    "item_id", "title", "image_url", "item_url", "price", "price_text", "currency", "shipping",
    "total_sold", "one_unit_every", "sold_per_day", "days_per_sale", "sold_rate_text", "watchers",
    "start_time", "seller", "category", "condition", "quantity_available", "est_sales", "raw_json",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE COLLATE NOCASE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    trigger TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    total_found INTEGER NOT NULL DEFAULT 0,
    total_kept INTEGER NOT NULL DEFAULT 0,
    pages_used INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE TABLE IF NOT EXISTS products (
    item_id TEXT PRIMARY KEY,
    title TEXT, image_url TEXT, item_url TEXT,
    price REAL, price_text TEXT, currency TEXT, shipping REAL,
    total_sold INTEGER, one_unit_every TEXT, sold_per_day REAL, days_per_sale REAL, sold_rate_text TEXT,
    watchers INTEGER, start_time TEXT, seller TEXT, category TEXT, condition TEXT,
    quantity_available INTEGER, est_sales TEXT, raw_json TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_run_id INTEGER
);
CREATE TABLE IF NOT EXISTS product_keywords (
    item_id TEXT NOT NULL,
    keyword TEXT NOT NULL COLLATE NOCASE,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_run_id INTEGER,
    kept INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, keyword)
);
CREATE TABLE IF NOT EXISTS product_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    run_id INTEGER,
    total_sold INTEGER,
    sold_per_day REAL,
    watchers INTEGER,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pk_keyword ON product_keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_pk_run ON product_keywords(last_run_id);
CREATE INDEX IF NOT EXISTS idx_snap_item ON product_snapshots(item_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else data_file("bestseller.db")
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ---- keywords -------------------------------------------------------------------------

    def list_keywords(self, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT id, keyword, enabled, created_at FROM keywords"
        if enabled_only:
            sql += " WHERE enabled = 1"
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY id")]

    def add_keywords(self, keywords: list[str]) -> int:
        cleaned = []
        for kw in keywords:
            kw = " ".join(kw.split())
            if kw and kw.lower() not in {c.lower() for c in cleaned}:
                cleaned.append(kw)
        with closing(self._connect()) as conn, conn:
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO keywords(keyword, enabled, created_at) VALUES (?, 1, ?)",
                [(kw, _now()) for kw in cleaned],
            )
            return conn.total_changes - before

    def set_keyword_enabled(self, keyword_id: int, enabled: bool) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE keywords SET enabled = ? WHERE id = ?", (1 if enabled else 0, keyword_id))

    def delete_keywords(self, keyword_ids: list[int]) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executemany("DELETE FROM keywords WHERE id = ?", [(i,) for i in keyword_ids])

    # ---- scan runs ------------------------------------------------------------------------

    def start_run(self, trigger: str) -> int:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("INSERT INTO scan_runs(started_at, trigger) VALUES (?, ?)", (_now(), trigger))
            return cur.lastrowid

    def finish_run(self, run_id: int, status: str, total_found: int, total_kept: int, pages_used: int,
                   error: str | None = None) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE scan_runs SET finished_at=?, status=?, total_found=?, total_kept=?, pages_used=?, error=?"
                " WHERE id=?",
                (_now(), status, total_found, total_kept, pages_used, error, run_id),
            )

    def list_runs(self, limit: int = 50) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in rows]

    # ---- products -------------------------------------------------------------------------

    def save_products(self, run_id: int, keyword: str, products: list[dict], kept_ids: set[str]) -> None:
        now = _now()
        cols = PRODUCT_COLUMNS
        update_cols = [c for c in cols if c != "item_id"]
        product_sql = (
            f"INSERT INTO products({', '.join(cols)}, first_seen, last_seen, last_run_id) "
            f"VALUES ({', '.join('?' for _ in cols)}, ?, ?, ?) "
            f"ON CONFLICT(item_id) DO UPDATE SET "
            + ", ".join(f"{c}=excluded.{c}" for c in update_cols)
            + ", last_seen=excluded.last_seen, last_run_id=excluded.last_run_id"
        )
        link_sql = (
            "INSERT INTO product_keywords(item_id, keyword, first_seen, last_seen, last_run_id, kept) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(item_id, keyword) DO UPDATE SET last_seen=excluded.last_seen, "
            "last_run_id=excluded.last_run_id, kept=excluded.kept"
        )
        with closing(self._connect()) as conn, conn:
            conn.executemany(product_sql, [[p.get(c) for c in cols] + [now, now, run_id] for p in products])
            conn.executemany(
                link_sql,
                [(p["item_id"], keyword, now, now, run_id, 1 if p["item_id"] in kept_ids else 0) for p in products],
            )
            conn.executemany(
                "INSERT INTO product_snapshots(item_id, run_id, total_sold, sold_per_day, watchers, captured_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(p["item_id"], run_id, p.get("total_sold"), p.get("sold_per_day"), p.get("watchers"), now)
                 for p in products],
            )

    def query_products(self, keyword: str | None = None, run_id: int | None = None,
                       kept_only: bool = False) -> list[dict]:
        """One row per (product, keyword) so a card can show which keyword found it."""
        where, params = [], []
        if keyword:
            where.append("pk.keyword = ?")
            params.append(keyword)
        if run_id:
            where.append("pk.last_run_id = ?")
            params.append(run_id)
        if kept_only:
            where.append("pk.kept = 1")
        sql = (
            "SELECT p.*, pk.keyword AS keyword, pk.kept AS kept, pk.first_seen AS keyword_first_seen "
            "FROM product_keywords pk JOIN products p ON p.item_id = pk.item_id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.total_sold DESC, p.sold_per_day DESC"
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def keywords_with_products(self) -> list[str]:
        with closing(self._connect()) as conn:
            return [r[0] for r in conn.execute("SELECT DISTINCT keyword FROM product_keywords ORDER BY keyword")]
