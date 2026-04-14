"""Tests for API quota tracking."""

import sqlite3
from pathlib import Path

import pytest

from orchestrator import quota_manager as qm


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_deals.db")
    monkeypatch.setattr(qm, "DB_PATH", db_path)


def test_init_quota_table():
    qm.init_quota_db()
    conn = sqlite3.connect(qm.DB_PATH)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quota_usage'").fetchone()
    conn.close()
    assert row is not None


def test_record_call_increments():
    qm.init_quota_db()
    qm.record_api_call("amadeus")
    qm.record_api_call("amadeus")
    assert qm.get_daily_usage("amadeus") == 2


def test_get_daily_usage_zero_for_new():
    qm.init_quota_db()
    assert qm.get_daily_usage("amadeus") == 0


def test_get_monthly_usage():
    qm.init_quota_db()
    for _ in range(5):
        qm.record_api_call("kiwi")
    assert qm.get_monthly_usage("kiwi") >= 5


def test_has_quota_true_when_under_limit():
    qm.init_quota_db()
    assert qm.has_quota("amadeus") is True


def test_has_quota_false_when_over_limit():
    qm.init_quota_db()
    for _ in range(67):  # daily limit is 66
        qm.record_api_call("amadeus")
    assert qm.has_quota("amadeus") is False


def test_different_apis_tracked_separately():
    qm.init_quota_db()
    qm.record_api_call("amadeus")
    qm.record_api_call("kiwi")
    assert qm.get_daily_usage("amadeus") == 1
    assert qm.get_daily_usage("kiwi") == 1
