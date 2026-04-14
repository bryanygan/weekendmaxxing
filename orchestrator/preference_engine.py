"""Preference engine — tracks user feedback and computes preference boosts for deals."""

import sqlite3
from datetime import datetime
from pathlib import Path

from orchestrator.state_manager import deal_hash

PREFS_DB_PATH = "data/preferences.db"

VALID_REACTIONS = {"thumbs_up", "thumbs_down", "booked"}

REACTION_WEIGHTS = {
    "thumbs_up": 1,
    "thumbs_down": -2,
    "booked": 5,
}


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(PREFS_DB_PATH)


def init_preferences_db() -> None:
    """Create tables if they don't exist. Create data/ dir if needed."""
    Path(PREFS_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_hash TEXT NOT NULL,
                destination TEXT,
                transport_type TEXT,
                airline TEXT,
                price_range TEXT,
                hotel_type TEXT,
                score REAL,
                reaction TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS preference_profile (
                key TEXT PRIMARY KEY,
                weight REAL,
                sample_count INTEGER,
                updated_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _bucket_price(price: float) -> str:
    """Bucket a price into a range string."""
    if price < 100:
        return "0-100"
    elif price < 200:
        return "100-200"
    elif price < 300:
        return "200-300"
    elif price < 500:
        return "300-500"
    else:
        return "500+"


def record_feedback(deal: dict, reaction: str) -> None:
    """Record a thumbs_up, thumbs_down, or booked reaction for a deal."""
    if reaction not in VALID_REACTIONS:
        raise ValueError(f"reaction must be one of {VALID_REACTIONS}, got {reaction!r}")

    init_preferences_db()

    best_stay = deal.get("best_stay") or {}
    price_usd = deal.get("price_usd") or 0
    price_range = _bucket_price(float(price_usd))

    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO feedback
               (deal_hash, destination, transport_type, airline, price_range,
                hotel_type, score, reaction, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                deal_hash(deal),
                deal.get("destination"),
                deal.get("transport_type"),
                deal.get("airline"),
                price_range,
                best_stay.get("type"),
                deal.get("score"),
                reaction,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def rebuild_profile() -> None:
    """Recompute the preference_profile table from all feedback."""
    init_preferences_db()
    conn = _get_conn()
    try:
        # Fetch all feedback
        rows = conn.execute(
            "SELECT destination, transport_type, airline, price_range, reaction FROM feedback"
        ).fetchall()

        # Accumulate weights per key
        key_weights: dict[str, list[float]] = {}

        for destination, transport_type, airline, price_range, reaction in rows:
            weight = REACTION_WEIGHTS.get(reaction, 0)

            keys_to_update = []
            if destination:
                keys_to_update.append(f"dest:{destination}")
            if transport_type:
                keys_to_update.append(f"transport:{transport_type}")
            if airline:
                keys_to_update.append(f"airline:{airline}")
            if price_range:
                keys_to_update.append(f"price:{price_range}")

            for key in keys_to_update:
                if key not in key_weights:
                    key_weights[key] = []
                key_weights[key].append(weight)

        now = datetime.now().isoformat()

        # Delete and reinsert
        conn.execute("DELETE FROM preference_profile")
        for key, weights in key_weights.items():
            conn.execute(
                """INSERT INTO preference_profile (key, weight, sample_count, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (key, sum(weights), len(weights), now),
            )
        conn.commit()
    finally:
        conn.close()


def get_preference_boost(deal: dict) -> float:
    """Look up deal attributes in the profile and return a 0-5 boost."""
    init_preferences_db()
    conn = _get_conn()
    try:
        destination = deal.get("destination")
        transport_type = deal.get("transport_type")
        airline = deal.get("airline")

        keys = []
        if destination:
            keys.append(f"dest:{destination}")
        if transport_type:
            keys.append(f"transport:{transport_type}")
        if airline:
            keys.append(f"airline:{airline}")

        if not keys:
            return 0.0

        placeholders = ",".join("?" * len(keys))
        rows = conn.execute(
            f"SELECT weight FROM preference_profile WHERE key IN ({placeholders})",
            keys,
        ).fetchall()

        if not rows:
            return 0.0

        total_weight = sum(r[0] for r in rows)
        return min(5.0, max(0.0, total_weight / 5.0))
    finally:
        conn.close()


def get_profile_summary() -> dict:
    """Return top destinations, top transport type, and blacklisted airlines."""
    init_preferences_db()
    conn = _get_conn()
    try:
        # Top 5 destinations
        dest_rows = conn.execute(
            """SELECT key, weight FROM preference_profile
               WHERE key LIKE 'dest:%'
               ORDER BY weight DESC LIMIT 5"""
        ).fetchall()
        top_destinations = [r[0].removeprefix("dest:") for r in dest_rows]

        # Top preferred transport type
        transport_rows = conn.execute(
            """SELECT key, weight FROM preference_profile
               WHERE key LIKE 'transport:%'
               ORDER BY weight DESC LIMIT 1"""
        ).fetchall()
        top_transport = transport_rows[0][0].removeprefix("transport:") if transport_rows else None

        # Blacklisted airlines (weight < -3)
        airline_rows = conn.execute(
            """SELECT key, weight FROM preference_profile
               WHERE key LIKE 'airline:%' AND weight < -3"""
        ).fetchall()
        blacklisted_airlines = [r[0].removeprefix("airline:") for r in airline_rows]

        return {
            "top_destinations": top_destinations,
            "top_transport": top_transport,
            "blacklisted_airlines": blacklisted_airlines,
        }
    finally:
        conn.close()


def get_feedback_count() -> int:
    """Return total number of feedback entries."""
    init_preferences_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()
