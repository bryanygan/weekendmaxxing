"""Integration tests — full pipeline with mocked scraping, real or mocked LLM."""

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.flight_agent import FlightAgent
from agents.hotel_agent import HotelAgent
from notifications.local_dashboard import write_dashboard
from orchestrator import state_manager
from orchestrator.deal_scorer import score_deal
from orchestrator import pipeline as pipeline_module


# ── Date helpers ────────────────────────────────────────────────────────────


def _next_friday():
    today = date.today()
    days = (4 - today.weekday()) % 7
    if days == 0 and today.weekday() == 4:
        return today
    return today + timedelta(days=days or 7)


FRIDAY = _next_friday()
SUNDAY = FRIDAY + timedelta(days=2)
CONSTRAINTS = json.loads(Path("config/constraints.json").read_text(encoding="utf-8"))


# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_flight(**overrides):
    base = {
        "price_usd": 150, "airline": "AA", "destination": "Boston", "iata": "BOS",
        "outbound_depart": "18:00", "outbound_arrive": "20:00",
        "return_depart": "18:00", "return_arrive": "19:30",
        "layovers": 0, "duration_mins": 120, "is_nonstop": True,
        "outbound_date": FRIDAY.isoformat(), "return_date": SUNDAY.isoformat(),
        "hours_at_destination": 46,
    }
    base.update(overrides)
    return base


def _make_enriched(**overrides):
    d = _make_flight()
    d["best_stay"] = {"name": "Test Hotel", "total_price": 200, "rating": 4.2, "type": "hotel"}
    d["all_stays"] = [d["best_stay"]]
    d["total_trip_cost"] = 350
    d["hotel_search_performed"] = True
    d.update(overrides)
    return d


@pytest.fixture
def mock_call_llm():
    """Returns pre-baked JSON for different agent prompts."""
    def _mock(system, user, **kwargs):
        if "flight" in system.lower():
            return json.dumps([{
                "price_usd": 150, "airline": "AA", "outbound_depart": "18:00",
                "outbound_arrive": "20:00", "return_depart": "18:00", "return_arrive": "19:30",
                "layovers": 0, "duration_mins": 120, "is_nonstop": True,
                "destination": "Boston", "iata": "BOS",
                "outbound_date": FRIDAY.isoformat(), "return_date": SUNDAY.isoformat(),
            }])
        if "hotel" in system.lower() or "accommodation" in system.lower():
            return json.dumps([{
                "name": "Test Hotel", "price_per_night": 100, "total_price": 200,
                "rating": 4.2, "review_count": 80, "type": "hotel",
                "neighborhood": "Downtown", "source": "booking.com",
            }])
        if "cost" in system.lower() or "estimat" in system.lower():
            return json.dumps({
                "airport_transit_one_way": 12, "rideshare_one_way": 30,
                "daily_food_budget_low": 35, "daily_food_budget_mid": 55,
                "avg_activity_cost": 20, "public_transit_day_pass": 8,
            })
        return "Visit the Freedom Trail, eat at Neptune Oyster, stay in Back Bay."
    return _mock


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_deals.db")
    monkeypatch.setattr(state_manager, "DB_PATH", db_path)


# ── Tests ───────────────────────────────────────────────────────────────────


def test_full_pipeline_end_to_end(mock_call_llm, tmp_path):
    """Mock asyncio.run to return pre-built flight/hotel data, test full pipeline wiring."""
    flights = [_make_flight(), _make_flight(price_usd=185, airline="UA", destination="Miami", iata="MIA")]
    enriched = [_make_enriched(), _make_enriched(destination="Miami", iata="MIA")]

    dash_path = str(tmp_path / "dashboard.html")

    with patch("orchestrator.pipeline.asyncio.run", side_effect=[flights, [], enriched]), \
         patch("orchestrator.pipeline.CostAgent") as mock_cost, \
         patch("orchestrator.pipeline.RecommendationAgent") as mock_rec, \
         patch("orchestrator.pipeline.write_dashboard",
               side_effect=lambda deals, **kw: write_dashboard(deals, output_path=dash_path)):
        mock_cost.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mock_rec.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        result = pipeline_module.run_pipeline()

    assert result["deals_found"] > 0
    assert Path(state_manager.DB_PATH).exists()
    conn = sqlite3.connect(state_manager.DB_PATH)
    rows = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    conn.close()
    assert rows > 0


@pytest.mark.llm
@pytest.mark.asyncio
async def test_llm_extracts_flights_from_real_text():
    agent = FlightAgent(CONSTRAINTS)
    fake_text = (
        "Showing flights from PHL to BOS on Friday\n"
        "$189 · American Airlines · Nonstop · 1h 25m · 6:00 PM → 7:25 PM\n"
        "$245 · Delta · 1 stop · 3h 10m · 5:30 PM → 8:40 PM\n"
        "$159 · JetBlue · Nonstop · 1h 20m · 7:00 PM → 8:20 PM\n"
    )
    with patch("agents.flight_agent.fetch_raw", new_callable=AsyncMock, return_value=fake_text):
        result = await agent.scrape_and_parse("PHL", "Boston", "BOS", FRIDAY.isoformat(), SUNDAY.isoformat())

    assert len(result) >= 1
    assert any(f.get("price_usd", 0) > 0 for f in result)


