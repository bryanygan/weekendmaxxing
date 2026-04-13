"""Phase 2 tests — Google Flights scraper."""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from scrapers.google_flights import build_url, fetch_raw


# ── build_url tests ─────────────────────────────────────────────────────────


def test_build_url_format():
    url = build_url("PHL", "BOS", "2026-04-17", "2026-04-19")
    assert "PHL" in url
    assert "BOS" in url
    assert "2026-04-17" in url
    assert "2026-04-19" in url
    assert url.startswith("https://www.google.com/travel/flights/search")


def test_build_url_no_spaces():
    url = build_url("PHL", "MIA", "2026-04-17", "2026-04-19")
    assert " " not in url


# ── fetch_raw tests ─────────────────────────────────────────────────────────


def _next_friday():
    today = date.today()
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_raw_returns_string():
    friday = _next_friday()
    sunday = friday + timedelta(days=2)
    result = await fetch_raw("PHL", "BOS", friday.isoformat(), sunday.isoformat())
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_fetch_raw_captcha_returns_empty():
    with patch("scrapers.google_flights.async_playwright") as mock_pw:
        # Build the mock chain: async_playwright() -> context manager -> browser -> context -> page
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.inner_text = AsyncMock(return_value="Please complete the captcha to continue")
        mock_page.evaluate = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.google_flights.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_raw("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert result == ""


@pytest.mark.asyncio
async def test_fetch_raw_timeout_returns_empty():
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    with patch("scrapers.google_flights.async_playwright") as mock_pw:
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=PlaywrightTimeout("Timeout"))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_raw("PHL", "BOS", "2026-04-17", "2026-04-19")

    assert result == ""
