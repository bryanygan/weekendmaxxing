"""Phase 6 tests — Recommendation Agent and State Manager."""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.recommendation_agent import RecommendationAgent
from orchestrator import state_manager


# ── RecommendationAgent tests ───────────────────────────────────────────────


def _make_deal():
    return {
        "destination": "Boston", "iata": "BOS",
        "outbound_date": "2026-04-17", "return_date": "2026-04-19",
        "outbound_arrive": "19:30", "return_depart": "18:00",
        "hours_at_destination": 46.5, "price_usd": 150,
    }


def test_generate_adds_recommendations():
    agent = RecommendationAgent()
    deal = _make_deal()
    with patch("agents.recommendation_agent.call_llm", return_value="RECS TEXT"):
        result = agent.generate(deal)
    assert result["recommendations"] == "RECS TEXT"
    assert result["recommendations_city"] == "Boston"


def test_generate_batch_handles_exception():
    agent = RecommendationAgent()
    deals = [_make_deal(), _make_deal()]
    deals[1]["destination"] = "Miami"

    call_count = {"n": 0}
    def mock_llm(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("LLM down")
        return "Good recs"

    with patch("agents.recommendation_agent.call_llm", side_effect=mock_llm):
        result = agent.generate_batch(deals)

    assert len(result) == 2
    assert result[0]["recommendations"] == "Good recs"
    assert result[1]["recommendations"] == "Could not generate recommendations."


# ── State Manager tests ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    """Point DB_PATH to a temp directory for every test."""
    db_path = str(tmp_path / "test_deals.db")
    monkeypatch.setattr(state_manager, "DB_PATH", db_path)


def _make_db_deal(**overrides):
    base = {
        "destination": "Boston", "outbound_date": "2026-04-17",
        "airline": "AA", "price_usd": 150, "best_stay": {"total_price": 200},
        "estimated_total": 500, "score": 72.5,
    }
    base.update(overrides)
    return base


def test_deal_hash_deterministic():
    deal = _make_db_deal()
    assert state_manager.deal_hash(deal) == state_manager.deal_hash(deal)


def test_deal_hash_different_for_different_deals():
    d1 = _make_db_deal(destination="Boston")
    d2 = _make_db_deal(destination="Miami")
    assert state_manager.deal_hash(d1) != state_manager.deal_hash(d2)


def test_is_duplicate_false_for_new():
    deal = _make_db_deal()
    assert state_manager.is_duplicate(deal) is False


def test_is_duplicate_true_after_save():
    deal = _make_db_deal()
    state_manager.save_deal(deal)
    assert state_manager.is_duplicate(deal) is True


def test_save_deal_persists():
    deal = _make_db_deal()
    state_manager.save_deal(deal)
    recent = state_manager.get_recent_deals()
    assert len(recent) == 1
    assert recent[0]["destination"] == "Boston"


def test_get_recent_deals_order():
    import time
    for i, city in enumerate(["Alpha", "Bravo", "Charlie"]):
        state_manager.save_deal(_make_db_deal(destination=city, airline=f"X{i}"))
        time.sleep(0.05)  # ensure distinct seen_at timestamps
    recent = state_manager.get_recent_deals()
    assert recent[0]["destination"] == "Charlie"
    assert recent[2]["destination"] == "Alpha"


def test_log_run_persists():
    state_manager.init_db()
    state_manager.log_run("2026-04-13T10:00:00", "2026-04-13T10:05:00", 5, 3)
    conn = sqlite3.connect(state_manager.DB_PATH)
    row = conn.execute("SELECT * FROM runs").fetchone()
    conn.close()
    assert row is not None
    assert row[3] == 5  # deals_found
    assert row[4] == 3  # deals_notified


def test_init_db_idempotent():
    state_manager.init_db()
    state_manager.init_db()
    state_manager.init_db()
    # No error means success
