# Weekend Deal Hunter v2 — Hybrid Intelligence Enhancement

**Date:** 2026-04-13
**Status:** Approved
**Approach:** Hybrid Layer with Intelligence (APIs primary, scrapers fallback, learning system on top)

## Problem Statement

The current system has three core issues:
1. **Price unreliability** — LLM extracts prices from raw scraped text and hallucinates ~40% of the time (AM/PM format errors, missing fields, invented prices)
2. **Low deal volume** — Hard constraint filters reject deals entirely, resulting in 8 deals when 20-30 are viable
3. **No learning** — Every scan starts from zero. The system doesn't know what the user likes, what they've booked, or whether a price is historically good

## Solution Overview

Three interconnected enhancements:
- **API-first data with scraper fallback** — Structured APIs return real bookable prices; scrapers fill gaps when APIs hit rate limits
- **Soft scoring replaces hard filtering** — Constraints become penalties in a weighted score, not binary pass/fail gates
- **Preference engine** — Learns from user feedback, booking history, and price trends to surface better deals over time

## 1. API Data Sources

### Flight APIs (all free tier)

| API | Free Quota | Returns | Signup |
|-----|-----------|---------|--------|
| Amadeus Self-Service | 2,000 calls/month | Real-time flight offers with bookable prices, airlines, layovers, durations | developers.amadeus.com |
| Kiwi.com Tequila | 3,000 calls/month | Multi-city search with booking deep links, good for budget airlines | tequila.kiwi.com |
| Serpapi Google Flights | 100 calls/month | Structured JSON from Google Flights, low quota but good cross-reference | serpapi.com |

### Hotel API

| API | Free Quota | Returns |
|-----|-----------|---------|
| Amadeus Hotel Search | Shared with flight quota (2,000 total/month) | Hotel offers with real prices, ratings, amenities |

### Train

No API changes. Keep existing Amtrak scraper + SEPTA zone fares. LLM extraction works adequately here because Amtrak schedules and prices are predictable and stable.

### Fallback Chain

```
Flights: Amadeus → Kiwi → Serpapi → Google Flights scraper → Kayak scraper
Hotels:  Amadeus Hotels → Booking.com scraper → Airbnb scraper
Trains:  Amtrak scraper → SEPTA fares (unchanged)
```

Each source in the chain is tried only if the previous one returned no results or hit rate limits. A quota manager tracks monthly usage per API in SQLite and routes to the next source when limits approach.

### API Configuration

New environment variables in `config/settings.py`:

```
AMADEUS_API_KEY=
AMADEUS_API_SECRET=
KIWI_API_KEY=
SERPAPI_API_KEY=
```

All optional. If none are set, the system falls back to scraper-only mode (current behavior). Each API that has a key configured is added to the fallback chain.

## 2. Data Reconciliation Layer

New module: `orchestrator/reconciler.py`

When multiple sources return data for the same route, the reconciler merges them into a single trustworthy result.

### Flight Matching

Same route + similar departure time (within 30 minutes) + same airline = same flight. These are grouped.

### Price Confidence Scoring

For each grouped flight:
- **High confidence**: 3+ sources agree within 10%. Use median price.
- **Medium confidence**: 2 sources agree within 15%. Use lower price.
- **Low confidence**: Only 1 source, or sources disagree by >20%. Flag it, still show but warn.
- API-sourced prices always trusted over LLM-extracted scraper prices when they conflict.

### Reconciled Deal Fields

```python
{
    "price_usd": 149,              # median of agreeing sources (or API price)
    "price_confidence": "high",    # "high" / "medium" / "low"
    "price_sources": ["amadeus", "kiwi"],  # which sources contributed
    "booking_link": "https://...", # deep link from Kiwi or Amadeus
    # all other fields (times, layovers, airline) from highest-priority source
}
```

### Hotel Reconciliation

Same logic — match by name similarity + price range, prefer API data over scraped. Normalize ratings to 5-point scale across sources.

### Confidence Display

- **High**: Green price, no qualifier
- **Medium**: Yellow price, "(~estimated)" label
- **Low**: Red price, "(unverified)" label

Shown in both the HTML dashboard and Discord embeds.

## 3. Soft Scoring

### Current Problem

Hard constraints reject deals entirely: Friday departure before 5pm = filtered out, over budget = gone. This kills deal volume.

### New Approach

Everything that's remotely viable passes through. Constraints become scoring penalties. The user sees 20-30 deals ranked from "amazing" to "meh."

### Revised Scoring Formula (0-100)

