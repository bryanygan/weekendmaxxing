"""Pipeline — end-to-end orchestration of the deal-hunting workflow."""

from typing import Any


class Pipeline:
    """Orchestrate the full search-score-recommend pipeline.

    Loads config, fans out searches across destinations, collects results,
    scores deals, and produces final recommendations.
    """

    def run(self, weekend_date: str | None = None) -> list[dict[str, Any]]:
        """Execute the full pipeline for the next (or given) weekend and return recommendations."""
        pass
