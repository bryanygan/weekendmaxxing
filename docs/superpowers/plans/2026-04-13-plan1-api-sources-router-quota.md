# Plan 1: API Data Sources + Source Router + Quota Manager

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Amadeus, Kiwi, and Serpapi as primary flight/hotel data sources with automatic fallback to existing scrapers when APIs hit rate limits or return no results.

**Architecture:** Three new API client modules under `apis/`, a quota manager that tracks daily/monthly usage in SQLite, and a source router that tries APIs first then falls back to scrapers. The existing pipeline calls the source router instead of agents directly for raw data fetching.

**Tech Stack:** `requests` (already installed), Amadeus/Kiwi/Serpapi REST APIs (free tiers), SQLite for quota tracking.

---

### Task 1: Quota Manager

**Files:**
- Create: `orchestrator/quota_manager.py`
- Create: `tests/test_quota_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_quota_manager.py
"""Tests for API quota tracking."""

import sqlite3
from pathlib import Path

import pytest

from orchestrator import quota_manager as qm


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_deals.db")
    monkeypatch.setattr(qm, "DB_PATH", db_path)


def test_init_quota_table():
    qm.init_quota_db()
    conn = sqlite3.connect(qm.DB_PATH)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quota_usage'").fetchone()
    conn.close()
    assert row is not None


def test_record_call_increments():
    qm.init_quota_db()
    qm.record_api_call("amadeus")
    qm.record_api_call("amadeus")
    assert qm.get_daily_usage("amadeus") == 2


def test_get_daily_usage_zero_for_new():
    qm.init_quota_db()
    assert qm.get_daily_usage("amadeus") == 0


def test_get_monthly_usage():
    qm.init_quota_db()
    for _ in range(5):
        qm.record_api_call("kiwi")
    assert qm.get_monthly_usage("kiwi") >= 5


def test_has_quota_true_when_under_limit():
    qm.init_quota_db()
    assert qm.has_quota("amadeus") is True


def test_has_quota_false_when_over_limit():
    qm.init_quota_db()
    # Simulate hitting the limit
    for _ in range(67):  # daily limit is 66
        qm.record_api_call("amadeus")
    assert qm.has_quota("amadeus") is False


def test_different_apis_tracked_separately():
    qm.init_quota_db()
    qm.record_api_call("amadeus")
    qm.record_api_call("kiwi")
    assert qm.get_daily_usage("amadeus") == 1
    assert qm.get_daily_usage("kiwi") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_quota_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.quota_manager'`

- [ ] **Step 3: Implement quota manager**

```python
# orchestrator/quota_manager.py
"""Quota manager — tracks API call counts to stay within free tier limits."""

import sqlite3
from datetime import datetime, date
from pathlib import Path

DB_PATH = "data/deals.db"

# Free tier daily limits (monthly / 30, rounded down)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_quota_manager.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/quota_manager.py tests/test_quota_manager.py
git commit -m "feat: add API quota manager with daily/monthly tracking"
```

---

### Task 2: Settings — Add API Key Configuration

**Files:**
- Modify: `config/settings.py`
- Modify: `tests/test_phase0.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_phase0.py — new test at the end of file

def test_api_settings_defaults(monkeypatch):
    monkeypatch.delenv("AMADEUS_API_KEY", raising=False)
    monkeypatch.delenv("AMADEUS_API_SECRET", raising=False)
    monkeypatch.delenv("KIWI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

    import config.settings as settings_module
    importlib.reload(settings_module)

    assert settings_module.AMADEUS_API_KEY == ""
    assert settings_module.AMADEUS_API_SECRET == ""
    assert settings_module.KIWI_API_KEY == ""
    assert settings_module.SERPAPI_API_KEY == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_phase0.py::test_api_settings_defaults -v`
Expected: FAIL — `AttributeError: module 'config.settings' has no attribute 'AMADEUS_API_KEY'`

- [ ] **Step 3: Add API key settings**

Append to `config/settings.py`:

