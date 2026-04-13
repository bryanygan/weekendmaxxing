"""Phase 3 tests — Flight Agent."""

import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from agents.flight_agent import FlightAgent

# ── shared fixtures ─────────────────────────────────────────────────────────

CONSTRAINTS = json.loads(
    open("config/constraints.json").read()
)


def _next_friday():
    today = date.today()
    days = (4 - today.weekday()) % 7
    if days == 0 and today.weekday() == 4:
        return today
    return today + timedelta(days=days or 7)


def _make_flight(**overrides) -> dict:
    """Build a valid flight dict, with optional overrides."""
    friday = _next_friday()
    sunday = friday + timedelta(days=2)
    base = {
        "price_usd": 150,
        "airline": "AA",
        "outbound_depart": "18:00",
        "outbound_arrive": "20:00",
        "return_depart": "18:00",
        "return_arrive": "19:30",
        "layovers": 0,
        "duration_mins": 120,
        "is_nonstop": True,
        "destination": "Boston",
        "iata": "BOS",
        "outbound_date": friday.isoformat(),
        "return_date": sunday.isoformat(),
    }
    base.update(overrides)
    return base


# ── get_weekend_pairs ───────────────────────────────────────────────────────


def test_get_weekend_pairs_count():
    agent = FlightAgent(CONSTRAINTS)
    pairs = agent.get_weekend_pairs(num_weekends=6)
    assert len(pairs) == 12


def test_get_weekend_pairs_no_past_dates():
    agent = FlightAgent(CONSTRAINTS)
    today = date.today()
    for outbound, _ in agent.get_weekend_pairs():
        assert date.fromisoformat(outbound) >= today


def test_get_weekend_pairs_sunday_returns():
    agent = FlightAgent(CONSTRAINTS)
    for _, ret in agent.get_weekend_pairs():
        d = date.fromisoformat(ret)
        assert d.weekday() == 6, f"{ret} is not a Sunday"


# ── passes_constraints ──────────────────────────────────────────────────────


def test_passes_constraints_valid():
    agent = FlightAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_flight()) is True


def test_passes_constraints_over_budget():
    agent = FlightAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_flight(price_usd=999)) is False


def test_passes_constraints_bad_timing_friday():
    agent = FlightAgent(CONSTRAINTS)
    friday = _next_friday()
    flight = _make_flight(outbound_depart="14:00", outbound_date=friday.isoformat())
    assert agent.passes_constraints(flight) is False


def test_passes_constraints_bad_timing_saturday():
    agent = FlightAgent(CONSTRAINTS)
    saturday = _next_friday() + timedelta(days=1)
    sunday = saturday + timedelta(days=1)
    flight = _make_flight(
        outbound_depart="11:00",
        outbound_date=saturday.isoformat(),
        return_date=sunday.isoformat(),
    )
    assert agent.passes_constraints(flight) is False


def test_passes_constraints_late_return():
    agent = FlightAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_flight(return_arrive="23:30")) is False


def test_passes_constraints_missing_field():
    agent = FlightAgent(CONSTRAINTS)
    flight = _make_flight()
    del flight["price_usd"]
    assert agent.passes_constraints(flight) is False


# ── calc_hours_at_destination ───────────────────────────────────────────────


def test_calc_hours_normal():
    agent = FlightAgent(CONSTRAINTS)
    friday = _next_friday()
    sunday = friday + timedelta(days=2)
    flight = _make_flight(
        outbound_arrive="20:00",
        outbound_date=friday.isoformat(),
        return_depart="18:00",
        return_date=sunday.isoformat(),
    )
    hours = agent.calc_hours_at_destination(flight)
    assert abs(hours - 46.0) < 0.1


def test_calc_hours_saturday_arrive():
    agent = FlightAgent(CONSTRAINTS)
    saturday = _next_friday() + timedelta(days=1)
    sunday = saturday + timedelta(days=1)
    flight = _make_flight(
        outbound_arrive="09:30",
        outbound_date=saturday.isoformat(),
        return_depart="19:00",
        return_date=sunday.isoformat(),
    )
    hours = agent.calc_hours_at_destination(flight)
    assert abs(hours - 33.5) < 0.1


# ── scrape_and_parse ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_and_parse_empty_raw():
    agent = FlightAgent(CONSTRAINTS)
    with patch("scrapers.google_flights.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("scrapers.kayak.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("scrapers.skyscanner.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("agents.flight_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("PHL", "Boston", "BOS", "2026-04-17", "2026-04-19")
    assert result == []


@pytest.mark.asyncio
async def test_scrape_and_parse_llm_called():
    agent = FlightAgent(CONSTRAINTS)
    llm_response = json.dumps([{
        "price_usd": 150, "airline": "AA",
        "outbound_depart": "18:00", "outbound_arrive": "19:30",
        "return_depart": "18:00", "return_arrive": "19:30",
        "layovers": 0, "duration_mins": 90, "is_nonstop": True,
    }])
    with patch("scrapers.google_flights.fetch_raw", new_callable=AsyncMock, return_value="some text"), \
         patch("scrapers.kayak.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("scrapers.skyscanner.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("agents.flight_agent.call_llm", return_value=llm_response), \
         patch("agents.flight_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("PHL", "Boston", "BOS", "2026-04-17", "2026-04-19")

    assert len(result) >= 1
    assert result[0]["price_usd"] == 150


# ── deduplication in run() ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deduplication():
    agent = FlightAgent(CONSTRAINTS)
    friday = _next_friday()
    sunday = friday + timedelta(days=2)

    dup_flight = _make_flight(
        outbound_date=friday.isoformat(),
        return_date=sunday.isoformat(),
    )

    async def fake_scrape_and_parse(*args, **kwargs):
        return [dup_flight.copy()]

    destinations = [{"city": "Boston", "iata": "BOS"}]

    with patch.object(agent, "scrape_and_parse", side_effect=fake_scrape_and_parse), \
         patch.object(agent, "get_weekend_pairs", return_value=[
             (friday.isoformat(), sunday.isoformat()),
             (friday.isoformat(), sunday.isoformat()),
         ]):
        result = await agent.run(destinations)

    assert len(result) == 1
