"""Phase 8 tests — Master Pipeline and Scheduler."""

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator import pipeline as pipeline_module


# ── helpers ─────────────────────────────────────────────────────────────────


def _mock_flight():
    return {
        "price_usd": 150, "airline": "AA", "destination": "Boston", "iata": "BOS",
        "outbound_date": "2026-04-17", "return_date": "2026-04-19",
        "outbound_depart": "18:00", "outbound_arrive": "20:00",
        "return_depart": "18:00", "return_arrive": "19:30",
        "layovers": 0, "duration_mins": 120, "is_nonstop": True,
        "hours_at_destination": 46,
    }


def _mock_enriched():
    d = _mock_flight()
    d["best_stay"] = {"name": "Hotel", "total_price": 200, "rating": 4.5, "type": "hotel"}
    d["all_stays"] = [d["best_stay"]]
    d["total_trip_cost"] = 350
    d["hotel_search_performed"] = True
    return d


def _full_mock_patches(flight_result=None, hotel_result=None, score_val=70):
    """Return a list of patch context managers that mock the full pipeline dependencies."""
    if flight_result is None:
        flight_result = [_mock_flight()]
    if hotel_result is None:
        hotel_result = [_mock_enriched()]

    return [
        patch("orchestrator.pipeline.asyncio.run", side_effect=[flight_result, hotel_result]),
        patch("orchestrator.pipeline.CostAgent") if score_val else patch("orchestrator.pipeline.CostAgent"),
        patch("orchestrator.pipeline.score_deal", return_value=score_val),
        patch("orchestrator.pipeline.RecommendationAgent"),
        patch("orchestrator.pipeline.is_duplicate", return_value=False),
        patch("orchestrator.pipeline.save_deal"),
        patch("orchestrator.pipeline.write_dashboard"),
        patch("orchestrator.pipeline.render_no_deals_page"),
        patch("orchestrator.pipeline.log_run"),
        patch("orchestrator.pipeline.init_db"),
    ]


# ── tests ───────────────────────────────────────────────────────────────────


def test_pipeline_returns_summary_dict():
    patches = _full_mock_patches()
    with patches[0], patches[1] as mock_cost, patches[2], patches[3] as mock_rec, \
         patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
        mock_cost.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mock_rec.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        result = pipeline_module.run_pipeline()

    assert "started_at" in result
    assert "finished_at" in result
    assert "deals_found" in result
    assert "deals_notified" in result


def test_pipeline_aborts_on_no_flights():
    with patch("orchestrator.pipeline.asyncio.run", return_value=[]), \
         patch("orchestrator.pipeline.render_no_deals_page"), \
         patch("orchestrator.pipeline.log_run"), \
         patch("orchestrator.pipeline.init_db"):
        result = pipeline_module.run_pipeline()

    assert result["deals_found"] == 0


def test_pipeline_aborts_on_no_hotels():
    flights = [_mock_flight()]
    with patch("orchestrator.pipeline.asyncio.run", side_effect=[flights, []]), \
         patch("orchestrator.pipeline.render_no_deals_page"), \
         patch("orchestrator.pipeline.log_run"), \
         patch("orchestrator.pipeline.init_db"):
        result = pipeline_module.run_pipeline()

    assert result["deals_found"] == 0


def test_pipeline_filters_by_score_threshold(monkeypatch):
    monkeypatch.setattr(pipeline_module, "SCORE_THRESHOLD", 55)
    deals = [_mock_enriched(), _mock_enriched(), _mock_enriched()]
    scores = [80, 60, 40]
    score_iter = iter(scores)

    with patch("orchestrator.pipeline.asyncio.run", side_effect=[[_mock_flight()], deals]), \
         patch("orchestrator.pipeline.CostAgent") as mock_cost, \
         patch("orchestrator.pipeline.score_deal", side_effect=lambda d, c: next(score_iter)), \
         patch("orchestrator.pipeline.RecommendationAgent") as mock_rec, \
         patch("orchestrator.pipeline.is_duplicate", return_value=False), \
         patch("orchestrator.pipeline.save_deal"), \
         patch("orchestrator.pipeline.write_dashboard"), \
         patch("orchestrator.pipeline.log_run"), \
         patch("orchestrator.pipeline.init_db"):
        mock_cost.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mock_rec.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        result = pipeline_module.run_pipeline()

    assert result["deals_found"] == 2  # 80 and 60 pass threshold 55


