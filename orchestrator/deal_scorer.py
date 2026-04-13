"""Deal scorer — assigns a composite score to each flight+hotel bundle."""

from typing import Any


class DealScorer:
    """Score deal bundles on price, timing convenience, hotel quality, and destination appeal.

    Produces a normalised 0-100 score for each candidate deal.
    """

    def score(self, deal: dict[str, Any]) -> float:
        """Return a 0-100 composite score for the given deal bundle."""
        pass