```python
# Flight/Hotel APIs (optional — system falls back to scrapers if not set)
AMADEUS_API_KEY: str = os.getenv("AMADEUS_API_KEY", "")
AMADEUS_API_SECRET: str = os.getenv("AMADEUS_API_SECRET", "")
KIWI_API_KEY: str = os.getenv("KIWI_API_KEY", "")
SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_phase0.py::test_api_settings_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/settings.py tests/test_phase0.py
git commit -m "feat: add API key settings (Amadeus, Kiwi, Serpapi)"
```

---

### Task 3: Amadeus API Client

**Files:**
- Create: `apis/__init__.py`
- Create: `apis/amadeus.py`
- Create: `tests/test_apis.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_apis.py
"""Tests for API clients."""

import json
from unittest.mock import patch, MagicMock

import pytest

from apis.amadeus import AmadeusClient


@pytest.fixture
def client():
    return AmadeusClient(api_key="test_key", api_secret="test_secret")


def test_amadeus_get_token(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "tok123", "expires_in": 1799}

    with patch("apis.amadeus.requests.post", return_value=mock_resp):
        token = client._get_token()
    assert token == "tok123"


def test_amadeus_search_flights(client):
    token_resp = MagicMock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "tok123", "expires_in": 1799}

    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {
        "data": [{
            "price": {"total": "149.00", "currency": "USD"},
            "itineraries": [
                {"segments": [{"departure": {"iataCode": "PHL", "at": "2026-04-17T18:00:00"},
                               "arrival": {"iataCode": "BOS", "at": "2026-04-17T19:25:00"},
                               "carrierCode": "AA", "duration": "PT1H25M"}]},
                {"segments": [{"departure": {"iataCode": "BOS", "at": "2026-04-19T17:00:00"},
                               "arrival": {"iataCode": "PHL", "at": "2026-04-19T18:30:00"},
                               "carrierCode": "AA", "duration": "PT1H30M"}]},
            ],
        }],
    }

    with patch("apis.amadeus.requests.post", return_value=token_resp), \
         patch("apis.amadeus.requests.get", return_value=flight_resp):
        results = client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["price_usd"] == 149.0
    assert results[0]["airline"] == "AA"
    assert results[0]["source"] == "amadeus"
    assert results[0]["layovers"] == 0


def test_amadeus_search_flights_empty_on_error(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("apis.amadeus.requests.post", return_value=mock_resp):
        results = client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert results == []


def test_amadeus_search_hotels(client):
    token_resp = MagicMock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "tok123", "expires_in": 1799}

    hotel_resp = MagicMock()
    hotel_resp.status_code = 200
    hotel_resp.json.return_value = {
        "data": [{
            "hotel": {"name": "Test Hotel", "rating": "4"},
            "offers": [{"price": {"total": "278.00", "currency": "USD"}}],
        }],
    }

    with patch("apis.amadeus.requests.post", return_value=token_resp), \
         patch("apis.amadeus.requests.get", return_value=hotel_resp):
        results = client.search_hotels("BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["name"] == "Test Hotel"
    assert results[0]["total_price"] == 278.0
    assert results[0]["source"] == "amadeus"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_apis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apis'`

- [ ] **Step 3: Implement Amadeus client**

```python
# apis/__init__.py
# apis package
```

