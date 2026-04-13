"""Phase 4 tests — Hotel Agent + Booking scraper."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.hotel_agent import HotelAgent
from scrapers.booking import build_url

CONSTRAINTS = json.loads(open("config/constraints.json").read())


# ── build_url tests ─────────────────────────────────────────────────────────


def test_build_url_contains_city():
    url = build_url("Boston", "2026-04-17", "2026-04-19")
    assert "Boston" in url


def test_build_url_contains_dates():
    url = build_url("Boston", "2026-04-17", "2026-04-19")
    assert "2026-04-17" in url
    assert "2026-04-19" in url


# ── scrape_and_parse tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_and_parse_empty_raw():
    agent = HotelAgent(CONSTRAINTS)
    with patch("scrapers.booking.fetch_raw", new_callable=AsyncMock, return_value=""), \
         patch("agents.hotel_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("Boston", "2026-04-17", "2026-04-19", "booking.com")
    assert result == []


@pytest.mark.asyncio
async def test_scrape_and_parse_filters_low_rating():
    agent = HotelAgent(CONSTRAINTS)
    llm_response = json.dumps([{
        "name": "Bad Hotel", "price_per_night": 80, "total_price": 160,
        "rating": 2.0, "review_count": 10, "type": "hotel",
        "neighborhood": None, "source": "booking.com",
    }])
    with patch("scrapers.booking.fetch_raw", new_callable=AsyncMock, return_value="text"), \
         patch("agents.hotel_agent.call_llm", return_value=llm_response), \
         patch("agents.hotel_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("Boston", "2026-04-17", "2026-04-19", "booking.com")
    assert len(result) == 0


@pytest.mark.asyncio
async def test_scrape_and_parse_normalizes_10pt_rating():
    agent = HotelAgent(CONSTRAINTS)
    llm_response = json.dumps([{
        "name": "Good Hotel", "price_per_night": 100, "total_price": 200,
        "rating": 8.4, "review_count": 50, "type": "hotel",
        "neighborhood": "Downtown", "source": "booking.com",
    }])
    with patch("scrapers.booking.fetch_raw", new_callable=AsyncMock, return_value="text"), \
         patch("agents.hotel_agent.call_llm", return_value=llm_response), \
         patch("agents.hotel_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("Boston", "2026-04-17", "2026-04-19", "booking.com")
    assert len(result) == 1
    assert result[0]["rating"] == pytest.approx(4.2)


@pytest.mark.asyncio
async def test_scrape_and_parse_filters_zero_price():
    agent = HotelAgent(CONSTRAINTS)
    llm_response = json.dumps([{
        "name": "Free Hotel", "price_per_night": 0, "total_price": 0,
        "rating": 4.0, "review_count": 10, "type": "hotel",
        "neighborhood": None, "source": "booking.com",
    }])
    with patch("scrapers.booking.fetch_raw", new_callable=AsyncMock, return_value="text"), \
         patch("agents.hotel_agent.call_llm", return_value=llm_response), \
         patch("agents.hotel_agent.limiter.wait", new_callable=AsyncMock):
        result = await agent.scrape_and_parse("Boston", "2026-04-17", "2026-04-19", "booking.com")
    assert len(result) == 0


# ── run() tests ─────────────────────────────────────────────────────────────


def _make_deal(**overrides):
    base = {
        "price_usd": 200, "airline": "AA", "destination": "Boston",
        "iata": "BOS", "outbound_date": "2026-04-17", "return_date": "2026-04-19",
    }
    base.update(overrides)
    return base


def _make_hotel(**overrides):
    base = {
        "name": "Test Hotel", "price_per_night": 125, "total_price": 250,
        "rating": 4.2, "review_count": 100, "type": "hotel",
        "neighborhood": "Downtown", "source": "booking.com",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_run_skips_deal_with_no_stays():
    agent = HotelAgent(CONSTRAINTS)
    with patch.object(agent, "scrape_and_parse", new_callable=AsyncMock, return_value=[]):
        result = await agent.run([_make_deal()])
    assert len(result) == 0


@pytest.mark.asyncio
async def test_run_adds_best_stay():
    agent = HotelAgent(CONSTRAINTS)
    hotel = _make_hotel()
    with patch.object(agent, "scrape_and_parse", new_callable=AsyncMock, return_value=[hotel]):
        result = await agent.run([_make_deal()])
    assert len(result) == 1
    assert result[0]["best_stay"]["name"] == "Test Hotel"


@pytest.mark.asyncio
async def test_run_adds_total_trip_cost():
    agent = HotelAgent(CONSTRAINTS)
    hotel = _make_hotel(total_price=250)
    deal = _make_deal(price_usd=200)
    with patch.object(agent, "scrape_and_parse", new_callable=AsyncMock, return_value=[hotel]):
        result = await agent.run([deal])
    assert result[0]["total_trip_cost"] == 450


@pytest.mark.asyncio
async def test_run_sorts_by_rating_then_price():
    agent = HotelAgent(CONSTRAINTS)
    stays = [
        _make_hotel(name="Cheap Low", rating=3.8, total_price=100),
        _make_hotel(name="Expensive High", rating=4.9, total_price=300),
        _make_hotel(name="Mid Mid", rating=4.5, total_price=200),
    ]
    with patch.object(agent, "scrape_and_parse", new_callable=AsyncMock, return_value=stays):
        result = await agent.run([_make_deal()])
    # Best stay should be highest rated
    assert result[0]["best_stay"]["name"] == "Expensive High"