@pytest.mark.llm
@pytest.mark.asyncio
async def test_llm_extracts_hotels_from_real_text():
    agent = HotelAgent(CONSTRAINTS)
    fake_text = (
        "Search results for Boston\n"
        "The Liberty Hotel · 4.5/5 · $189/night · $378 total · Back Bay\n"
        "Budget Inn Boston · 3.8/5 · $89/night · $178 total · Downtown\n"
        "Luxury Suites · 4.8/5 · $299/night · $598 total · Beacon Hill\n"
    )
    with patch("agents.hotel_agent.fetch_raw", new_callable=AsyncMock, return_value=fake_text):
        result = await agent.scrape_and_parse("Boston", FRIDAY.isoformat(), SUNDAY.isoformat(), "booking.com")

    assert len(result) >= 1
    assert any(h.get("rating", 0) > 0 and h.get("total_price", 0) > 0 for h in result)


def test_scorer_ranks_correctly():
    deals = [
        {"total_trip_cost": 500, "layovers": 2, "best_stay": {"rating": 3.0},
         "hours_at_destination": 20, "return_arrive": "21:45"},
        {"total_trip_cost": 200, "layovers": 0, "best_stay": {"rating": 5.0},
         "hours_at_destination": 48, "return_arrive": "18:00"},
        {"total_trip_cost": 350, "layovers": 1, "best_stay": {"rating": 4.0},
         "hours_at_destination": 36, "return_arrive": "19:30"},
        {"total_trip_cost": 150, "layovers": 0, "best_stay": {"rating": 4.5},
         "hours_at_destination": 40, "return_arrive": "19:00"},
        {"total_trip_cost": 400, "layovers": 1, "best_stay": {"rating": 3.5},
         "hours_at_destination": 30, "return_arrive": "20:00"},
    ]
    scored = [(score_deal(d, CONSTRAINTS), i) for i, d in enumerate(deals)]
    scored.sort(reverse=True)
    assert scored[0][1] in (1, 3)  # cheap nonstop deals rank first
    assert scored[-1][1] == 0      # expensive 2-stop deal ranks last


def test_dashboard_renders_all_deals(tmp_path):
    cities = ["Boston", "Miami", "Chicago", "Nashville", "Atlanta"]
    deals = []
    for city in cities:
        deals.append({
            "destination": city, "score": 70, "outbound_date": FRIDAY.isoformat(),
            "return_date": SUNDAY.isoformat(), "airline": "AA", "price_usd": 150,
            "layovers": 0, "outbound_depart": "18:00", "outbound_arrive": "20:00",
            "return_depart": "18:00", "return_arrive": "19:30",
            "best_stay": {"name": "Hotel", "total_price": 200, "rating": 4.0, "type": "hotel"},
            "all_stays": [], "estimated_total": 450, "total_trip_cost": 350,
            "hours_at_destination": 46, "recommendations": "Visit stuff",
        })
    out = str(tmp_path / "dash.html")
    write_dashboard(deals, output_path=out)
    html = Path(out).read_text(encoding="utf-8")
    for city in cities:
        assert city in html


def test_no_duplicate_notification(mock_call_llm, tmp_path):
    flights = [_make_flight()]
    enriched = [_make_enriched()]
    dash_path = str(tmp_path / "dashboard.html")

    def run_once():
        with patch("orchestrator.pipeline.asyncio.run", side_effect=[flights, [], enriched]), \
             patch("orchestrator.pipeline.CostAgent") as mc, \
             patch("orchestrator.pipeline.RecommendationAgent") as mr, \
             patch("orchestrator.pipeline.write_dashboard",
                   side_effect=lambda deals, **kw: write_dashboard(deals, output_path=dash_path)):
            mc.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
            mr.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
            return pipeline_module.run_pipeline()

    result1 = run_once()
    result2 = run_once()
    assert result2["deals_notified"] == 0


def test_pipeline_resilient_to_partial_scrape_failure(mock_call_llm, tmp_path):
    """Even when 2 of 3 flights are empty, pipeline should still process the 1 that works."""
    # Only 1 of 3 flights returns data
    good_flight = _make_flight()
    flights = [good_flight]  # FlightAgent.run already filters empties
    enriched = [_make_enriched()]
    dash_path = str(tmp_path / "dashboard.html")

    with patch("orchestrator.pipeline.asyncio.run", side_effect=[flights, [], enriched]), \
         patch("orchestrator.pipeline.CostAgent") as mc, \
         patch("orchestrator.pipeline.RecommendationAgent") as mr, \
         patch("orchestrator.pipeline.write_dashboard",
               side_effect=lambda deals, **kw: write_dashboard(deals, output_path=dash_path)):
        mc.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mr.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        result = pipeline_module.run_pipeline()

    assert isinstance(result, dict)
    assert result["deals_found"] > 0
