# Plan 2: Data Reconciliation Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When multiple sources return data for the same route, merge them into a single result with a price confidence score (high/medium/low) so the user knows which prices are trustworthy.

**Architecture:** A new `orchestrator/reconciler.py` module that groups flights by route+airline+time, computes price confidence from agreement across sources, and picks the best price. The source router gets a new `fetch_flights_multi` function that collects from all available sources instead of stopping at the first.

**Tech Stack:** Pure Python, no new dependencies. Uses `statistics.median` for price aggregation.

---

### Task 1: Add multi-source fetch to source router

**Files:**
- Modify: `orchestrator/source_router.py`
- Modify: `tests/test_source_router.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_source_router.py`:

```python
from orchestrator.source_router import fetch_flights_multi

def test_fetch_flights_multi_collects_all_sources():
    amadeus_results = [{"price_usd": 149, "source": "amadeus", "airline": "AA",
                        "outbound_depart": "18:00", "outbound_arrive": "19:25"}]
    kiwi_results = [{"price_usd": 155, "source": "kiwi", "airline": "AA",
                     "outbound_depart": "18:00", "outbound_arrive": "19:20"}]

    with patch("orchestrator.source_router._get_amadeus_client") as mock_a, \
         patch("orchestrator.source_router._get_kiwi_client") as mock_k, \
         patch("orchestrator.source_router._get_serpapi_client", return_value=None):
        mock_a.return_value.search_flights.return_value = amadeus_results
        mock_k.return_value.search_flights.return_value = kiwi_results
        results = fetch_flights_multi("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) == 2
    sources = {r["source"] for r in results}
    assert "amadeus" in sources
    assert "kiwi" in sources
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_router.py::test_fetch_flights_multi_collects_all_sources -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_flights_multi'`

- [ ] **Step 3: Implement fetch_flights_multi**

Add to `orchestrator/source_router.py`:

```python
def fetch_flights_multi(
    origin: str,
    dest_iata: str,
    depart_date: str,
    return_date: str,
) -> list[dict]:
    """Fetch flights from ALL available sources (for reconciliation).

    Unlike fetch_flights which stops at the first successful source,
    this collects results from every source that returns data.
    """
    all_results: list[dict] = []

    for name, get_client in [("amadeus", _get_amadeus_client),
                              ("kiwi", _get_kiwi_client),
                              ("serpapi", _get_serpapi_client)]:
        client = get_client()
        if client is None:
            continue
        try:
            results = client.search_flights(origin, dest_iata, depart_date, return_date)
            all_results.extend(results)
        except Exception as exc:
            logger.warning("[source_router] %s multi-fetch failed: %s", name, exc)

    # If no API results, fall back to scrapers
    if not all_results:
        all_results = _scraper_fetch_flights(origin, dest_iata, depart_date, return_date)

    return all_results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_source_router.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/source_router.py tests/test_source_router.py
git commit -m "feat: add fetch_flights_multi for cross-source collection"
```

---

### Task 2: Reconciler — flight matching and price confidence