```python
# apis/amadeus.py
"""Amadeus Self-Service API client for flights and hotels."""

import logging
from datetime import datetime, timedelta

import requests

from orchestrator.quota_manager import has_quota, record_api_call

logger = logging.getLogger("weekendmaxxing.apis.amadeus")

AUTH_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
FLIGHT_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
HOTEL_URL = "https://test.api.amadeus.com/v2/shopping/hotel-offers"


class AmadeusClient:
    """Client for Amadeus Self-Service API (free test tier)."""

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self._token: str | None = None
        self._token_expires: datetime | None = None

    def _get_token(self) -> str | None:
        """Obtain or reuse an OAuth2 access token."""
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        try:
            resp = requests.post(AUTH_URL, data={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.api_secret,
            }, timeout=15)

            if resp.status_code != 200:
                logger.warning("Amadeus auth failed: %s", resp.status_code)
                return None

            data = resp.json()
            self._token = data["access_token"]
            self._token_expires = datetime.now() + timedelta(seconds=data.get("expires_in", 1700))
            return self._token
        except Exception as exc:
            logger.warning("Amadeus auth error: %s", exc)
            return None

    def search_flights(self, origin: str, destination: str, depart_date: str, return_date: str) -> list[dict]:
        """Search for round-trip flight offers. Returns normalized deal dicts."""
        if not has_quota("amadeus"):
            logger.info("Amadeus quota exhausted, skipping")
            return []

        token = self._get_token()
        if not token:
            return []

        try:
            record_api_call("amadeus")
            resp = requests.get(FLIGHT_URL, headers={"Authorization": f"Bearer {token}"}, params={
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": depart_date,
                "returnDate": return_date,
                "adults": 1,
                "currencyCode": "USD",
                "max": 10,
            }, timeout=30)

            if resp.status_code != 200:
                logger.warning("Amadeus flight search failed: %s %s", resp.status_code, resp.text[:200])
                return []

            return self._parse_flight_offers(resp.json(), destination, depart_date, return_date)
        except Exception as exc:
            logger.warning("Amadeus flight search error: %s", exc)
            return []

    def _parse_flight_offers(self, data: dict, destination: str, depart_date: str, return_date: str) -> list[dict]:
        """Parse Amadeus flight offer response into normalized dicts."""
        results = []
        for offer in data.get("data", []):
            try:
                price = float(offer["price"]["total"])
                itineraries = offer.get("itineraries", [])
                if len(itineraries) < 2:
                    continue

                outbound = itineraries[0]["segments"]
                ret = itineraries[1]["segments"]

                out_depart = outbound[0]["departure"]["at"]
                out_arrive = outbound[-1]["arrival"]["at"]
                ret_depart = ret[0]["departure"]["at"]
                ret_arrive = ret[-1]["arrival"]["at"]

                # Extract HH:MM from ISO datetime
                out_depart_time = out_depart[11:16]
                out_arrive_time = out_arrive[11:16]
                ret_depart_time = ret_depart[11:16]
                ret_arrive_time = ret_arrive[11:16]

                airline = outbound[0].get("carrierCode", "")
                layovers = len(outbound) - 1

                # Duration in minutes from first segment
                duration_str = outbound[0].get("duration", "PT0M")
                duration_mins = 0
                if "H" in duration_str:
                    hours = int(duration_str.split("H")[0].replace("PT", ""))
                    mins_part = duration_str.split("H")[1].replace("M", "") if "M" in duration_str.split("H")[1] else "0"
                    duration_mins = hours * 60 + int(mins_part)
                elif "M" in duration_str:
                    duration_mins = int(duration_str.replace("PT", "").replace("M", ""))

                results.append({
                    "price_usd": price,
                    "airline": airline,
                    "outbound_depart": out_depart_time,
                    "outbound_arrive": out_arrive_time,
                    "return_depart": ret_depart_time,
                    "return_arrive": ret_arrive_time,
                    "layovers": layovers,
                    "duration_mins": duration_mins,
                    "is_nonstop": layovers == 0,
                    "destination": destination,
                    "iata": destination,
                    "outbound_date": depart_date,
                    "return_date": return_date,
                    "source": "amadeus",
                    "booking_link": None,
                    "price_confidence": "high",
                })
            except (KeyError, ValueError, IndexError) as exc:
                logger.debug("Skipping malformed Amadeus offer: %s", exc)
                continue

        return results

    def search_hotels(self, city_code: str, checkin: str, checkout: str) -> list[dict]:
        """Search for hotel offers. Returns normalized hotel dicts."""
        if not has_quota("amadeus"):
            logger.info("Amadeus quota exhausted, skipping hotels")
            return []

        token = self._get_token()
        if not token:
            return []

        try:
            record_api_call("amadeus")
            resp = requests.get(HOTEL_URL, headers={"Authorization": f"Bearer {token}"}, params={
                "cityCode": city_code,
                "checkInDate": checkin,
                "checkOutDate": checkout,
                "adults": 1,
                "currency": "USD",
                "bestRateOnly": "true",
            }, timeout=30)

            if resp.status_code != 200:
                logger.warning("Amadeus hotel search failed: %s", resp.status_code)
                return []

            return self._parse_hotel_offers(resp.json())
        except Exception as exc:
            logger.warning("Amadeus hotel search error: %s", exc)
            return []

    def _parse_hotel_offers(self, data: dict) -> list[dict]:
        """Parse Amadeus hotel response into normalized dicts."""
        results = []
        for entry in data.get("data", []):
            try:
                hotel = entry.get("hotel", {})
                offers = entry.get("offers", [])
                if not offers:
                    continue

                price = float(offers[0]["price"]["total"])
                name = hotel.get("name", "Unknown Hotel")
                rating = float(hotel.get("rating", 0))

                results.append({
                    "name": name,
                    "price_per_night": round(price / 2, 2),
                    "total_price": price,
                    "rating": rating,
                    "review_count": 0,
                    "type": "hotel",
                    "neighborhood": None,
                    "source": "amadeus",
                })
            except (KeyError, ValueError) as exc:
                logger.debug("Skipping malformed Amadeus hotel: %s", exc)
                continue

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_apis.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apis/__init__.py apis/amadeus.py tests/test_apis.py
git commit -m "feat: add Amadeus API client for flights and hotels"
```

