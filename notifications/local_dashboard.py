"""Local dashboard — renders deal results to a local HTML report."""

from pathlib import Path


class LocalDashboard:
    """Generate a self-contained HTML dashboard summarising the best weekend deals.

    Writes an HTML file to the data/ directory that can be opened in a browser.
    """

    def render(self, recommendations: list[dict], output_path: Path | None = None) -> Path:
        """Write the HTML dashboard and return the output file path."""
        pass