**Files:**
- Create: `orchestrator/reconciler.py`
- Create: `tests/test_reconciler.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reconciler.py
"""Tests for the data reconciliation layer."""

import pytest

from orchestrator.reconciler import reconcile_flights, reconcile_hotels


# ── Flight reconciliation ───────────────────────────────────────────────────


def _flight(price, source, airline="AA", depart="18:00", arrive="19:25", **kw):
    base = {
        "price_usd": price, "source": source, "airline": airline,
        "outbound_depart": depart, "outbound_arrive": arrive,
        "return_depart": "17:00", "return_arrive": "18:30",
        "layovers": 0, "duration_mins": 85, "is_nonstop": True,
        "destination": "Boston", "iata": "BOS",
        "outbound_date": "2026-04-17", "return_date": "2026-04-19",
        "booking_link": None, "price_confidence": "high",
    }
    base.update(kw)
    return base


def test_reconcile_groups_same_flight():
    """Two sources, same airline+time -> merged into 1 result."""
    flights = [
        _flight(149, "amadeus"),
        _flight(155, "kiwi"),
    ]
    result = reconcile_flights(flights)
    assert len(result) == 1


def test_reconcile_keeps_different_flights():
    """Different airlines -> separate results."""
    flights = [
        _flight(149, "amadeus", airline="AA"),
        _flight(199, "kiwi", airline="DL"),
    ]
    result = reconcile_flights(flights)
    assert len(result) == 2


def test_reconcile_high_confidence_when_3_agree():
    """3 sources within 10% -> high confidence, median price."""
    flights = [
        _flight(149, "amadeus"),
        _flight(155, "kiwi"),
        _flight(152, "serpapi"),
    ]
    result = reconcile_flights(flights)
    assert len(result) == 1
    assert result[0]["price_confidence"] == "high"
    assert result[0]["price_usd"] == 152  # median


def test_reconcile_medium_confidence_when_2_agree():
    """2 sources within 15% -> medium confidence, lower price."""
    flights = [
        _flight(149, "amadeus"),
        _flight(160, "kiwi"),
    ]
    result = reconcile_flights(flights)
    assert result[0]["price_confidence"] == "medium"
    assert result[0]["price_usd"] == 149  # lower of the two


def test_reconcile_low_confidence_single_source():
    """Single source -> low confidence."""
    flights = [_flight(149, "amadeus")]
    result = reconcile_flights(flights)
    assert result[0]["price_confidence"] == "low"


def test_reconcile_low_confidence_when_disagree():
    """2 sources disagree by >20% -> low confidence."""
    flights = [
        _flight(100, "amadeus"),
        _flight(200, "kiwi"),
    ]
    result = reconcile_flights(flights)
    assert result[0]["price_confidence"] == "low"


def test_reconcile_prefers_api_over_scraper():
    """When API and scraper conflict, use API price."""
    flights = [
        _flight(149, "amadeus", price_confidence="high"),
        _flight(999, "google_flights", price_confidence="low"),
    ]
    result = reconcile_flights(flights)
    assert result[0]["price_usd"] == 149


def test_reconcile_keeps_booking_link():
    """Booking link from Kiwi should survive reconciliation."""
    flights = [
        _flight(149, "amadeus"),
        _flight(155, "kiwi", booking_link="https://kiwi.com/book/123"),
    ]
    result = reconcile_flights(flights)
    assert result[0]["booking_link"] == "https://kiwi.com/book/123"


def test_reconcile_collects_price_sources():
    """Result should list all contributing sources."""
    flights = [
        _flight(149, "amadeus"),
        _flight(155, "kiwi"),
    ]
    result = reconcile_flights(flights)
    assert set(result[0]["price_sources"]) == {"amadeus", "kiwi"}


def test_reconcile_time_tolerance():
    """Flights within 30 min depart time should still group."""
    flights = [
        _flight(149, "amadeus", depart="18:00"),
        _flight(155, "kiwi", depart="18:20"),
    ]
    result = reconcile_flights(flights)
    assert len(result) == 1


def test_reconcile_time_too_far_apart():
    """Flights >30 min apart should NOT group."""
    flights = [
        _flight(149, "amadeus", depart="18:00"),
        _flight(155, "kiwi", depart="20:00"),
    ]
    result = reconcile_flights(flights)
    assert len(result) == 2


def test_reconcile_empty_input():
    assert reconcile_flights([]) == []


# ── Hotel reconciliation ────────────────────────────────────────────────────


def _hotel(name, price, source, rating=4.2, **kw):
    base = {
        "name": name, "total_price": price, "price_per_night": price / 2,
        "rating": rating, "review_count": 100, "type": "hotel",
        "neighborhood": "Downtown", "source": source,
    }
    base.update(kw)
    return base


def test_reconcile_hotels_groups_same_name():
    hotels = [
        _hotel("The Godfrey", 338, "amadeus"),
        _hotel("The Godfrey Hotel", 350, "booking.com"),
    ]
    result = reconcile_hotels(hotels)
    assert len(result) == 1


def test_reconcile_hotels_keeps_different():
    hotels = [
        _hotel("The Godfrey", 338, "amadeus"),
        _hotel("HI Boston Hostel", 118, "booking.com"),
    ]
    result = reconcile_hotels(hotels)
    assert len(result) == 2


def test_reconcile_hotels_prefers_api_price():
    hotels = [
        _hotel("The Godfrey", 338, "amadeus"),
        _hotel("The Godfrey Hotel", 999, "booking.com"),
    ]
    result = reconcile_hotels(hotels)
    assert result[0]["total_price"] == 338
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reconciler.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement reconciler**

```python
# orchestrator/reconciler.py
"""Data reconciliation — merges results from multiple sources with confidence scoring."""

import logging
from statistics import median

logger = logging.getLogger("weekendmaxxing.reconciler")

# Sources in priority order (API > scraper)
API_SOURCES = {"amadeus", "kiwi", "serpapi"}
SCRAPER_SOURCES = {"google_flights", "kayak", "skyscanner", "booking.com", "airbnb"}


def _time_to_minutes(t: str) -> int:
    """Convert HH:MM to minutes since midnight."""
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return -1


