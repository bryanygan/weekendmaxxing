# Weekend Deal Hunter

Automated weekend trip deal finder. Searches flights and hotels from PHL to
nearby destinations, scores deals against budget and timing constraints, and
produces ranked recommendations.

## Quick start

```bash
pip install -r requirements.txt
playwright install chromium
pytest tests/
```

## Project structure

- **agents/** — LLM-backed agents for flights, hotels, costs, and recommendations
- **orchestrator/** — pipeline coordination, scoring, and state management
- **scrapers/** — Playwright-based scrapers for Google Flights and Booking.com
- **utils/** — LLM client and JSON extraction helpers
- **notifications/** — local HTML dashboard output
- **config/** — destinations, constraints, and settings
- **scheduler.py** — APScheduler entry point for recurring runs
