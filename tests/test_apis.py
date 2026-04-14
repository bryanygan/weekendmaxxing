"""Tests for API clients."""

import json
from unittest.mock import patch, MagicMock

import pytest

from apis.amadeus import AmadeusClient
from apis.kiwi import KiwiClient
from apis.serpapi_flights import SerpApiClient


# ── Amadeus ──────────────────────────────────────────────────────────────────


@pytest.fixture
def amadeus_client():
    return AmadeusClient(api_key="test_key", api_secret="test_secret")


def test_amadeus_get_token(amadeus_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "tok123", "expires_in": 1799}

    with patch("apis.amadeus.requests.post", return_value=mock_resp):
        token = amadeus_client._get_token()
    assert token == "tok123"


def test_amadeus_search_flights(amadeus_client):
    token_resp = MagicMock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "tok123", "expires_in": 1799}

    flight_resp = MagicMock()
    flight_resp.status_code = 200
    flight_resp.json.return_value = {
        "data": [{
            "price": {"total": "149.00", "currency": "USD"},
            "itineraries": [
                {"segments": [{"departure": {"iataCode": "PHL", "at": "2026-04-17T18:00:00"},
                               "arrival": {"iataCode": "BOS", "at": "2026-04-17T19:25:00"},
                               "carrierCode": "AA", "duration": "PT1H25M"}]},
                {"segments": [{"departure": {"iataCode": "BOS", "at": "2026-04-19T17:00:00"},
                               "arrival": {"iataCode": "PHL", "at": "2026-04-19T18:30:00"},
                               "carrierCode": "AA", "duration": "PT1H30M"}]},
            ],
        }],
    }

    with patch("apis.amadeus.requests.post", return_value=token_resp), \
         patch("apis.amadeus.requests.get", return_value=flight_resp):
        results = amadeus_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["price_usd"] == 149.0
    assert results[0]["airline"] == "AA"
    assert results[0]["source"] == "amadeus"
    assert results[0]["layovers"] == 0


def test_amadeus_search_flights_empty_on_error(amadeus_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("apis.amadeus.requests.post", return_value=mock_resp):
        results = amadeus_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert results == []


def test_amadeus_search_hotels(amadeus_client):
    token_resp = MagicMock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "tok123", "expires_in": 1799}

    hotel_resp = MagicMock()
    hotel_resp.status_code = 200
    hotel_resp.json.return_value = {
        "data": [{
            "hotel": {"name": "Test Hotel", "rating": "4"},
            "offers": [{"price": {"total": "278.00", "currency": "USD"}}],
        }],
    }

    with patch("apis.amadeus.requests.post", return_value=token_resp), \
         patch("apis.amadeus.requests.get", return_value=hotel_resp):
        results = amadeus_client.search_hotels("BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["name"] == "Test Hotel"
    assert results[0]["total_price"] == 278.0
    assert results[0]["source"] == "amadeus"


# ── Kiwi ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def kiwi_client():
    return KiwiClient(api_key="test_key")


def test_kiwi_search_flights(kiwi_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{
            "price": 159,
            "airlines": ["B6"],
            "route": [
                {"cityFrom": "Philadelphia", "flyFrom": "PHL",
                 "cityTo": "Boston", "flyTo": "BOS",
                 "local_departure": "2026-04-17T18:00:00.000Z",
                 "local_arrival": "2026-04-17T19:20:00.000Z"},
                {"cityFrom": "Boston", "flyFrom": "BOS",
                 "cityTo": "Philadelphia", "flyTo": "PHL",
                 "local_departure": "2026-04-19T17:00:00.000Z",
                 "local_arrival": "2026-04-19T18:30:00.000Z"},
            ],
            "deep_link": "https://kiwi.com/booking/abc123",
            "duration": {"departure": 4800, "return": 5400},
        }],
    }

    with patch("apis.kiwi.requests.get", return_value=mock_resp):
        results = kiwi_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["price_usd"] == 159
    assert results[0]["source"] == "kiwi"
    assert results[0]["booking_link"] == "https://kiwi.com/booking/abc123"


def test_kiwi_search_flights_empty_on_error(kiwi_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("apis.kiwi.requests.get", return_value=mock_resp):
        results = kiwi_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert results == []


# ── Serpapi ───────────────────────────────────────────────────────────────────


@pytest.fixture
def serpapi_client():
    return SerpApiClient(api_key="test_key")


def test_serpapi_search_flights(serpapi_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "best_flights": [{
            "price": 189,
            "flights": [
                {"departure_airport": {"id": "PHL", "time": "2026-04-17 18:00"},
                 "arrival_airport": {"id": "BOS", "time": "2026-04-17 19:25"},
                 "airline": "American Airlines", "duration": 85},
            ],
            "layovers": [],
            "total_duration": 85,
        }],
        "other_flights": [],
    }

    with patch("apis.serpapi_flights.requests.get", return_value=mock_resp):
        results = serpapi_client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert len(results) >= 1
    assert results[0]["price_usd"] == 189
    assert results[0]["source"] == "serpapi"


def test_serpapi_empty_on_no_key():
    client = SerpApiClient(api_key="")
    results = client.search_flights("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert results == []
