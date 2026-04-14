"""Tests for the source router — API-first with scraper fallback."""

from unittest.mock import MagicMock, patch

import pytest

from orchestrator.source_router import fetch_flights, fetch_flights_multi, fetch_hotels


@pytest.fixture(autouse=True)
def _mock_quota(monkeypatch):
    """Ensure quota DB doesn't interfere."""
    import orchestrator.quota_manager as qm
    monkeypatch.setattr(qm, "DB_PATH", ":memory:")


def test_fetch_flights_uses_api_first():
    api_results = [{"price_usd": 149, "source": "amadeus", "airline": "AA"}]

    with patch("orchestrator.source_router._get_amadeus_client") as mock_amadeus, \
         patch("orchestrator.source_router._get_kiwi_client") as mock_kiwi:
        mock_amadeus.return_value.search_flights.return_value = api_results
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["source"] == "amadeus"


def test_fetch_flights_falls_back_to_kiwi():
    kiwi_results = [{"price_usd": 159, "source": "kiwi", "airline": "B6"}]

    with patch("orchestrator.source_router._get_amadeus_client") as mock_amadeus, \
         patch("orchestrator.source_router._get_kiwi_client") as mock_kiwi, \
         patch("orchestrator.source_router._get_serpapi_client") as mock_serpapi:
        mock_amadeus.return_value.search_flights.return_value = []
        mock_kiwi.return_value.search_flights.return_value = kiwi_results
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "kiwi"


def test_fetch_flights_falls_back_to_scraper():
    with patch("orchestrator.source_router._get_amadeus_client") as mock_a, \
         patch("orchestrator.source_router._get_kiwi_client") as mock_k, \
         patch("orchestrator.source_router._get_serpapi_client") as mock_s, \
         patch("orchestrator.source_router._scraper_fetch_flights") as mock_scraper:
        mock_a.return_value.search_flights.return_value = []
        mock_k.return_value.search_flights.return_value = []
        mock_s.return_value.search_flights.return_value = []
        mock_scraper.return_value = [{"price_usd": 199, "source": "google_flights"}]
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "google_flights"


def test_fetch_flights_skips_api_when_no_key():
    with patch("orchestrator.source_router._get_amadeus_client", return_value=None), \
         patch("orchestrator.source_router._get_kiwi_client", return_value=None), \
         patch("orchestrator.source_router._get_serpapi_client", return_value=None), \
         patch("orchestrator.source_router._scraper_fetch_flights") as mock_scraper:
        mock_scraper.return_value = [{"price_usd": 199, "source": "kayak"}]
        results = fetch_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1


def test_fetch_hotels_api_first():
    api_results = [{"name": "Hotel", "total_price": 278, "source": "amadeus"}]

    with patch("orchestrator.source_router._get_amadeus_client") as mock_amadeus:
        mock_amadeus.return_value.search_hotels.return_value = api_results
        results = fetch_hotels("BOS", "Boston", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "amadeus"


def test_fetch_hotels_falls_back_to_scraper():
    with patch("orchestrator.source_router._get_amadeus_client") as mock_a, \
         patch("orchestrator.source_router._scraper_fetch_hotels") as mock_scraper:
        mock_a.return_value.search_hotels.return_value = []
        mock_scraper.return_value = [{"name": "Hostel", "source": "booking.com"}]
        results = fetch_hotels("BOS", "Boston", "2026-04-17", "2026-04-19")

    assert results[0]["source"] == "booking.com"


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
