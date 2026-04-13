"""Tests for train scrapers and TrainAgent."""

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from agents.train_agent import TrainAgent
from scrapers.amtrak import build_url as amtrak_build_url, get_station_code
from scrapers.booking import build_url as booking_build_url
from scrapers.septa import get_septa_info
from orchestrator.deal_scorer import score_deal

CONSTRAINTS = json.loads(open("config/constraints.json").read())


def _next_friday():
    today = date.today()
    days = (4 - today.weekday()) % 7
    if days == 0 and today.weekday() == 4:
        return today
    return today + timedelta(days=days or 7)


FRIDAY = _next_friday()
SUNDAY = FRIDAY + timedelta(days=2)


# ── Amtrak scraper tests ────────────────────────────────────────────────────


def test_amtrak_station_codes():
    assert get_station_code("Washington DC") == "WAS"
    assert get_station_code("New York") == "NYP"
    assert get_station_code("Boston") == "BOS"
    assert get_station_code("Philadelphia") == "PHL"
    assert get_station_code("Baltimore") == "BAL"


def test_amtrak_no_station_for_unknown_city():
    assert get_station_code("Timbuktu") is None
    assert get_station_code("Los Angeles") is None


def test_amtrak_build_url_contains_stations():
    url = amtrak_build_url("PHL", "WAS", "2026-04-17", "2026-04-19")
    assert "PHL" in url
    assert "WAS" in url
    assert "amtrak.com" in url


def test_amtrak_build_url_contains_dates():
    url = amtrak_build_url("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert "04%2F17%2F2026" in url
    assert "04%2F19%2F2026" in url


# ── SEPTA scraper tests ─────────────────────────────────────────────────────


def test_septa_info_for_trenton():
    info = get_septa_info("Trenton")
    assert info is not None
    assert info["peak_fare"] > 0
    assert info["duration_min"] > 0


def test_septa_info_for_wilmington():
    info = get_septa_info("Wilmington")
    assert info is not None
    assert info["off_peak_fare"] > 0


def test_septa_no_info_for_unserved_city():
    assert get_septa_info("Miami") is None
    assert get_septa_info("Chicago") is None


# ── TrainAgent tests ─────────────────────────────────────────────────────────


def _make_train(**overrides):
    base = {
        "price_usd": 80,
        "operator": "Amtrak",
        "airline": "Amtrak",
        "outbound_depart": "17:00",
        "outbound_arrive": "18:45",
        "return_depart": "18:00",
        "return_arrive": "19:45",
        "stops": 0,
        "layovers": 0,
        "duration_mins": 105,
        "is_nonstop": True,
        "destination": "Washington DC",
        "iata": "DCA",
        "outbound_date": FRIDAY.isoformat(),
        "return_date": SUNDAY.isoformat(),
        "transport_type": "train",
        "source": "amtrak",
    }
    base.update(overrides)
    return base


def test_get_weekend_pairs_count():
    agent = TrainAgent(CONSTRAINTS)
    pairs = agent.get_weekend_pairs(num_weekends=3)
    assert len(pairs) == 6


def test_passes_constraints_valid_train():
    agent = TrainAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_train()) is True


def test_passes_constraints_over_budget_train():
    agent = TrainAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_train(price_usd=999)) is False


def test_passes_constraints_friday_too_early():
    agent = TrainAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_train(outbound_depart="14:00")) is False


def test_passes_constraints_friday_4pm_ok_for_train():
    """Trains can leave at 16:00 on Friday (earlier than flights at 17:00)."""
    agent = TrainAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_train(outbound_depart="16:00")) is True


def test_passes_constraints_saturday_ok():
    agent = TrainAgent(CONSTRAINTS)
    saturday = FRIDAY + timedelta(days=1)
    train = _make_train(
        outbound_depart="08:00",
        outbound_arrive="09:45",  # Arrive early enough for 24+ hrs at dest
        outbound_date=saturday.isoformat(),
        return_date=SUNDAY.isoformat(),
    )
    assert agent.passes_constraints(train) is True


def test_passes_constraints_late_return_train():
    """Trains can return as late as 23:00 (vs 22:00 for flights)."""
    agent = TrainAgent(CONSTRAINTS)
    assert agent.passes_constraints(_make_train(return_arrive="22:30")) is True
    assert agent.passes_constraints(_make_train(return_arrive="23:30")) is False


def test_calc_hours_at_destination():
    agent = TrainAgent(CONSTRAINTS)
    train = _make_train(
        outbound_arrive="18:45",
        outbound_date=FRIDAY.isoformat(),
        return_depart="18:00",
        return_date=SUNDAY.isoformat(),
    )
    hours = agent.calc_hours_at_destination(train)
    assert abs(hours - 47.25) < 0.1


@pytest.mark.asyncio
async def test_scrape_and_parse_empty_raw():
    agent = TrainAgent(CONSTRAINTS)
    with patch("scrapers.amtrak.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("scrapers.septa.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("agents.train_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("Philadelphia", "Miami", FRIDAY.isoformat(), SUNDAY.isoformat())
    assert result == []


@pytest.mark.asyncio
async def test_scrape_and_parse_returns_trains():
    agent = TrainAgent(CONSTRAINTS)
    llm_response = json.dumps([{
        "price_usd": 80, "operator": "Amtrak",
        "outbound_depart": "17:00", "outbound_arrive": "18:45",
        "return_depart": "18:00", "return_arrive": "19:45",
        "stops": 0, "duration_mins": 105,
        "destination": "Washington DC",
        "outbound_date": FRIDAY.isoformat(), "return_date": SUNDAY.isoformat(),
    }])
    with patch("scrapers.amtrak.fetch_raw", new_callable=AsyncMock, return_value="Amtrak results"), \
         patch("scrapers.septa.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("agents.train_agent.call_llm", return_value=llm_response), \
         patch("agents.train_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("Philadelphia", "Washington DC", FRIDAY.isoformat(), SUNDAY.isoformat())
    assert len(result) >= 1
    assert result[0]["transport_type"] == "train"
    assert result[0]["price_usd"] == 80


# ── Scorer tests for trains ─────────────────────────────────────────────────


def test_score_train_gets_convenience_bonus():
    train_deal = {
        "total_trip_cost": 200, "layovers": 0,
        "best_stay": {"rating": 4.5}, "hours_at_destination": 48,
        "return_arrive": "19:00", "transport_type": "train",
    }
    flight_deal = {
        "total_trip_cost": 200, "layovers": 0,
        "best_stay": {"rating": 4.5}, "hours_at_destination": 48,
        "return_arrive": "19:00",
    }
    train_score = score_deal(train_deal, CONSTRAINTS)
    flight_score = score_deal(flight_deal, CONSTRAINTS)
    # Train should score higher due to convenience bonus
    assert train_score > flight_score


def test_score_train_one_stop_less_penalized():
    train_deal = {
        "total_trip_cost": 200, "layovers": 1,
        "best_stay": {"rating": 4.0}, "hours_at_destination": 36,
        "return_arrive": "20:00", "transport_type": "train",
    }
    flight_deal = {
        "total_trip_cost": 200, "layovers": 1,
        "best_stay": {"rating": 4.0}, "hours_at_destination": 36,
        "return_arrive": "20:00",
    }
    train_score = score_deal(train_deal, CONSTRAINTS)
    flight_score = score_deal(flight_deal, CONSTRAINTS)
    assert train_score > flight_score