---

### Task 4: Kiwi API Client

**Files:**
- Create: `apis/kiwi.py`
- Modify: `tests/test_apis.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_apis.py`:

```python
from apis.kiwi import KiwiClient


@pytest.fixture
def kiwi_client():
    return KiwiClient(api_key="test_key")


def test_kiwi_search_flights(kiwi_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{
            "price": 159,
            "airlines": ["B6"],
            "route": [
                {"cityFrom": "Philadelphia", "flyFrom": "PHL",
                 "cityTo": "Boston", "flyTo": "BOS",
                 "local_departure": "2026-04-17T18:00:00.000Z",
                 "local_arrival": "2026-04-17T19:20:00.000Z"},
                {"cityFrom": "Boston", "flyFrom": "BOS",
                 "cityTo": "Philadelphia", "flyTo": "PHL",
                 "local_departure": "2026-04-19T17:00:00.000Z",
                 "local_arrival": "2026-04-19T18:30:00.000Z"},
            ],
            "deep_link": "https://kiwi.com/booking/abc123",
            "duration": {"departure": 4800, "return": 5400},
        }],
    }

    with patch("apis.kiwi.requests.get", return_value=mock_resp):
        results = kiwi_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["price_usd"] == 159
    assert results[0]["source"] == "kiwi"
    assert results[0]["booking_link"] == "https://kiwi.com/booking/abc123"


def test_kiwi_search_flights_empty_on_error(kiwi_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("apis.kiwi.requests.get", return_value=mock_resp):
        results = kiwi_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_apis.py::test_kiwi_search_flights -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apis.kiwi'`

- [ ] **Step 3: Implement Kiwi client**

