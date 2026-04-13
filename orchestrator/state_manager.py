"""State manager — SQLite persistence for deals, run history, and price tracking."""

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_key TEXT NOT NULL,
                destination TEXT NOT NULL,
                outbound_date TEXT NOT NULL,
                airline TEXT,
                price_usd REAL,
                hotel_price REAL,
                total_trip_cost REAL,
                recorded_at TEXT NOT NULL
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


def _route_key(deal: dict) -> str:
    """Key for tracking price history of a route (destination + date, ignoring airline/price)."""
    return f"{deal.get('destination', '')}-{deal.get('outbound_date', '')}"


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


def record_price(deal: dict) -> None:
    """Record a price snapshot for trend tracking."""
    init_db()
    best_stay = deal.get("best_stay", {})
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT INTO price_history
               (route_key, destination, outbound_date, airline, price_usd,
                hotel_price, total_trip_cost, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _route_key(deal),
                deal.get("destination", ""),
                deal.get("outbound_date", ""),
                deal.get("airline", ""),
                deal.get("price_usd"),
                best_stay.get("total_price"),
                deal.get("total_trip_cost"),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_price_history(destination: str, outbound_date: str, limit: int = 20) -> list[dict]:
    """Return price history for a route, ordered by recorded_at ascending."""
    init_db()
    rk = f"{destination}-{outbound_date}"
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """SELECT airline, price_usd, hotel_price, total_trip_cost, recorded_at
               FROM price_history WHERE route_key = ?
               ORDER BY recorded_at ASC LIMIT ?""",
            (rk, limit),
        ).fetchall()
        return [
            {
                "airline": r[0], "price_usd": r[1], "hotel_price": r[2],
                "total_trip_cost": r[3], "recorded_at": r[4],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_price_drop(deal: dict) -> float | None:
    """Return the price drop from the previous observation, or None if no history."""
    history = get_price_history(deal.get("destination", ""), deal.get("outbound_date", ""))
    if len(history) < 2:
        return None
    prev = history[-2].get("total_trip_cost", 0) or 0
    current = deal.get("total_trip_cost", 0)
    if prev > 0:
        return prev - current
    return None


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
