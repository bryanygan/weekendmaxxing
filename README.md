# Weekend Deal Hunter

Automated weekend trip deal finder for Philadelphia. Scans flights, trains (Amtrak + SEPTA), hotels, and Airbnbs across 48 destinations, scores deals against budget and timing constraints, and produces ranked recommendations with AI-generated itineraries.

Runs entirely locally using Ollama (llama3.1:8b) for data extraction and recommendation generation.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Install and start Ollama
# Download from https://ollama.com/download/windows
ollama pull llama3.1:8b
ollama serve

# 3. Run the pipeline once and open the dashboard
python run_once.py
```

## How It Works

```
Destinations (48 cities)
        |
        v
  +------------------+     +------------------+
  |  FlightAgent     |     |  TrainAgent      |
  |  Google Flights  |     |  Amtrak          |
  |  Kayak           |     |  SEPTA           |
  |  Skyscanner      |     +------------------+
  +------------------+              |
        |                           |
        +---------> Merge <---------+
                     |
                     v
             +---------------+
             |  HotelAgent   |
             |  Booking.com  |
             |  Airbnb       |
             +---------------+
                     |
                     v
             +---------------+
             |  CostAgent    |
             |  LLM-estimated|
             |  transit/food |
             +---------------+
                     |
                     v
             +---------------+
             |  Deal Scorer  |
             |  0-100 score  |
             +---------------+
                     |
                     v
             +------------------+
             | Recommendations  |
             | LLM itineraries  |
             +------------------+
                     |
          +----------+----------+
          |          |          |
          v          v          v
      Dashboard  Desktop   Email
      (HTML)     Toast     Alert
```

## Transport Sources

| Source | Type | What It Scrapes |
|--------|------|-----------------|
| Google Flights | Flight | Round-trip flights with prices, times, layovers |
| Kayak | Flight | Same, sorted by price |
| Skyscanner | Flight | Same, economy class |
| Amtrak | Train | Northeast Corridor routes from 30th St Station (10 cities) |
| SEPTA | Train | Regional Rail with zone-based fares (7 destinations) |

## Accommodation Sources

| Source | What It Scrapes |
|--------|-----------------|
| Booking.com | Hotels, hostels — name, price, rating, neighborhood |
| Airbnb | Apartments, rooms — name, price, rating, neighborhood |

## Destinations

**48 destinations** from Philadelphia, including:

- **With Amtrak service (10):** New York, Boston, Washington DC, Baltimore, Pittsburgh, Richmond, Norfolk, Raleigh, Charlotte, Providence
- **With SEPTA Regional Rail (7):** Trenton, Newark, Wilmington, Doylestown, Norristown, Lansdale, West Chester
- **Flight-only (31):** Miami, Orlando, Tampa, Fort Lauderdale, West Palm Beach, Key West, Atlanta, Nashville, Chicago, Detroit, Charleston, Savannah, New Orleans, San Juan, Myrtle Beach, Hilton Head, Jacksonville, Toronto, Montreal, Bermuda, St. Louis, Cincinnati, Cleveland, Buffalo, Burlington, Portland ME, Nantucket, Martha's Vineyard, Minneapolis, Denver, Austin, San Antonio, Dallas, Houston, Cancun, Nassau, Punta Cana, Reykjavik

## Constraints

All configurable in `config/constraints.json`:

| Constraint | Flights | Trains |
|-----------|---------|--------|
| Max round-trip price | $300 | $200 |
| Friday earliest departure | 17:00 | 16:00 |
| Saturday latest departure | 09:00 | 10:00 |
| Sunday latest arrival home | 22:00 | 23:00 |
| Min hours at destination | 24 | 24 |
| Max layovers/stops | 1 | 2 |
| Min hotel rating | 3.5/5 | 3.5/5 |
| Max hotel per night | $150 | $150 |

Trains have relaxed timing constraints because there's no airport security overhead and 30th Street Station is in the city center.

## Deal Scoring (0-100)

| Factor | Points | How It's Calculated |
|--------|--------|---------------------|
| Price | 40 | Lower price relative to budget cap = higher score |
| Nonstop/Direct | 20 | 0 stops = 20pts, 1 stop = 10-15pts, 2+ = 0pts |
| Hotel Quality | 20 | Rating / 5.0 * 20 |
| Time at Destination | 10 | Hours / 48 * 10, capped at 10 |
| Return Buffer | 10 | Earlier return = more buffer = higher score |
| Train Convenience Bonus | +5 | Trains get +5 (no airport, city center) |

## CLI Options

```bash
# Basic run — scans all destinations, opens dashboard
python run_once.py

# Custom budget
python run_once.py --budget 400 --max-flight 250 --max-hotel 100

