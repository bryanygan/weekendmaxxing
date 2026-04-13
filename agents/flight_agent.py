"""Flight search agent — finds outbound/return flights matching constraints."""

from typing import Any


class FlightAgent:
    """Search for round-trip flights that fit the weekend timing and budget constraints.

    Coordinates with the Google Flights scraper, filters by departure windows,
    layover limits, and price caps, then returns ranked flight options.
    """

    def search(self, origin: str, destination: str, constraints: dict) -> list[dict[str, Any]]:
        """Return a list of matching flight option dicts for the given route and constraints."""
        pass