def _flights_match(a: dict, b: dict) -> bool:
    """Return True if two flights are likely the same offering."""
    # Same airline (or close match)
    if a.get("airline", "").upper() != b.get("airline", "").upper():
        return False

    # Departure times within 30 minutes
    t_a = _time_to_minutes(a.get("outbound_depart", ""))
    t_b = _time_to_minutes(b.get("outbound_depart", ""))
    if t_a < 0 or t_b < 0:
        return False
    if abs(t_a - t_b) > 30:
        return False

    return True


def _compute_flight_confidence(group: list[dict]) -> tuple[float, str, list[str]]:
    """Compute price, confidence level, and source list for a group of matched flights.

    Returns (price, confidence, sources).
    """
    sources = [f["source"] for f in group]
    prices = [f["price_usd"] for f in group if isinstance(f.get("price_usd"), (int, float))]

    if not prices:
        return 0, "low", sources

    # Separate API vs scraper prices
    api_prices = [f["price_usd"] for f in group if f.get("source") in API_SOURCES and isinstance(f.get("price_usd"), (int, float))]
    scraper_prices = [f["price_usd"] for f in group if f.get("source") in SCRAPER_SOURCES and isinstance(f.get("price_usd"), (int, float))]

    # If we have API prices and scraper prices that conflict, trust API
    if api_prices and scraper_prices:
        prices = api_prices

    if len(prices) == 1:
        return prices[0], "low", sources

    # Check agreement
    med = median(prices)
    spread = (max(prices) - min(prices)) / med if med > 0 else 1.0

    if len(prices) >= 3 and spread <= 0.10:
        return med, "high", sources
    elif len(prices) >= 2 and spread <= 0.15:
        return min(prices), "medium", sources
    elif spread > 0.20:
        # Big disagreement — trust API if available, else use lower price
        if api_prices:
            return min(api_prices), "low", sources
        return min(prices), "low", sources
    else:
        return min(prices), "medium", sources


def reconcile_flights(flights: list[dict]) -> list[dict]:
    """Group matching flights and reconcile prices with confidence scoring.

    Returns deduplicated list with price_confidence, price_sources, and booking_link fields.
    """
    if not flights:
        return []

    groups: list[list[dict]] = []

    for flight in flights:
        matched = False
        for group in groups:
            if _flights_match(group[0], flight):
                group.append(flight)
                matched = True
                break
        if not matched:
            groups.append([flight])

    results = []
    for group in groups:
        # Use the highest-priority source as the base (API > scraper)
        group.sort(key=lambda f: 0 if f.get("source") in API_SOURCES else 1)
        base = dict(group[0])

        price, confidence, sources = _compute_flight_confidence(group)
        base["price_usd"] = price
        base["price_confidence"] = confidence
        base["price_sources"] = sources

        # Preserve booking link from any source that has one
        for f in group:
            if f.get("booking_link"):
                base["booking_link"] = f["booking_link"]
                break

        results.append(base)

    return results


def _hotels_match(a: dict, b: dict) -> bool:
    """Return True if two hotels are likely the same property."""
    name_a = a.get("name", "").lower().strip()
    name_b = b.get("name", "").lower().strip()

    # Exact match or one contains the other
    if name_a == name_b:
        return True
    if name_a in name_b or name_b in name_a:
        return True

    # Check if significant words overlap (>60%)
    words_a = set(name_a.split())
    words_b = set(name_b.split())
    # Remove common filler words
    filler = {"the", "hotel", "inn", "a", "an", "&", "and"}
    words_a -= filler
    words_b -= filler
    if words_a and words_b:
        overlap = len(words_a & words_b) / max(len(words_a), len(words_b))
        if overlap >= 0.6:
            return True

    return False


def reconcile_hotels(hotels: list[dict]) -> list[dict]:
    """Group matching hotels and prefer API-sourced data."""
    if not hotels:
        return []

    groups: list[list[dict]] = []

    for hotel in hotels:
        matched = False
        for group in groups:
            if _hotels_match(group[0], hotel):
                group.append(hotel)
                matched = True
                break
        if not matched:
            groups.append([hotel])

    results = []
    for group in groups:
        # Prefer API source
        group.sort(key=lambda h: 0 if h.get("source") in API_SOURCES else 1)
        base = dict(group[0])

        sources = [h["source"] for h in group]
        base["price_sources"] = sources
        base["price_confidence"] = "high" if any(s in API_SOURCES for s in sources) else "low"

        results.append(base)

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reconciler.py -v`
Expected: All 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/reconciler.py tests/test_reconciler.py
git commit -m "feat: add data reconciler with price confidence scoring"
```

---

### Task 3: Full regression

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -q -m "not slow and not llm" -k "not test_call_llm_returns_string"`
Expected: All 150+ tests pass

- [ ] **Step 2: Commit milestone**

```bash
git add -A
git commit -m "milestone: Plan 2 complete — data reconciliation with confidence scoring"
git push
```