```python
# apis/kiwi.py
"""Kiwi.com Tequila API client for flights."""

import logging

import requests

from orchestrator.quota_manager import has_quota, record_api_call

logger = logging.getLogger("weekendmaxxing.apis.kiwi")

SEARCH_URL = "https://api.tequila.kiwi.com/v2/search"


class KiwiClient:
    """Client for Kiwi.com Tequila API (free tier)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_flights(self, origin: str, destination: str, depart_date: str, return_date: str) -> list[dict]:
        """Search round-trip flights. Returns normalized deal dicts."""
        if not has_quota("kiwi"):
            logger.info("Kiwi quota exhausted, skipping")
            return []

        # Kiwi uses DD/MM/YYYY format
        dep_parts = depart_date.split("-")
        ret_parts = return_date.split("-")
        dep_fmt = f"{dep_parts[2]}/{dep_parts[1]}/{dep_parts[0]}"
        ret_fmt = f"{ret_parts[2]}/{ret_parts[1]}/{ret_parts[0]}"

        try:
            record_api_call("kiwi")
            resp = requests.get(SEARCH_URL, headers={"apikey": self.api_key}, params={
                "fly_from": origin,
                "fly_to": destination,
                "date_from": dep_fmt,
                "date_to": dep_fmt,
                "return_from": ret_fmt,
                "return_to": ret_fmt,
                "adults": 1,
                "curr": "USD",
                "limit": 10,
                "sort": "price",
                "flight_type": "round",
            }, timeout=30)

            if resp.status_code != 200:
                logger.warning("Kiwi search failed: %s %s", resp.status_code, resp.text[:200])
                return []

            return self._parse_results(resp.json(), destination, depart_date, return_date)
        except Exception as exc:
            logger.warning("Kiwi search error: %s", exc)
            return []

    def _parse_results(self, data: dict, destination: str, depart_date: str, return_date: str) -> list[dict]:
        """Parse Kiwi response into normalized dicts."""
        results = []
        for item in data.get("data", []):
            try:
                price = float(item["price"])
                route = item.get("route", [])
                if len(route) < 2:
                    continue

                # Split route into outbound and return segments
                outbound_segs = [r for r in route if r["flyFrom"] == "PHL" or route.index(r) == 0]
                return_segs = [r for r in route if r not in outbound_segs]

                out_seg = route[0]
                ret_seg = route[-1]

                out_depart_time = out_seg["local_departure"][11:16]
                out_arrive_time = outbound_segs[-1]["local_arrival"][11:16] if outbound_segs else out_seg["local_arrival"][11:16]
                ret_depart_time = return_segs[0]["local_departure"][11:16] if return_segs else ret_seg["local_departure"][11:16]
                ret_arrive_time = ret_seg["local_arrival"][11:16]

                airlines = item.get("airlines", [])
                airline = airlines[0] if airlines else ""

                # Count outbound layovers (segments where destination != final dest)
                outbound_count = sum(1 for r in route if r.get("return") == 0) if any("return" in r for r in route) else max(0, len(outbound_segs) - 1)

                booking_link = item.get("deep_link", "")

                results.append({
                    "price_usd": price,
                    "airline": airline,
                    "outbound_depart": out_depart_time,
                    "outbound_arrive": out_arrive_time,
                    "return_depart": ret_depart_time,
                    "return_arrive": ret_arrive_time,
                    "layovers": outbound_count,
                    "duration_mins": item.get("duration", {}).get("departure", 0) // 60,
                    "is_nonstop": outbound_count == 0,
                    "destination": destination,
                    "iata": destination,
                    "outbound_date": depart_date,
                    "return_date": return_date,
                    "source": "kiwi",
                    "booking_link": booking_link,
                    "price_confidence": "high",
                })
            except (KeyError, ValueError, IndexError) as exc:
                logger.debug("Skipping malformed Kiwi result: %s", exc)
                continue

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_apis.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apis/kiwi.py tests/test_apis.py
git commit -m "feat: add Kiwi.com Tequila API client for flights"
```

---

### Task 5: Serpapi Client

**Files:**
- Create: `apis/serpapi_flights.py`
- Modify: `tests/test_apis.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_apis.py`:

```python
from apis.serpapi_flights import SerpApiClient


@pytest.fixture
def serpapi_client():
    return SerpApiClient(api_key="test_key")


def test_serpapi_search_flights(serpapi_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "best_flights": [{
            "price": 189,
            "flights": [
                {"departure_airport": {"id": "PHL", "time": "2026-04-17 18:00"},
                 "arrival_airport": {"id": "BOS", "time": "2026-04-17 19:25"},
                 "airline": "American Airlines", "duration": 85},
            ],
            "layovers": [],
            "total_duration": 85,
        }],
        "other_flights": [],
    }

    with patch("apis.serpapi_flights.requests.get", return_value=mock_resp):
        results = serpapi_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["price_usd"] == 189
    assert results[0]["source"] == "serpapi"


def test_serpapi_empty_on_no_key():
    client = SerpApiClient(api_key="")
    results = client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_apis.py::test_serpapi_search_flights -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apis.serpapi_flights'`

- [ ] **Step 3: Implement Serpapi client**

