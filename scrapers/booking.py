"""Booking.com scraper — extracts hotel data via Playwright."""

from typing import Any


class BookingScraper:
    """Scrape Booking.com search results using a headless browser.

    Navigates to Booking.com, enters destination and date parameters,
    and extracts price, rating, name, and location data.
    """

    def scrape(self, destination: str, check_in: str, check_out: str) -> list[dict[str, Any]]:
        """Return raw hotel result dicts scraped from Booking.com."""
        pass
