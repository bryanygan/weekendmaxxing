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


def _make_deal(**overrides):
    base = {
        "total_trip_cost": 200,
        "layovers": 0,
        "best_stay": {"rating": 5.0},
        "hours_at_destination": 48,
        "return_arrive": "18:00",
    }
    base.update(overrides)
    return base


def test_score_perfect_deal():
    deal = _make_deal(total_trip_cost=100, layovers=0,
                      best_stay={"rating": 5.0}, hours_at_destination=48,
                      return_arrive="18:00")
    score = score_deal(deal, CONSTRAINTS)
    assert score >= 90


def test_score_bad_deal():
    deal = _make_deal(total_trip_cost=580, layovers=2,
                      best_stay={"rating": 2.5}, hours_at_destination=20,
                      return_arrive="21:45")
    score = score_deal(deal, CONSTRAINTS)
    assert score <= 30


def test_score_price_component():
    cheap = _make_deal(total_trip_cost=150)
    expensive = _make_deal(total_trip_cost=500)
    assert score_deal(cheap, CONSTRAINTS) > score_deal(expensive, CONSTRAINTS)


def test_score_nonstop_beats_one_stop():
    nonstop = _make_deal(layovers=0)
    one_stop = _make_deal(layovers=1)
    diff = score_deal(nonstop, CONSTRAINTS) - score_deal(one_stop, CONSTRAINTS)
    assert abs(diff - 10) < 0.1


def test_score_missing_keys_returns_zero():
    assert score_deal({}, CONSTRAINTS) == 0.0
