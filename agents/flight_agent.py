"""Flight agent — scrapes multiple flight sources and uses LLM to extract structured data."""

from datetime import date, datetime, timedelta

import scrapers.google_flights as google_flights
import scrapers.kayak as kayak
import scrapers.skyscanner as skyscanner
from utils.json_extractor import extract_json
from utils.llm import call_llm
from utils.rate_limiter import limiter

SYSTEM_PROMPT = (
    "You are a flight data extraction agent. Extract all visible "
    "flight options from the given search results page text. Return ONLY a valid "
    "JSON array of flight objects. No markdown, no preamble, no explanation."
)

# Scrapers to try in order — if one gets blocked, we still get data from others
FLIGHT_SOURCES = [
    ("google_flights", google_flights),
    ("kayak", kayak),
    ("skyscanner", skyscanner),
]


class FlightAgent:
    """Search for round-trip flights that fit weekend timing and budget constraints."""

    def __init__(self, constraints: dict):
        self.constraints = constraints
        self.results: list[dict] = []

    # ── date helpers ────────────────────────────────────────────────────────

    def get_weekend_pairs(self, num_weekends: int = 6) -> list[tuple[str, str]]:
        """Return (outbound, return) date-string pairs for the next N weekends.

        Each weekend produces two pairs: one departing Friday, one Saturday.
        Return day is always the following Sunday. Past dates are excluded.
        """
        today = date.today()
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0 and today.weekday() == 4:
            next_friday = today
        else:
            next_friday = today + timedelta(days=days_until_friday or 7)

        pairs: list[tuple[str, str]] = []
        for i in range(num_weekends):
            friday = next_friday + timedelta(weeks=i)
            saturday = friday + timedelta(days=1)
            sunday = friday + timedelta(days=2)

            if friday >= today:
                pairs.append((friday.isoformat(), sunday.isoformat()))
            if saturday >= today:
                pairs.append((saturday.isoformat(), sunday.isoformat()))

        return pairs

    # ── scrape + LLM parse ──────────────────────────────────────────────────

    async def scrape_and_parse(
        self,
        origin: str,
        dest_city: str,
        dest_iata: str,
        outbound_date: str,
        return_date: str,
    ) -> list[dict]:
        """Fetch raw flight page text from multiple sources and extract structured data."""
        all_flights: list[dict] = []

        for source_name, source_module in FLIGHT_SOURCES:
            await limiter.wait(source_name)
            try:
                raw = await source_module.fetch_raw(origin, dest_iata, outbound_date, return_date)
            except Exception as exc:
                print(f"[FlightAgent] {source_name} scrape failed for {dest_iata}: {exc}")
                continue

            if not raw:
                continue

            user_prompt = (
                f"Extract every flight option from this {source_name} search results text.\n"
                f"Destination city: {dest_city}, IATA: {dest_iata}\n"
                f"Outbound date: {outbound_date}, Return date: {return_date}\n\n"
                f"For each flight return a JSON object with these exact keys:\n"
                f"  price_usd (number, round trip price as integer),\n"
                f"  airline (string),\n"
                f"  outbound_depart (string, 24-hour format like \"18:30\" — NEVER use AM/PM),\n"
                f"  outbound_arrive (string, 24-hour format like \"20:15\" — NEVER use AM/PM),\n"
                f"  return_depart (string, 24-hour format like \"17:00\" — NEVER use AM/PM),\n"
                f"  return_arrive (string, 24-hour format like \"19:30\" — NEVER use AM/PM),\n"
                f"  layovers (number, 0 if nonstop), duration_mins (number),\n"
                f"  is_nonstop (bool),\n"
                f"  destination (\"{dest_city}\"), iata (\"{dest_iata}\"),\n"
                f"  outbound_date (\"{outbound_date}\"), return_date (\"{return_date}\")\n\n"
                f"IMPORTANT: All times MUST be in 24-hour HH:MM format. Convert any AM/PM times.\n"
                f"Example: 6:00 PM becomes \"18:00\", 7:25 AM becomes \"07:25\".\n\n"
                f"Page text (trimmed):\n{raw[:3500]}"
            )

            try:
                response = call_llm(SYSTEM_PROMPT, user_prompt)
                parsed = extract_json(response)
                if isinstance(parsed, dict):
                    parsed = [parsed]
                if isinstance(parsed, list):
                    for f in parsed:
                        if isinstance(f, dict):
                            f["source"] = source_name
                            all_flights.append(f)
            except Exception as exc:
                print(f"[FlightAgent] LLM parse failed for {source_name}/{dest_iata}: {exc}")

        return all_flights

    # ── constraint checking ─────────────────────────────────────────────────

    def passes_constraints(self, flight: dict) -> bool:
        """Return True if the flight meets all budget, timing, and layover constraints."""
        required = [
            "price_usd", "layovers", "outbound_depart", "outbound_date",
            "return_arrive",
        ]
        if any(k not in flight or not flight[k] for k in required):
            return False

        c = self.constraints

        try:
            price = float(flight["price_usd"])
        except (ValueError, TypeError):
            return False
        if price > c["budget"]["max_flight_roundtrip"]:
            return False

        try:
            layovers = int(flight["layovers"])
        except (ValueError, TypeError):
            return False
        if layovers > c["preferences"]["max_layovers"]:
            return False

        depart = str(flight["outbound_depart"])
        try:
            day_of_week = datetime.strptime(str(flight["outbound_date"]), "%Y-%m-%d").strftime("%A")
        except (ValueError, TypeError):
            return False

        if day_of_week == "Friday" and depart < "17:00":
            return False
        if day_of_week == "Saturday" and depart > "09:00":
            return False

        if flight["return_arrive"] > "22:00":
            return False

        hours = self.calc_hours_at_destination(flight)
        if hours < c["timing"]["min_hours_at_destination"]:
            return False

        return True

    # ── time-at-destination ─────────────────────────────────────────────────

    def calc_hours_at_destination(self, flight: dict) -> float:
        """Calculate hours between arrival at destination and return departure."""
        try:
            arrive = datetime.strptime(
                f"{flight['outbound_date']} {flight['outbound_arrive']}", "%Y-%m-%d %H:%M"
            )
            depart = datetime.strptime(
                f"{flight['return_date']} {flight['return_depart']}", "%Y-%m-%d %H:%M"
            )
            return (depart - arrive).total_seconds() / 3600
        except (KeyError, ValueError, TypeError):
            return 0.0

    # ── main entry point ────────────────────────────────────────────────────

    async def run(self, destinations: list[dict]) -> list[dict]:
        """Search all destinations across all upcoming weekends and return filtered results."""
        pairs = self.get_weekend_pairs()
        seen: set[str] = set()
        valid: list[dict] = []

        for dest in destinations:
            city = dest["city"]
            iata = dest["iata"]
            for outbound, ret in pairs:
                print(f"[FlightAgent] Checking {city} {outbound}...")
                flights = await self.scrape_and_parse("PHL", city, iata, outbound, ret)
                for f in flights:
                    if not self.passes_constraints(f):
                        continue
                    dedup_key = f"{f.get('airline')}-{f.get('price_usd')}-{f.get('outbound_date')}-{f.get('destination', city)}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    f["hours_at_destination"] = self.calc_hours_at_destination(f)
                    valid.append(f)

        valid.sort(key=lambda f: f.get("price_usd", 9999))
        print(f"[FlightAgent] {len(valid)} valid flights found")
        return valid