| Factor | Points | Description |
|--------|--------|-------------|
| Price | 35 | Ratio-based against budget cap. Cheaper = higher. |
| Nonstop/Direct | 15 | 0 stops = 15, 1 stop = 10 (trains: 12), 2+ = 0-5 |
| Hotel Quality | 15 | (rating / 5.0) * 15 |
| Time at Destination | 10 | (hours / 48) * 10, capped at 10 |
| Return Buffer | 5 | Earlier return home = more buffer = higher score |
| Timing Fit | 10 | **New.** Friday 5pm+ or Saturday before 9am = full points. Outside windows = graduated penalty. Friday 3pm = 6/10, Friday noon = 2/10. Nothing hard-rejected. |
| Price Confidence | 5 | **New.** High = 5, Medium = 3, Low = 1 |
| User Preference | 5 | **New.** Boosted by feedback/booking history (see Section 4) |
| Train Convenience | +5 bonus | No change from current. No airport overhead. |

### Absolute Floors (configurable)

Hard reject only for truly unusable deals:
- Departure before noon on Friday
- Departure after noon on Saturday
- Return after midnight Sunday
- Price over $800 total
- Less than 12 hours at destination

These are much more relaxed than the current constraints. Users can tighten them in `config/constraints.json`.

## 4. User Preference Learning

New module: `orchestrator/preference_engine.py`
New database: `data/preferences.db`

### Layer 1: Feedback Buttons

Every deal DM'd via Discord gets three reaction buttons:
- **Interested** (thumbs up)
- **Not for me** (thumbs down)
- **Book link** (link emoji, opens booking URL)

Each reaction logs:
```python
{
    "deal_hash": "abc123",
    "destination": "Washington DC",
    "transport_type": "train",
    "airline": "Amtrak",
    "price_range": "0-100",    # bucketed
    "hotel_type": "hotel",
    "score": 73.0,
    "reaction": "thumbs_up",   # or "thumbs_down"
    "timestamp": "2026-04-13T14:30:00"
}
```

After 10+ reactions, the system builds a preference profile:
- **Destination affinity**: Weighted by reaction history. DC gets +3 if thumbs-up'd 4 times.
- **Price comfort zone**: Learns actual range vs configured max.
- **Transport preference**: Train vs flight ratio.
- **Airline blacklist**: Consistently thumbs-down'd airlines stop appearing.

The profile feeds into the User Preference scoring factor (5 points).

### Layer 2: Booking Confirmation

New Discord command: `/booked <deal_number>` and a "Booked it!" button on deal embeds.

Logs which deals the user actually committed to. Bookings weighted 5x more than thumbs-up in the preference model — a like is cheap, a booking is real signal.

After 3+ bookings, deals matching booking patterns get a "Your type of deal" tag.

### Layer 3: Price Trend Intelligence

Built on the existing `price_history` table.

- **Route averages**: After 4+ data points per route, compute rolling 4-week average price.
- **Drop detection**: Flag any price >15% below its rolling average as a "price drop alert."
- **Seasonal patterns**: After 8+ weeks of data, detect recurring patterns (e.g., "flights to Miami cheapest 3 weeks out").
- **Proactive alerts**: When a watched destination drops below average, DM immediately — don't wait for next scheduled scan.

## 5. Watch Lists + Scan Scheduling

### Passive Scanning (automatic, background)

Schedule:
- **1 API-powered full scan per day** (morning, when prices update)
- **3 additional scraper-fallback scans per day** (every 6 hours)
- Only DMs the user when something meaningful changed:
  - New deal scoring 70+ not in previous run
  - Price dropped >15% on a previously seen deal
  - A watched destination has new availability
- Silent runs produce no DMs (no spam)

### Active Watching (user-triggered)

New Discord commands:
- `/watch <city> [date]` — Add to high-frequency watch list (checked 3x/day via API)
- `/unwatch <city>` — Remove from watch list
- `/watchlist` — Show all active watches with last check times

Maximum 5 active watches to stay within API free tiers.

### Quota Budgeting

Monthly budget: 2,000 Amadeus + 3,000 Kiwi + 100 Serpapi

| Activity | Amadeus calls/day | Notes |
|----------|------------------|-------|
| 1 full API scan (top 15 destinations, 2 weekends) | ~45 | 30 flight + 15 hotel (shares Amadeus quota) |
| Watch checks (5 cities x 3/day) | ~15 | Flights only |
| **Daily total** | ~60 | Fits within 66/day (2,000/30) |

Kiwi used as fallback only when Amadeus fails. Serpapi reserved for cross-validation of top 10 deals during the daily API scan.

`orchestrator/quota_manager.py` tracks all API calls in SQLite with daily/monthly counters and automatically routes to scraper fallback when approaching limits.

## 6. Discord Bot Enhancements

### New Commands

