"""Data Reconciliation Layer for the Weekend Deal Hunter project.

Merges flight and hotel data from multiple sources (APIs and scrapers),
resolving duplicate listings and assigning price confidence scores.
"""

import statistics
from datetime import datetime, timedelta
from typing import Any

API_SOURCES = {"amadeus", "kiwi", "serpapi"}
SCRAPER_SOURCES = {"google_flights", "kayak", "skyscanner", "booking.com", "airbnb"}

_HOTEL_FILLER = {"the", "hotel", "inn", "hostel", "suites", "suite", "a", "an"}


def _parse_time(t: str) -> datetime:
    """Parse HH:MM time string into a datetime for comparison."""
    return datetime.strptime(t, "%H:%M")


def _times_within(t1: str, t2: str, minutes: int = 30) -> bool:
    """Return True if two HH:MM strings are within `minutes` of each other."""
    dt1 = _parse_time(t1)
    dt2 = _parse_time(t2)
    diff = abs((dt1 - dt2).total_seconds()) / 60
    return diff <= minutes


def _flights_match(f1: dict, f2: dict) -> bool:
    """Two flights match if same airline (case-insensitive) and depart within 30 min."""
    same_airline = f1["airline"].upper() == f2["airline"].upper()
    close_depart = _times_within(f1["outbound_depart"], f2["outbound_depart"], 30)
    return same_airline and close_depart


def _prices_agree(prices: list[float], threshold_pct: float) -> bool:
    """Return True if all prices are within threshold_pct of the mean."""
    if len(prices) < 2:
        return False
    avg = statistics.mean(prices)
    return all(abs(p - avg) / avg <= threshold_pct / 100 for p in prices)


def _compute_price_confidence(group: list[dict]) -> tuple[str, float]:
    """
    Determine price confidence and canonical price for a group of matched flights.

    Returns (confidence, price_usd).
    """
    api_flights = [f for f in group if f["source"] in API_SOURCES]
    scraper_flights = [f for f in group if f["source"] in SCRAPER_SOURCES]

    # When both API and scraper sources exist, use only API prices for computation
    if api_flights and scraper_flights:
        working_flights = api_flights
    else:
        working_flights = group

    prices = [f["price_usd"] for f in working_flights]

    if len(working_flights) == 1 and len(group) == 1:
        # Single source overall
        return "low", prices[0]

    if len(working_flights) >= 3 and _prices_agree(prices, 10):
        return "high", statistics.median(prices)

    if len(working_flights) >= 2 and _prices_agree(prices, 15):
        return "medium", min(prices)

    # Sources disagree — check for >20% spread
    if len(prices) >= 2:
        lo, hi = min(prices), max(prices)
        if lo > 0 and (hi - lo) / lo > 0.20:
            # Use API price if available
            if api_flights:
                return "low", min(f["price_usd"] for f in api_flights)
            return "low", min(prices)

    # Fall-through: single working source after filtering
    if api_flights:
        return "low", min(f["price_usd"] for f in api_flights)
    return "low", min(prices)


def _best_source_flight(group: list[dict]) -> dict:
    """Return the flight from the highest-priority source in the group."""
    api_flights = [f for f in group if f["source"] in API_SOURCES]
    return api_flights[0] if api_flights else group[0]


def reconcile_flights(flights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge flights from multiple sources into deduplicated records with
    confidence-scored prices.
    """
    if not flights:
        return []

    # Group matching flights using union-find via a simple list-of-groups approach
    groups: list[list[dict]] = []
    assigned = [False] * len(flights)

    for i, flight in enumerate(flights):
        if assigned[i]:
            continue
        group = [flight]
        assigned[i] = True
        for j in range(i + 1, len(flights)):
            if not assigned[j] and _flights_match(flight, flights[j]):
                group.append(flights[j])
                assigned[j] = True
        groups.append(group)

    results = []
    for group in groups:
        confidence, price = _compute_price_confidence(group)

        # Base record from highest-priority source
        base = dict(_best_source_flight(group))

        # Collect first non-None booking link across the group
        booking_link = None
        for f in group:
            if f.get("booking_link") is not None:
                booking_link = f["booking_link"]
                break

        base["price_usd"] = price
        base["price_confidence"] = confidence
        base["price_sources"] = [f["source"] for f in group]
        base["booking_link"] = booking_link

        results.append(base)

    return results


# ---------------------------------------------------------------------------
# Hotel reconciliation
# ---------------------------------------------------------------------------

def _normalize_hotel_name(name: str) -> set[str]:
    """Return meaningful words from a hotel name (lowercase, filler removed)."""
    words = name.lower().split()
    return {w for w in words if w not in _HOTEL_FILLER}


def _hotels_match(h1: dict, h2: dict) -> bool:
    """Two hotels match if one name's meaningful words are a subset of the other's."""
    words1 = _normalize_hotel_name(h1["name"])
    words2 = _normalize_hotel_name(h2["name"])
    if not words1 or not words2:
        return False
    return words1.issubset(words2) or words2.issubset(words1)


def reconcile_hotels(hotels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge hotels from multiple sources, preferring API-sourced data for
    price and rating.
    """
    if not hotels:
        return []

    groups: list[list[dict]] = []
    assigned = [False] * len(hotels)

    for i, hotel in enumerate(hotels):
        if assigned[i]:
            continue
        group = [hotel]
        assigned[i] = True
        for j in range(i + 1, len(hotels)):
            if not assigned[j] and _hotels_match(hotel, hotels[j]):
                group.append(hotels[j])
                assigned[j] = True
        groups.append(group)

    results = []
    for group in groups:
        api_hotels = [h for h in group if h["source"] in API_SOURCES]
        primary = api_hotels[0] if api_hotels else group[0]

        result = dict(primary)
        results.append(result)

    return results
