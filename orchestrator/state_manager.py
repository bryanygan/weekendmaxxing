"""State manager — tracks pipeline state and caches intermediate results."""

from typing import Any


class StateManager:
    """Persist and retrieve pipeline state between runs.

    Stores intermediate results (flights, hotels, scores) so that
    partial runs can resume and historical data can be compared.
    """

    def save(self, key: str, data: Any) -> None:
        """Persist data under the given key."""
        pass

    def load(self, key: str) -> Any:
        """Retrieve previously saved data by key, or None if not found."""
        pass
