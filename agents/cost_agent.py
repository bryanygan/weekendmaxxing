"""Cost estimation agent — computes total trip cost from components."""

from typing import Any


class CostAgent:
    """Aggregate flight, hotel, and incidental costs into a total trip estimate.

    Validates the total against budget constraints and flags over-budget trips.
    """

    def estimate(self, flights: list[dict], hotels: list[dict], constraints: dict) -> dict[str, Any]:
        """Return a cost breakdown dict with total, per-category costs, and budget status."""
        pass
