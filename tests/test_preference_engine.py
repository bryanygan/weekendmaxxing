"""Tests for the preference engine."""

import pytest

from orchestrator import preference_engine as pe
from orchestrator.state_manager import deal_hash


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_prefs.db")
    monkeypatch.setattr(pe, "PREFS_DB_PATH", db_path)


def _make_deal(**overrides):
    base = {
        "destination": "Washington DC", "transport_type": "train",
        "airline": "Amtrak", "price_usd": 98, "score": 73.0,
        "outbound_date": "2026-04-18", "best_stay": {"type": "hotel"},
    }
    base.update(overrides)
    return base


def test_init_creates_tables():
    pe.init_preferences_db()
    assert pe.get_feedback_count() == 0


def test_record_feedback_stores():
    pe.init_preferences_db()
    deal = _make_deal()
    pe.record_feedback(deal, "thumbs_up")
    assert pe.get_feedback_count() == 1


def test_record_feedback_multiple():
    pe.init_preferences_db()
    for _ in range(5):
        pe.record_feedback(_make_deal(), "thumbs_up")
    assert pe.get_feedback_count() == 5


def test_bucket_price():
    assert pe._bucket_price(50) == "0-100"
    assert pe._bucket_price(150) == "100-200"
    assert pe._bucket_price(250) == "200-300"
    assert pe._bucket_price(400) == "300-500"
    assert pe._bucket_price(600) == "500+"


def test_rebuild_profile_from_feedback():
    pe.init_preferences_db()
    deal = _make_deal()
    pe.record_feedback(deal, "thumbs_up")
    pe.record_feedback(deal, "thumbs_up")
    pe.record_feedback(deal, "booked")
    pe.rebuild_profile()

    boost = pe.get_preference_boost(deal)
    assert boost > 0


def test_preference_boost_zero_without_data():
    pe.init_preferences_db()
    deal = _make_deal()
    assert pe.get_preference_boost(deal) == 0


def test_preference_boost_capped_at_5():
    pe.init_preferences_db()
    deal = _make_deal()
    for _ in range(50):
        pe.record_feedback(deal, "booked")
    pe.rebuild_profile()
    boost = pe.get_preference_boost(deal)
    assert boost <= 5.0


def test_thumbs_down_reduces_boost():
    pe.init_preferences_db()
    good = _make_deal(destination="Boston", airline="JetBlue")
    bad = _make_deal(destination="Miami", airline="Spirit")

    pe.record_feedback(good, "thumbs_up")
    pe.record_feedback(good, "thumbs_up")
    pe.record_feedback(bad, "thumbs_down")
    pe.record_feedback(bad, "thumbs_down")
    pe.rebuild_profile()

    assert pe.get_preference_boost(good) > pe.get_preference_boost(bad)


def test_profile_summary():
    pe.init_preferences_db()
    pe.record_feedback(_make_deal(destination="DC"), "booked")
    pe.record_feedback(_make_deal(destination="Boston"), "thumbs_up")
    pe.record_feedback(_make_deal(destination="Miami", airline="Spirit"), "thumbs_down")
    pe.record_feedback(_make_deal(destination="Miami", airline="Spirit"), "thumbs_down")
    pe.rebuild_profile()

    summary = pe.get_profile_summary()
    assert isinstance(summary, dict)
    assert "top_destinations" in summary
    assert "blacklisted_airlines" in summary


def test_booked_weighs_more_than_like():
    pe.init_preferences_db()
    deal_a = _make_deal(destination="DC")
    deal_b = _make_deal(destination="Boston")

    pe.record_feedback(deal_a, "booked")         # weight: +5
    pe.record_feedback(deal_b, "thumbs_up")      # weight: +1
    pe.record_feedback(deal_b, "thumbs_up")      # weight: +1
    pe.record_feedback(deal_b, "thumbs_up")      # weight: +1
    pe.rebuild_profile()

    assert pe.get_preference_boost(deal_a) > pe.get_preference_boost(deal_b)
