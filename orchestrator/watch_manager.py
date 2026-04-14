"""Watch list manager for the Weekend Deal Hunter.

Manages a watch list of destinations (max 5) stored in the same
preferences DB used by the preference engine.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

PREFS_DB_PATH = "data/preferences.db"

MAX_WATCHES = 5


def _get_conn() -> sqlite3.Connection:
    """Return a connection to the preferences DB, creating dirs if needed."""
    db_path = Path(PREFS_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_watches_db() -> None:
    """Create watches table if it does not already exist."""
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destination TEXT NOT NULL,
                specific_date TEXT,
                added_at TEXT NOT NULL,
                last_checked_at TEXT,
                last_price REAL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def add_watch(destination: str, specific_date: str | None = None) -> bool:
    """Add a destination to the watch list.

    Returns False if already at the 5-watch limit or destination is already
    being watched. Returns True on success.
    """
    conn = _get_conn()
    try:
        # Check current count
        count_row = conn.execute("SELECT COUNT(*) FROM watches").fetchone()
        if count_row[0] >= MAX_WATCHES:
            return False

        # Check for duplicate
        existing = conn.execute(
            "SELECT id FROM watches WHERE destination = ?", (destination,)
        ).fetchone()
        if existing is not None:
            return False

        conn.execute(
            "INSERT INTO watches (destination, specific_date, added_at) VALUES (?, ?, ?)",
            (destination, specific_date, datetime.now().isoformat()),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def remove_watch(destination: str) -> bool:
    """Remove a watch by destination name.

    Returns True if removed, False if not found.
    """
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM watches WHERE destination = ?", (destination,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_watches() -> list[dict]:
    """Return all active watches as a list of dicts."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, destination, specific_date, added_at, last_checked_at, last_price "
            "FROM watches ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_watch_count() -> int:
    """Return the number of active watches."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) FROM watches").fetchone()
        return row[0]
    finally:
        conn.close()


def update_watch_price(destination: str, price: float) -> None:
    """Update last_checked_at and last_price for a watched destination."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE watches SET last_checked_at = ?, last_price = ? WHERE destination = ?",
            (datetime.now().isoformat(), price, destination),
        )
        conn.commit()
    finally:
        conn.close()


def is_watched(destination: str) -> bool:
    """Return True if this destination is on the watch list."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM watches WHERE destination = ?", (destination,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()