# Search specific cities only
python run_once.py --destinations Boston Miami "Washington DC"

# Fewer weekends (faster)
python run_once.py --weekends 2

# Higher score threshold
python run_once.py --threshold 70

# Start the live filterable dashboard server
python run_once.py --server

# Don't auto-open browser
python run_once.py --no-browser
```

## Scheduler

```bash
# Run on a recurring schedule
python scheduler.py
```

- Runs the pipeline immediately on startup
- Then every 6 hours automatically
- Tuesday 9:00 AM aggressive run
- Ctrl+C to stop

## Live Dashboard

```bash
python run_once.py --server
```

Opens a Flask-powered dashboard at `http://127.0.0.1:5050` with:

- Real-time filtering by max price, min score, destination, nonstop-only
- Sort by score, price, or destination
- Auto-refreshes every 60 seconds
- Collapsible recommendations and hotel alternatives per deal

## Notifications

| Channel | Setup |
|---------|-------|
| **HTML Dashboard** | Always generated at `data/dashboard.html` (auto-refreshes every 10 min) |
| **Desktop Toast** | Automatic — Windows (PowerShell), macOS (osascript), Linux (notify-send) |
| **Email** | Set env vars: `EMAIL_ENABLED=true`, `EMAIL_SENDER`, `EMAIL_PASSWORD`, `EMAIL_RECIPIENT` |

## Project Structure

```
weekendmaxxing/
├── agents/
│   ├── flight_agent.py         # Multi-source flight search + LLM parsing
│   ├── train_agent.py          # Amtrak + SEPTA search + LLM parsing
│   ├── hotel_agent.py          # Booking.com + Airbnb search + LLM parsing
│   ├── cost_agent.py           # LLM-estimated transit/food/activity costs
│   └── recommendation_agent.py # LLM-generated weekend itineraries
├── orchestrator/
│   ├── pipeline.py             # End-to-end pipeline orchestration
│   ├── deal_scorer.py          # Weighted 0-100 scoring with train bonus
│   └── state_manager.py        # SQLite: deals, runs, price history
├── scrapers/
│   ├── google_flights.py       # Playwright + stealth
│   ├── kayak.py                # Playwright + stealth
│   ├── skyscanner.py           # Playwright + stealth
│   ├── booking.py              # Playwright + stealth
│   ├── airbnb.py               # Playwright + stealth
│   ├── amtrak.py               # Playwright + station codes
│   └── septa.py                # Zone fares + schedule scraping
├── utils/
│   ├── llm.py                  # Ollama client with 3x retry
│   ├── json_extractor.py       # Extracts JSON from LLM output
│   └── rate_limiter.py         # 3-7s random delays per domain
├── notifications/
│   ├── local_dashboard.py      # Static HTML dashboard generator
│   ├── live_dashboard.py       # Flask server with filtering
│   ├── desktop_notify.py       # OS-native toast notifications
│   └── email_notify.py         # SMTP email alerts
├── config/
│   ├── destinations.json       # 48 destinations with Amtrak metadata
│   ├── constraints.json        # Budget, timing, preference constraints
│   └── settings.py             # Env var configuration
├── data/                       # SQLite DB + dashboard output (gitignored)
├── tests/                      # 122 tests across 11 test files
├── run_once.py                 # CLI entry point with argument parsing
├── scheduler.py                # APScheduler for recurring runs
└── requirements.txt
```

## Configuration

All settings can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_LOCAL_LLM` | `true` | Use local Ollama instance |
| `LOCAL_LLM_URL` | `http://localhost:11434/api/chat` | Ollama endpoint |
| `LOCAL_LLM_MODEL` | `llama3.1:8b` | Model to use |
| `DEAL_SCORE_THRESHOLD` | `55` | Minimum score to surface a deal |
| `EMAIL_ENABLED` | `false` | Enable email notifications |
| `EMAIL_SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `EMAIL_SMTP_PORT` | `587` | SMTP port |
| `EMAIL_SENDER` | | Sender email address |
| `EMAIL_PASSWORD` | | Sender email password (use app passwords for Gmail) |
| `EMAIL_RECIPIENT` | | Recipient email address |
| `DASHBOARD_HOST` | `127.0.0.1` | Live dashboard bind address |
| `DASHBOARD_PORT` | `5050` | Live dashboard port |

## Tests

```bash
# Run all tests (except live network tests)
pytest tests/ -m "not slow and not llm"

# Run with live Ollama
pytest tests/ -m "not slow"

# Full suite including real scraping
pytest tests/ -v
```

**122 tests** covering: scaffold integrity, LLM client, JSON extraction, all scrapers, all agents, constraint checking, deal scoring, pipeline orchestration, state management, dashboard rendering, train support, and integration.