| Command | Description |
|---------|-------------|
| `/watch <city> [date]` | Add city to high-frequency watch list (max 5) |
| `/unwatch <city>` | Remove from watch list |
| `/watchlist` | Show active watches with last check times |
| `/booked <deal_number>` | Mark deal as booked — feeds preference learning |
| `/preferences` | Show learned preference profile |
| `/preferences reset` | Wipe preference data |

### Modified Commands

| Command | Change |
|---------|--------|
| `/deals` | Returns 20-30 deals (up from 8-10), shows confidence badges, adds reaction buttons |
| `/dealstatus` | Enhanced — shows quota usage, next scan time, watch count |

### Deal Embed Enhancements

Each deal DM includes:
- Price confidence indicator (green/yellow/red dot + label)
- Booking deep link button (when available from API)
- Thumbs up / Thumbs down / Booked it reaction buttons
- "Your type of deal" tag when matching booking history
- Price trend: "↓ $40 below 4-week avg" or "→ typical price"

### Notification Behavior

- **Scheduled scans**: Only DM when something meaningful changed
- **`/deals` command**: Always DMs full results (user explicitly asked)
- **Watch alerts**: DM immediately on price drops for watched cities

## 7. New Files

| File | Purpose |
|------|---------|
| `apis/__init__.py` | Package init |
| `apis/amadeus.py` | Amadeus flight + hotel API client |
| `apis/kiwi.py` | Kiwi.com Tequila API client |
| `apis/serpapi_flights.py` | Serpapi Google Flights API client |
| `orchestrator/reconciler.py` | Cross-source price validation + confidence scoring |
| `orchestrator/quota_manager.py` | Tracks API call counts, decides API vs scraper |
| `orchestrator/source_router.py` | Fallback chain logic |
| `orchestrator/preference_engine.py` | Feedback, booking history, trends, preference profile |
| `orchestrator/scheduler_smart.py` | Quota-aware scan scheduling |

## 8. Modified Files

| File | Change |
|------|--------|
| `orchestrator/pipeline.py` | Use source router instead of direct agent calls, add reconciler, preference boost |
| `orchestrator/deal_scorer.py` | Soft scoring with timing penalties, confidence factor, preference factor |
| `agents/flight_agent.py` | Accept data from APIs or scrapers interchangeably |
| `agents/hotel_agent.py` | Same |
| `notifications/local_dashboard.py` | Confidence badges, booking links, trend indicators |
| `notifications/live_dashboard.py` | Same + filter by confidence level |
| `config/settings.py` | Add API key env vars (AMADEUS_API_KEY, etc.) |
| `config/constraints.json` | Add soft constraint floors alongside existing hard constraints |
| `zrbot/commands/deals.py` | Reaction buttons, watch commands, booking command, preference commands |

## 9. Database Schema Additions

### preferences.db

```sql
-- Reaction feedback
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_hash TEXT NOT NULL,
    destination TEXT,
    transport_type TEXT,
    airline TEXT,
    price_range TEXT,
    hotel_type TEXT,
    score REAL,
    reaction TEXT NOT NULL,  -- 'thumbs_up', 'thumbs_down', 'booked'
    timestamp TEXT NOT NULL
);

-- Watch list
CREATE TABLE watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination TEXT NOT NULL,
    specific_date TEXT,  -- NULL = all weekends
    added_at TEXT NOT NULL,
    last_checked_at TEXT,
    last_price REAL
);

-- Learned preference profile (recomputed from feedback)
CREATE TABLE preference_profile (
    key TEXT PRIMARY KEY,  -- e.g., 'dest:Washington DC', 'airline:Spirit', 'transport:train'
    weight REAL,           -- positive = preferred, negative = avoided
    sample_count INTEGER,
    updated_at TEXT
);
```

### deals.db additions

```sql
-- API quota tracking
CREATE TABLE quota_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_name TEXT NOT NULL,    -- 'amadeus', 'kiwi', 'serpapi'
    call_date TEXT NOT NULL,   -- 'YYYY-MM-DD'
    call_count INTEGER DEFAULT 0,
    UNIQUE(api_name, call_date)
);
```

## 10. Configuration Changes

### config/constraints.json additions

```json
{
  "soft_floors": {
    "min_friday_depart": "12:00",
    "max_saturday_depart": "12:00",
    "max_sunday_arrive": "23:59",
    "max_total_usd": 800,
    "min_hours_at_dest": 12
  }
}
```

### config/settings.py additions

```python
AMADEUS_API_KEY = os.getenv("AMADEUS_API_KEY", "")
AMADEUS_API_SECRET = os.getenv("AMADEUS_API_SECRET", "")
KIWI_API_KEY = os.getenv("KIWI_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
```

All optional. System degrades gracefully to scraper-only if no API keys configured.
