"""Google Flights scraper — extracts flight data via Playwright."""

from typing import Any


class GoogleFlightsScraper:
    """Scrape Google Flights search results using a headless browser.

    Navigates to Google Flights, enters route and date parameters,
    and extracts price, duration, layover, and schedule data.
    """

    def scrape(self, origin: str, destination: str, depart_date: str, return_date: str) -> list[dict[str, Any]]:
        """Return raw flight result dicts scraped from Google Flights."""
        pass
