"""Flight agent — scrapes Google Flights and uses LLM to extract structured data."""

from datetime import date, datetime, timedelta

from scrapers.google_flights import fetch_raw
from utils.json_extractor import extract_json
from utils.llm import call_llm

SYSTEM_PROMPT = (
    "You are a flight data extraction agent. Extract all visible "
    "flight options from the given search results page text. Return ONLY a valid "
    "JSON array of flight objects. No markdown, no preamble, no explanation."
)


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
        # Find the next Friday (weekday 4)
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
        """Fetch raw flight page text and use the LLM to extract structured data."""
        raw = await fetch_raw(origin, dest_iata, outbound_date, return_date)
        if not raw:
            return []

        user_prompt = (
            f"Extract every flight option from this search results text.\n"
            f"Destination city: {dest_city}, IATA: {dest_iata}\n"
            f"Outbound date: {outbound_date}, Return date: {return_date}\n\n"
            f"For each flight return a JSON object with these exact keys:\n"
            f"  price_usd (number), airline (string), outbound_depart (HH:MM),\n"
            f"  outbound_arrive (HH:MM), return_depart (HH:MM), return_arrive (HH:MM),\n"
            f"  layovers (number, 0 if nonstop), duration_mins (number),\n"
            f"  is_nonstop (bool), destination (string), iata (string),\n"
            f"  outbound_date (string), return_date (string)\n\n"
            f"Page text (trimmed):\n{raw[:3500]}"
        )

        response = call_llm(SYSTEM_PROMPT, user_prompt)
        parsed = extract_json(response)
        if isinstance(parsed, list):
            return parsed
        return [parsed] if isinstance(parsed, dict) else []

    # ── constraint checking ─────────────────────────────────────────────────

    def passes_constraints(self, flight: dict) -> bool:
        """Return True if the flight meets all budget, timing, and layover constraints."""
        required = [
            "price_usd", "layovers", "outbound_depart", "outbound_date",
            "return_arrive",
        ]
        if any(k not in flight for k in required):
            return False

        c = self.constraints

        # Budget
        if flight["price_usd"] > c["budget"]["max_flight_roundtrip"]:
            return False

        # Layovers
        if flight["layovers"] > c["preferences"]["max_layovers"]:
            return False

        # Outbound timing
        depart = flight["outbound_depart"]
        day_of_week = datetime.strptime(flight["outbound_date"], "%Y-%m-%d").strftime("%A")

        if day_of_week == "Friday" and depart < "17:00":
            return False
        if day_of_week == "Saturday" and depart > "09:00":
            return False

        # Return timing
        if flight["return_arrive"] > "22:00":
            return False

        # Hours at destination
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
