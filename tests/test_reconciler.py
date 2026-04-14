"""Tests for the data reconciliation layer."""

import pytest

from orchestrator.reconciler import reconcile_flights, reconcile_hotels


def _flight(price, source, airline="AA", depart="18:00", arrive="19:25", **kw):
    base = {
        "price_usd": price, "source": source, "airline": airline,
        "outbound_depart": depart, "outbound_arrive": arrive,
        "return_depart": "17:00", "return_arrive": "18:30",
        "layovers": 0, "duration_mins": 85, "is_nonstop": True,
        "destination": "Boston", "iata": "BOS",
        "outbound_date": "2026-04-17", "return_date": "2026-04-19",
        "booking_link": None, "price_confidence": "high",
    }
    base.update(kw)
    return base


def test_reconcile_groups_same_flight():
    flights = [_flight(149, "amadeus"), _flight(155, "kiwi")]
    result = reconcile_flights(flights)
    assert len(result) == 1


def test_reconcile_keeps_different_flights():
    flights = [_flight(149, "amadeus", airline="AA"), _flight(199, "kiwi", airline="DL")]
    result = reconcile_flights(flights)
    assert len(result) == 2


def test_reconcile_high_confidence_when_3_agree():
    flights = [_flight(149, "amadeus"), _flight(155, "kiwi"), _flight(152, "serpapi")]
    result = reconcile_flights(flights)
    assert len(result) == 1
    assert result[0]["price_confidence"] == "high"
    assert result[0]["price_usd"] == 152  # median


def test_reconcile_medium_confidence_when_2_agree():
    flights = [_flight(149, "amadeus"), _flight(160, "kiwi")]
    result = reconcile_flights(flights)
    assert result[0]["price_confidence"] == "medium"
    assert result[0]["price_usd"] == 149  # lower of two


def test_reconcile_low_confidence_single_source():
    flights = [_flight(149, "amadeus")]
    result = reconcile_flights(flights)
    assert result[0]["price_confidence"] == "low"


def test_reconcile_low_confidence_when_disagree():
    flights = [_flight(100, "amadeus"), _flight(200, "kiwi")]
    result = reconcile_flights(flights)
    assert result[0]["price_confidence"] == "low"


def test_reconcile_prefers_api_over_scraper():
    flights = [
        _flight(149, "amadeus", price_confidence="high"),
        _flight(999, "google_flights", price_confidence="low"),
    ]
    result = reconcile_flights(flights)
    assert result[0]["price_usd"] == 149


def test_reconcile_keeps_booking_link():
    flights = [
        _flight(149, "amadeus"),
        _flight(155, "kiwi", booking_link="https://kiwi.com/book/123"),
    ]
    result = reconcile_flights(flights)
    assert result[0]["booking_link"] == "https://kiwi.com/book/123"


def test_reconcile_collects_price_sources():
    flights = [_flight(149, "amadeus"), _flight(155, "kiwi")]
    result = reconcile_flights(flights)
    assert set(result[0]["price_sources"]) == {"amadeus", "kiwi"}


def test_reconcile_time_tolerance():
    flights = [_flight(149, "amadeus", depart="18:00"), _flight(155, "kiwi", depart="18:20")]
    result = reconcile_flights(flights)
    assert len(result) == 1


def test_reconcile_time_too_far_apart():
    flights = [_flight(149, "amadeus", depart="18:00"), _flight(155, "kiwi", depart="20:00")]
    result = reconcile_flights(flights)
    assert len(result) == 2


def test_reconcile_empty_input():
    assert reconcile_flights([]) == []


def _hotel(name, price, source, rating=4.2, **kw):
    base = {
        "name": name, "total_price": price, "price_per_night": price / 2,
        "rating": rating, "review_count": 100, "type": "hotel",
        "neighborhood": "Downtown", "source": source,
    }
    base.update(kw)
    return base


def test_reconcile_hotels_groups_same_name():
    hotels = [_hotel("The Godfrey", 338, "amadeus"), _hotel("The Godfrey Hotel", 350, "booking.com")]
    result = reconcile_hotels(hotels)
    assert len(result) == 1


def test_reconcile_hotels_keeps_different():
    hotels = [_hotel("The Godfrey", 338, "amadeus"), _hotel("HI Boston Hostel", 118, "booking.com")]
    result = reconcile_hotels(hotels)
    assert len(result) == 2


def test_reconcile_hotels_prefers_api_price():
    hotels = [_hotel("The Godfrey", 338, "amadeus"), _hotel("The Godfrey Hotel", 999, "booking.com")]
    result = reconcile_hotels(hotels)
    assert result[0]["total_price"] == 338
