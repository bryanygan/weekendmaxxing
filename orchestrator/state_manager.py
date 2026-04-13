"""State manager — SQLite persistence for deals and run history."""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = "data/deals.db"


def init_db() -> None:
    """Create data/ directory and database tables if they don't exist."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id TEXT PRIMARY KEY,
                destination TEXT NOT NULL,
                outbound_date TEXT NOT NULL,
                airline TEXT,
                flight_price REAL,
                hotel_price REAL,
                total_estimated REAL,
                score REAL,
                seen_at TEXT,
                full_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                deals_found INTEGER,
                deals_notified INTEGER
            )
        """)
        conn.commit()
    finally:
        conn.close()


def deal_hash(deal: dict) -> str:
    """Return an MD5 hex digest uniquely identifying a deal."""
    key = (
        f"{deal.get('destination', '')}-{deal.get('outbound_date', '')}"
        f"-{deal.get('airline', '')}-{deal.get('price_usd', '')}"
    )
    return hashlib.md5(key.encode()).hexdigest()


def is_duplicate(deal: dict) -> bool:
    """Return True if this deal has already been saved."""
    init_db()
    h = deal_hash(deal)
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT 1 FROM deals WHERE id = ?", (h,)).fetchone()
        return row is not None
    finally:
        conn.close()


def save_deal(deal: dict) -> None:
    """Insert a deal into the database (ignore if duplicate)."""
    init_db()
    h = deal_hash(deal)
    best_stay = deal.get("best_stay", {})
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO deals
               (id, destination, outbound_date, airline, flight_price,
                hotel_price, total_estimated, score, seen_at, full_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                h,
                deal.get("destination", ""),
                deal.get("outbound_date", ""),
                deal.get("airline", ""),
                deal.get("price_usd"),
                best_stay.get("total_price"),
                deal.get("estimated_total"),
                deal.get("score"),
                datetime.now().isoformat(),
                json.dumps(deal, default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def log_run(started_at: str, finished_at: str, found: int, notified: int) -> None:
    """Record a pipeline run in the runs table."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO runs (started_at, finished_at, deals_found, deals_notified) VALUES (?, ?, ?, ?)",
            (started_at, finished_at, found, notified),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_deals(limit: int = 20) -> list[dict]:
    """Return recent deals ordered by seen_at descending."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT full_json FROM deals ORDER BY seen_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [json.loads(row[0]) for row in rows]
    finally:
        conn.close()