```python
# apis/serpapi_flights.py
"""Serpapi Google Flights API client."""

import logging

import requests

from orchestrator.quota_manager import has_quota, record_api_call

logger = logging.getLogger("weekendmaxxing.apis.serpapi")

SEARCH_URL = "https://serpapi.com/search"


class SerpApiClient:
    """Client for Serpapi Google Flights (free tier: 100/month)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_flights(self, origin: str, destination: str, depart_date: str, return_date: str) -> list[dict]:
        """Search round-trip flights via Serpapi. Returns normalized deal dicts."""
        if not self.api_key:
            return []

        if not has_quota("serpapi"):
            logger.info("Serpapi quota exhausted, skipping")
            return []

        try:
            record_api_call("serpapi")
            resp = requests.get(SEARCH_URL, params={
                "engine": "google_flights",
                "departure_id": origin,
                "arrival_id": destination,
                "outbound_date": depart_date,
                "return_date": return_date,
                "currency": "USD",
                "type": "1",  # round trip
                "api_key": self.api_key,
            }, timeout=30)

            if resp.status_code != 200:
                logger.warning("Serpapi search failed: %s", resp.status_code)
                return []

            return self._parse_results(resp.json(), destination, depart_date, return_date)
        except Exception as exc:
            logger.warning("Serpapi search error: %s", exc)
            return []

    def _parse_results(self, data: dict, destination: str, depart_date: str, return_date: str) -> list[dict]:
        """Parse Serpapi Google Flights response into normalized dicts."""
        results = []
        all_flights = data.get("best_flights", []) + data.get("other_flights", [])

        for item in all_flights:
            try:
                price = float(item["price"])
                flights = item.get("flights", [])
                if not flights:
                    continue

                out_seg = flights[0]
                out_depart_time = out_seg["departure_airport"]["time"][11:16]
                out_arrive_time = flights[-1]["arrival_airport"]["time"][11:16]
                airline = out_seg.get("airline", "")
                layover_count = len(item.get("layovers", []))
                duration = item.get("total_duration", out_seg.get("duration", 0))

                results.append({
                    "price_usd": price,
                    "airline": airline,
                    "outbound_depart": out_depart_time,
                    "outbound_arrive": out_arrive_time,
                    "return_depart": "",
                    "return_arrive": "",
                    "layovers": layover_count,
                    "duration_mins": duration,
                    "is_nonstop": layover_count == 0,
                    "destination": destination,
                    "iata": destination,
                    "outbound_date": depart_date,
                    "return_date": return_date,
                    "source": "serpapi",
                    "booking_link": None,
                    "price_confidence": "high",
                })
            except (KeyError, ValueError, IndexError) as exc:
                logger.debug("Skipping malformed Serpapi result: %s", exc)
                continue

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_apis.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apis/serpapi_flights.py tests/test_apis.py
git commit -m "feat: add Serpapi Google Flights API client"
```

---

### Task 6: Source Router

**Files:**
- Create: `orchestrator/source_router.py`
- Create: `tests/test_source_router.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_source_router.py
"""Tests for the source router — API-first with scraper fallback."""

import json
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from orchestrator.source_router import fetch_flights, fetch_hotels


@pytest.fixture(autouse=True)
def _mock_quota(monkeypatch):
    """Always allow quota for tests."""
    import orchestrator.quota_manager as qm
    monkeypatch.setattr(qm, "DB_PATH", ":memory:")


def test_fetch_flights_uses_api_first():
    api_results = [{"price_usd": 149, "source": "amadeus", "airline": "AA"}]

    with patch("orchestrator.source_router._get_amadeus_client") as mock_amadeus, \
         patch("orchestrator.source_router._get_kiwi_client") as mock_kiwi:
        mock_amadeus.return_value.search_flights.return_value = api_results
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["source"] == "amadeus"
    mock_kiwi.return_value.search_flights.assert_not_called()


def test_fetch_flights_falls_back_to_kiwi():
    kiwi_results = [{"price_usd": 159, "source": "kiwi", "airline": "B6"}]

    with patch("orchestrator.source_router._get_amadeus_client") as mock_amadeus, \
         patch("orchestrator.source_router._get_kiwi_client") as mock_kiwi, \
         patch("orchestrator.source_router._get_serpapi_client") as mock_serpapi:
        mock_amadeus.return_value.search_flights.return_value = []
        mock_kiwi.return_value.search_flights.return_value = kiwi_results
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "kiwi"


def test_fetch_flights_falls_back_to_scraper():
    with patch("orchestrator.source_router._get_amadeus_client") as mock_a, \
         patch("orchestrator.source_router._get_kiwi_client") as mock_k, \
         patch("orchestrator.source_router._get_serpapi_client") as mock_s, \
         patch("orchestrator.source_router._scraper_fetch_flights") as mock_scraper:
        mock_a.return_value.search_flights.return_value = []
        mock_k.return_value.search_flights.return_value = []
        mock_s.return_value.search_flights.return_value = []
        mock_scraper.return_value = [{"price_usd": 199, "source": "google_flights"}]
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "google_flights"


def test_fetch_flights_skips_api_when_no_key():
    with patch("orchestrator.source_router._get_amadeus_client", return_value=None), \
         patch("orchestrator.source_router._get_kiwi_client", return_value=None), \
         patch("orchestrator.source_router._get_serpapi_client", return_value=None), \
         patch("orchestrator.source_router._scraper_fetch_flights") as mock_scraper:
        mock_scraper.return_value = [{"price_usd": 199, "source": "kayak"}]
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1


def test_fetch_hotels_api_first():
    api_results = [{"name": "Hotel", "total_price": 278, "source": "amadeus"}]

    with patch("orchestrator.source_router._get_amadeus_client") as mock_amadeus:
        mock_amadeus.return_value.search_hotels.return_value = api_results
        results = fetch_hotels("BOS", "Boston", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "amadeus"


def test_fetch_hotels_falls_back_to_scraper():
    with patch("orchestrator.source_router._get_amadeus_client") as mock_a, \
         patch("orchestrator.source_router._scraper_fetch_hotels") as mock_scraper:
        mock_a.return_value.search_hotels.return_value = []
        mock_scraper.return_value = [{"name": "Hostel", "source": "booking.com"}]
        results = fetch_hotels("BOS", "Boston", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "booking.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_source_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.source_router'`

