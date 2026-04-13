"""Hotel search agent — finds accommodation matching constraints."""

from typing import Any


class HotelAgent:
    """Search for hotel options at the destination that meet rating and budget requirements.

    Coordinates with the Booking scraper, filters by minimum rating,
    price cap, and proximity preferences.
    """

    def search(self, destination: str, check_in: str, check_out: str, constraints: dict) -> list[dict[str, Any]]:
        """Return a list of matching hotel option dicts for the given destination and dates."""
        pass