def test_pipeline_deduplicates():
    patches = _full_mock_patches()
    with patches[0], patches[1] as mock_cost, patches[2], patches[3] as mock_rec, \
         patch("orchestrator.pipeline.is_duplicate", return_value=True), \
         patches[5], patches[6], patches[7], patches[8], patches[9]:
        mock_cost.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mock_rec.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        result = pipeline_module.run_pipeline()

    assert result["deals_notified"] == 0


def test_pipeline_saves_new_deals():
    with patch("orchestrator.pipeline.asyncio.run", side_effect=[[_mock_flight()], [_mock_enriched()]]), \
         patch("orchestrator.pipeline.CostAgent") as mock_cost, \
         patch("orchestrator.pipeline.score_deal", return_value=70), \
         patch("orchestrator.pipeline.RecommendationAgent") as mock_rec, \
         patch("orchestrator.pipeline.is_duplicate", return_value=False), \
         patch("orchestrator.pipeline.save_deal") as mock_save, \
         patch("orchestrator.pipeline.write_dashboard"), \
         patch("orchestrator.pipeline.log_run"), \
         patch("orchestrator.pipeline.init_db"):
        mock_cost.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mock_rec.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        pipeline_module.run_pipeline()

    assert mock_save.call_count == 1


def test_pipeline_calls_dashboard():
    with patch("orchestrator.pipeline.asyncio.run", side_effect=[[_mock_flight()], [_mock_enriched()]]), \
         patch("orchestrator.pipeline.CostAgent") as mock_cost, \
         patch("orchestrator.pipeline.score_deal", return_value=70), \
         patch("orchestrator.pipeline.RecommendationAgent") as mock_rec, \
         patch("orchestrator.pipeline.is_duplicate", return_value=False), \
         patch("orchestrator.pipeline.save_deal"), \
         patch("orchestrator.pipeline.write_dashboard") as mock_dash, \
         patch("orchestrator.pipeline.log_run"), \
         patch("orchestrator.pipeline.init_db"):
        mock_cost.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mock_rec.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        pipeline_module.run_pipeline()

    mock_dash.assert_called_once()


def test_pipeline_handles_exception():
    with patch("orchestrator.pipeline.asyncio.run", side_effect=RuntimeError("boom")), \
         patch("orchestrator.pipeline.render_no_deals_page"), \
         patch("orchestrator.pipeline.init_db"):
        result = pipeline_module.run_pipeline()

    assert result["deals_found"] == 0
    assert result["deals_notified"] == 0


def test_pipeline_logs_run():
    with patch("orchestrator.pipeline.asyncio.run", side_effect=[[_mock_flight()], [_mock_enriched()]]), \
         patch("orchestrator.pipeline.CostAgent") as mock_cost, \
         patch("orchestrator.pipeline.score_deal", return_value=70), \
         patch("orchestrator.pipeline.RecommendationAgent") as mock_rec, \
         patch("orchestrator.pipeline.is_duplicate", return_value=False), \
         patch("orchestrator.pipeline.save_deal"), \
         patch("orchestrator.pipeline.write_dashboard"), \
         patch("orchestrator.pipeline.log_run") as mock_log, \
         patch("orchestrator.pipeline.init_db"):
        mock_cost.return_value.compute_full_budget = MagicMock(side_effect=lambda d: d)
        mock_rec.return_value.generate_batch = MagicMock(side_effect=lambda d: d)
        pipeline_module.run_pipeline()

    mock_log.assert_called_once()
    args = mock_log.call_args[0]
    assert len(args) == 4  # started_at, finished_at, found, notified


def test_score_threshold_env_override(monkeypatch):
    monkeypatch.setenv("DEAL_SCORE_THRESHOLD", "75")
    import importlib
    importlib.reload(pipeline_module)
    assert pipeline_module.SCORE_THRESHOLD == 75.0
    # Restore default
    monkeypatch.delenv("DEAL_SCORE_THRESHOLD", raising=False)
    importlib.reload(pipeline_module)