- [ ] **Step 3: Implement source router**

```python
# orchestrator/source_router.py
"""Source router — tries APIs first, falls back to scrapers."""

import asyncio
import logging

from config import settings
from utils.json_extractor import extract_json
from utils.llm import call_llm

logger = logging.getLogger("weekendmaxxing.source_router")


def _get_amadeus_client():
    """Return an AmadeusClient if credentials are configured, else None."""
    if settings.AMADEUS_API_KEY and settings.AMADEUS_API_SECRET:
        from apis.amadeus import AmadeusClient
        return AmadeusClient(settings.AMADEUS_API_KEY, settings.AMADEUS_API_SECRET)
    return None


def _get_kiwi_client():
    """Return a KiwiClient if the API key is configured, else None."""
    if settings.KIWI_API_KEY:
        from apis.kiwi import KiwiClient
        return KiwiClient(settings.KIWI_API_KEY)
    return None


def _get_serpapi_client():
    """Return a SerpApiClient if the API key is configured, else None."""
    if settings.SERPAPI_API_KEY:
        from apis.serpapi_flights import SerpApiClient
        return SerpApiClient(settings.SERPAPI_API_KEY)
    return None


def _scraper_fetch_flights(origin: str, dest_iata: str, depart_date: str, return_date: str) -> list[dict]:
    """Fall back to existing Playwright scrapers + LLM extraction."""
    import scrapers.google_flights as gf
    import scrapers.kayak as kayak

    all_flights = []
    for source_name, module in [("google_flights", gf), ("kayak", kayak)]:
        try:
            raw = asyncio.run(module.fetch_raw(origin, dest_iata, depart_date, return_date))
            if not raw:
                continue

            system = (
                "You are a flight data extraction agent. Extract all visible "
                "flight options from the given search results page text. Return ONLY a valid "
                "JSON array of flight objects. No markdown, no preamble, no explanation."
            )
            user = (
                f"Extract every flight option. Destination IATA: {dest_iata}\n"
                f"Outbound date: {depart_date}, Return date: {return_date}\n"
                f"Return JSON with: price_usd (number), airline (string), "
                f"outbound_depart (HH:MM 24h), outbound_arrive (HH:MM 24h), "
                f"return_depart (HH:MM 24h), return_arrive (HH:MM 24h), "
                f"layovers (number), duration_mins (number), is_nonstop (bool), "
                f'destination, iata, outbound_date, return_date\n'
                f"IMPORTANT: All times in 24-hour HH:MM format.\n\n"
                f"Page text:\n{raw[:3500]}"
            )
            response = call_llm(system, user)
            parsed = extract_json(response)
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                for f in parsed:
                    if isinstance(f, dict):
                        f["source"] = source_name
                        f["price_confidence"] = "low"
                        all_flights.append(f)
        except Exception as exc:
            logger.warning("Scraper fallback failed for %s: %s", source_name, exc)

    return all_flights


def _scraper_fetch_hotels(city: str, checkin: str, checkout: str) -> list[dict]:
    """Fall back to existing Playwright scrapers + LLM extraction for hotels."""
    import scrapers.booking as booking

    try:
        raw = asyncio.run(booking.fetch_raw(city, checkin, checkout))
        if not raw:
            return []

        system = (
            "You are a hotel listing extraction agent. Extract all visible "
            "accommodation listings from the page text. Return ONLY a valid JSON "
            "array. No markdown, no preamble."
        )
        user = (
            f"Extract every accommodation listing. City: {city}\n"
            f"Return JSON with: name (string), price_per_night (number), "
            f"total_price (number), rating (number, 5-point scale, just the number), "
            f"review_count (number), type (string), neighborhood (string or null), "
            f'source ("booking.com")\n\n'
            f"Page text:\n{raw[:3500]}"
        )
        response = call_llm(system, user)
        parsed = extract_json(response)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            for h in parsed:
                if isinstance(h, dict):
                    h["price_confidence"] = "low"
            return [h for h in parsed if isinstance(h, dict)]
    except Exception as exc:
        logger.warning("Hotel scraper fallback failed: %s", exc)

    return []


def fetch_flights(origin: str, dest_iata: str, depart_date: str, return_date: str) -> list[dict]:
    """Fetch flights using APIs first, falling back to scrapers.

    Returns all results from the first source that returns data.
    """
    # Try APIs in priority order
    for name, get_client in [("amadeus", _get_amadeus_client), ("kiwi", _get_kiwi_client), ("serpapi", _get_serpapi_client)]:
        client = get_client()
        if client is None:
            continue
        try:
            results = client.search_flights(origin, dest_iata, depart_date, return_date)
            if results:
                logger.info("Got %d flights from %s for %s", len(results), name, dest_iata)
                return results
        except Exception as exc:
            logger.warning("%s flight search failed: %s", name, exc)

    # Fall back to scrapers
    logger.info("No API results for %s, falling back to scrapers", dest_iata)
    return _scraper_fetch_flights(origin, dest_iata, depart_date, return_date)


def fetch_hotels(city_code: str, city_name: str, checkin: str, checkout: str) -> list[dict]:
    """Fetch hotels using APIs first, falling back to scrapers."""
    amadeus = _get_amadeus_client()
    if amadeus:
        try:
            results = amadeus.search_hotels(city_code, checkin, checkout)
            if results:
                logger.info("Got %d hotels from amadeus for %s", len(results), city_name)
                return results
        except Exception as exc:
            logger.warning("Amadeus hotel search failed: %s", exc)

    # Fall back to scrapers
    logger.info("No API hotel results for %s, falling back to scrapers", city_name)
    return _scraper_fetch_hotels(city_name, checkin, checkout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_source_router.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/source_router.py tests/test_source_router.py
git commit -m "feat: add source router with API-first, scraper fallback"
```

---

### Task 7: Full Regression + Integration Test

**Files:**
- Modify: none (just run existing tests)

- [ ] **Step 1: Run full regression to make sure nothing broke**

Run: `pytest tests/ -v -m "not slow and not llm" -k "not test_call_llm_returns_string"`
Expected: All existing 122+ tests still pass, plus the new tests from this plan.

- [ ] **Step 2: Verify import chain works**

```bash
python -c "
from orchestrator.source_router import fetch_flights, fetch_hotels
from orchestrator.quota_manager import has_quota, get_daily_usage
from apis.amadeus import AmadeusClient
from apis.kiwi import KiwiClient
from apis.serpapi_flights import SerpApiClient
print('All imports OK')
print(f'Amadeus quota available: {has_quota(\"amadeus\")}')
print(f'Kiwi quota available: {has_quota(\"kiwi\")}')
"
```

Expected: "All imports OK" with quota = True for all APIs.

- [ ] **Step 3: Commit any fixes and tag the milestone**

```bash
git add -A
git commit -m "milestone: Plan 1 complete — API sources + router + quota manager"
git push
```
