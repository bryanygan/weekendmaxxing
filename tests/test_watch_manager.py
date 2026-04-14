"""Tests for watch list management."""

import pytest

from orchestrator import watch_manager as wm


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_prefs.db")
    monkeypatch.setattr(wm, "PREFS_DB_PATH", db_path)


def test_init_creates_table():
    wm.init_watches_db()
    assert wm.get_watch_count() == 0


def test_add_watch():
    wm.init_watches_db()
    assert wm.add_watch("Miami") is True
    assert wm.get_watch_count() == 1


def test_add_watch_with_date():
    wm.init_watches_db()
    assert wm.add_watch("Miami", "2026-05-01") is True
    watches = wm.get_watches()
    assert watches[0]["specific_date"] == "2026-05-01"


def test_add_watch_max_5():
    wm.init_watches_db()
    for city in ["A", "B", "C", "D", "E"]:
        wm.add_watch(city)
    assert wm.add_watch("F") is False
    assert wm.get_watch_count() == 5


def test_add_watch_no_duplicate():
    wm.init_watches_db()
    wm.add_watch("Miami")
    assert wm.add_watch("Miami") is False


def test_remove_watch():
    wm.init_watches_db()
    wm.add_watch("Miami")
    assert wm.remove_watch("Miami") is True
    assert wm.get_watch_count() == 0


def test_remove_watch_not_found():
    wm.init_watches_db()
    assert wm.remove_watch("Nowhere") is False


def test_get_watches():
    wm.init_watches_db()
    wm.add_watch("Miami")
    wm.add_watch("Boston")
    watches = wm.get_watches()
    assert len(watches) == 2
    assert all("destination" in w for w in watches)


def test_update_watch_price():
    wm.init_watches_db()
    wm.add_watch("Miami")
    wm.update_watch_price("Miami", 149.0)
    watches = wm.get_watches()
    assert watches[0]["last_price"] == 149.0
    assert watches[0]["last_checked_at"] is not None


def test_is_watched():
    wm.init_watches_db()
    wm.add_watch("Miami")
    assert wm.is_watched("Miami") is True
    assert wm.is_watched("Chicago") is False
