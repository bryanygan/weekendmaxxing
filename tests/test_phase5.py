"""Phase 5 tests — Cost Agent and Deal Scorer."""

import json
from unittest.mock import patch

import pytest

from agents.cost_agent import CostAgent, DEFAULTS
from orchestrator.deal_scorer import score_deal

CONSTRAINTS = json.loads(open("config/constraints.json").read())


# ── CostAgent tests ─────────────────────────────────────────────────────────


def test_estimate_transit_returns_dict():
    valid_json = json.dumps({
        "airport_transit_one_way": 12, "rideshare_one_way": 30,
        "daily_food_budget_low": 35, "daily_food_budget_mid": 55,
        "avg_activity_cost": 20, "public_transit_day_pass": 8,
    })
    agent = CostAgent()
    with patch("agents.cost_agent.call_llm", return_value=valid_json):
        result = agent.estimate_transit("Boston")
    assert isinstance(result, dict)
    for key in DEFAULTS:
        assert key in result


def test_estimate_transit_uses_defaults_on_bad_json():
    agent = CostAgent()
    with patch("agents.cost_agent.call_llm", return_value="I cannot estimate that"):
        result = agent.estimate_transit("Boston")
    assert result == DEFAULTS


def test_estimate_transit_clamps_high_values():
    extreme = json.dumps({
        "airport_transit_one_way": 9999, "rideshare_one_way": 9999,
        "daily_food_budget_low": 9999, "daily_food_budget_mid": 9999,
        "avg_activity_cost": 9999, "public_transit_day_pass": 9999,
    })
    agent = CostAgent()
    with patch("agents.cost_agent.call_llm", return_value=extreme):
        result = agent.estimate_transit("Boston")
    assert result["airport_transit_one_way"] == 100
    assert result["rideshare_one_way"] == 120
    assert result["daily_food_budget_low"] == 100
    assert result["daily_food_budget_mid"] == 150
    assert result["avg_activity_cost"] == 200
    assert result["public_transit_day_pass"] == 100


def test_compute_full_budget_adds_fields():
    agent = CostAgent()
    deal = {"destination": "Boston", "total_trip_cost": 400}
    transit = {
        "airport_transit_one_way": 10, "rideshare_one_way": 30,
        "daily_food_budget_low": 30, "daily_food_budget_mid": 60,
        "avg_activity_cost": 25, "public_transit_day_pass": 8,
    }
    with patch.object(agent, "estimate_transit", return_value=transit):
        result = agent.compute_full_budget(deal)
    assert "transit_estimates" in result
    assert "estimated_extras" in result
    assert "estimated_total" in result


def test_compute_full_budget_math():
    agent = CostAgent()
    deal = {"destination": "Boston", "price_usd": 200, "total_trip_cost": 450}
    transit = {
        "airport_transit_one_way": 10, "rideshare_one_way": 30,
        "daily_food_budget_low": 30, "daily_food_budget_mid": 60,
        "avg_activity_cost": 25, "public_transit_day_pass": 8,
    }
    with patch.object(agent, "estimate_transit", return_value=transit):
        result = agent.compute_full_budget(deal)
    # extras = 10*2 + 60*2 + 25 = 165
    assert result["estimated_extras"] == 165
    assert result["estimated_total"] == 615


# ── Deal Scorer tests ───────────────────────────────────────────────────────


def _make_scored_deal(**overrides):
    base = {
        "total_trip_cost": 200,
        "layovers": 0,
        "best_stay": {"rating": 5.0},
        "hours_at_destination": 48,
        "return_arrive": "18:00",
        "outbound_depart": "18:00",
        "outbound_date": "2026-04-17",  # Friday
        "price_confidence": "high",
    }
    base.update(overrides)
    return base


def test_score_perfect_deal():
    deal = _make_scored_deal(total_trip_cost=100, layovers=0,
                             best_stay={"rating": 5.0}, hours_at_destination=48,
                             return_arrive="18:00", outbound_depart="18:00",
                             outbound_date="2026-04-17", price_confidence="high")
    score = score_deal(deal, CONSTRAINTS)
    assert score >= 85


def test_score_bad_deal():
    deal = _make_scored_deal(total_trip_cost=700, layovers=2,
                             best_stay={"rating": 2.5}, hours_at_destination=14,
                             return_arrive="21:45", outbound_depart="13:00",
                             outbound_date="2026-04-17", price_confidence="low")
    score = score_deal(deal, CONSTRAINTS)
    assert score <= 35


def test_score_price_component():
    cheap = _make_scored_deal(total_trip_cost=150)
    expensive = _make_scored_deal(total_trip_cost=500)
    assert score_deal(cheap, CONSTRAINTS) > score_deal(expensive, CONSTRAINTS)


def test_score_nonstop_beats_one_stop():
    nonstop = _make_scored_deal(layovers=0)
    one_stop = _make_scored_deal(layovers=1)
    assert score_deal(nonstop, CONSTRAINTS) > score_deal(one_stop, CONSTRAINTS)


def test_score_missing_keys_returns_zero():
    assert score_deal({}, CONSTRAINTS) == 0.0


def test_score_timing_fit_friday_evening():
    deal = _make_scored_deal(outbound_depart="18:00", outbound_date="2026-04-17")
    score = score_deal(deal, CONSTRAINTS)
    # Friday 6pm = ideal timing = 10 points
    deal2 = _make_scored_deal(outbound_depart="14:00", outbound_date="2026-04-17")
    score2 = score_deal(deal2, CONSTRAINTS)
    assert score > score2  # 18:00 should score higher than 14:00


def test_score_timing_fit_saturday_morning():
    deal = _make_scored_deal(outbound_depart="08:00", outbound_date="2026-04-18")
    score = score_deal(deal, CONSTRAINTS)
    deal2 = _make_scored_deal(outbound_depart="11:00", outbound_date="2026-04-18")
    score2 = score_deal(deal2, CONSTRAINTS)
    assert score > score2  # 08:00 Sat should score higher than 11:00 Sat


def test_score_confidence_high_beats_low():
    high = _make_scored_deal(price_confidence="high")
    low = _make_scored_deal(price_confidence="low")
    assert score_deal(high, CONSTRAINTS) > score_deal(low, CONSTRAINTS)


def test_score_absolute_floor_over_budget():
    deal = _make_scored_deal(total_trip_cost=900)
    assert score_deal(deal, CONSTRAINTS) == 0.0


def test_score_absolute_floor_too_short():
    deal = _make_scored_deal(hours_at_destination=10)
    assert score_deal(deal, CONSTRAINTS) == 0.0


def test_score_train_bonus():
    train = _make_scored_deal(transport_type="train")
    flight = _make_scored_deal()
    assert score_deal(train, CONSTRAINTS) > score_deal(flight, CONSTRAINTS)
