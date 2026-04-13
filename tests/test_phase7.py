"""Phase 7 tests — Local Dashboard."""

from pathlib import Path

import pytest

from notifications.local_dashboard import render_no_deals_page, write_dashboard


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def _make_deal(destination="Boston", score=72.5, estimated_total=487.50, **kwargs):
    base = {
        "destination": destination, "score": score,
        "outbound_date": "2026-04-17", "return_date": "2026-04-19",
        "airline": "AA", "price_usd": 150, "layovers": 0,
        "outbound_depart": "18:00", "outbound_arrive": "20:00",
        "return_depart": "18:00", "return_arrive": "19:30",
        "best_stay": {"name": "Test Hotel", "total_price": 250, "rating": 4.2, "type": "hotel"},
        "all_stays": [], "estimated_total": estimated_total,
        "total_trip_cost": 400, "hours_at_destination": 46,
        "recommendations": "Some recs",
    }
    base.update(kwargs)
    return base


@pytest.fixture
def out_path(tmp_path):
    return str(tmp_path / "dashboard.html")


def test_write_dashboard_creates_file(out_path):
    write_dashboard([], output_path=out_path)
    assert Path(out_path).exists()


def test_write_dashboard_empty_state(out_path):
    write_dashboard([], output_path=out_path)
    html = _read(out_path)
    assert "No deals found" in html


def test_write_dashboard_shows_destination(out_path):
    write_dashboard([_make_deal(destination="Boston")], output_path=out_path)
    html = _read(out_path)
    assert "Boston" in html


def test_write_dashboard_shows_score(out_path):
    write_dashboard([_make_deal(score=72.5)], output_path=out_path)
    html = _read(out_path)
    assert "72.5" in html


def test_write_dashboard_shows_price(out_path):
    write_dashboard([_make_deal(estimated_total=487.50)], output_path=out_path)
    html = _read(out_path)
    assert "487" in html


def test_write_dashboard_multiple_deals(out_path):
    deals = [
        _make_deal(destination="Boston"),
        _make_deal(destination="Miami"),
        _make_deal(destination="Chicago"),
    ]
    write_dashboard(deals, output_path=out_path)
    html = _read(out_path)
    assert "Boston" in html
    assert "Miami" in html
    assert "Chicago" in html


def test_write_dashboard_score_order(out_path):
    deals = [
        _make_deal(destination="Low", score=45),
        _make_deal(destination="High", score=80),
        _make_deal(destination="Mid", score=62),
    ]
    write_dashboard(deals, output_path=out_path)
    html = _read(out_path)
    # High should appear before Mid, Mid before Low
    assert html.index("High") < html.index("Mid") < html.index("Low")


def test_write_dashboard_valid_html(out_path):
    write_dashboard([], output_path=out_path)
    html = _read(out_path)
    assert html.startswith("<!DOCTYPE html>")


def test_write_dashboard_no_external_deps(out_path):
    write_dashboard([_make_deal()], output_path=out_path)
    html = _read(out_path).lower()
    assert "cdn" not in html


def test_render_no_deals_page_creates_file(out_path):
    render_no_deals_page(output_path=out_path)
    assert Path(out_path).exists()
    html = _read(out_path)
    assert "202" in html  # timestamp year
