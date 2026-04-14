"""Quota manager — tracks API call counts to stay within free tier limits."""

import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = "data/deals.db"

DAILY_LIMITS = {
    "amadeus": 66,      # 2,000/month
    "kiwi": 100,        # 3,000/month
    "serpapi": 3,        # 100/month
}

MONTHLY_LIMITS = {
    "amadeus": 2000,
    "kiwi": 3000,
    "serpapi": 100,
}


def init_quota_db() -> None:
    """Create the quota_usage table if it doesn't exist."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quota_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT NOT NULL,
                call_date TEXT NOT NULL,
                call_count INTEGER DEFAULT 0,
                UNIQUE(api_name, call_date)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def record_api_call(api_name: str) -> None:
    """Increment the call counter for an API for today."""
    init_quota_db()
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT INTO quota_usage (api_name, call_date, call_count)
               VALUES (?, ?, 1)
               ON CONFLICT(api_name, call_date)
               DO UPDATE SET call_count = call_count + 1""",
            (api_name, today),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_usage(api_name: str) -> int:
    """Return the number of API calls made today."""
    init_quota_db()
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT call_count FROM quota_usage WHERE api_name = ? AND call_date = ?",
            (api_name, today),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_monthly_usage(api_name: str) -> int:
    """Return total API calls this calendar month."""
    init_quota_db()
    month_prefix = date.today().strftime("%Y-%m")
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(call_count), 0) FROM quota_usage WHERE api_name = ? AND call_date LIKE ?",
            (api_name, f"{month_prefix}%"),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def has_quota(api_name: str) -> bool:
    """Return True if the API has remaining quota for today and this month."""
    daily = get_daily_usage(api_name)
    monthly = get_monthly_usage(api_name)
    daily_limit = DAILY_LIMITS.get(api_name, 0)
    monthly_limit = MONTHLY_LIMITS.get(api_name, 0)
    return daily < daily_limit and monthly < monthly_limit
