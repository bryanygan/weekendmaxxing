"""Recommendation agent — ranks and explains the best weekend deals."""

from typing import Any


class RecommendationAgent:
    """Use an LLM to rank scored deals and produce human-readable recommendations.

    Takes scored deal bundles and generates a prioritised list with
    natural-language explanations of why each deal is worth considering.
    """

    def recommend(self, scored_deals: list[dict]) -> list[dict[str, Any]]:
        """Return ranked recommendations with explanations."""
        pass
