"""Train agent — scrapes Amtrak and SEPTA, uses LLM to extract structured data."""

from datetime import date, datetime, timedelta

import scrapers.amtrak as amtrak
import scrapers.septa as septa
from utils.json_extractor import extract_json
from utils.llm import call_llm
from utils.rate_limiter import limiter

SYSTEM_PROMPT = (
    "You are a train journey extraction agent. Extract all visible "
    "train options from the given search results or fare information. "
    "Return ONLY a valid JSON array of train journey objects. "
    "No markdown, no preamble, no explanation."
)

TRAIN_SOURCES = [
    ("amtrak", amtrak),
    ("septa", septa),
]


class TrainAgent:
    """Search for train options (Amtrak + SEPTA) as alternatives to flights."""

    def __init__(self, constraints: dict):
        self.constraints = constraints
        self.results: list[dict] = []

    def get_weekend_pairs(self, num_weekends: int = 6) -> list[tuple[str, str]]:
        """Return (outbound, return) date-string pairs for the next N weekends."""
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

    async def scrape_and_parse(
        self,
        origin_city: str,
        dest_city: str,
        outbound_date: str,
        return_date: str,
    ) -> list[dict]:
        """Fetch train data from all sources and extract structured results."""
        all_trains: list[dict] = []

        for source_name, source_module in TRAIN_SOURCES:
            await limiter.wait(source_name)
            try:
                raw = await source_module.fetch_raw(origin_city, dest_city, outbound_date, return_date)
            except Exception as exc:
                print(f"[TrainAgent] {source_name} scrape failed for {dest_city}: {exc}")
                continue

            if not raw:
                continue

            user_prompt = (
                f"Extract every train option from this {source_name} search results text.\n"
                f"Origin: Philadelphia, Destination: {dest_city}\n"
                f"Outbound date: {outbound_date}, Return date: {return_date}\n\n"
                f"For each train journey return a JSON object with these exact keys:\n"
                f"  price_usd (number, round-trip price as integer),\n"
                f"  operator (string, e.g. \"Amtrak\" or \"SEPTA\"),\n"
                f"  outbound_depart (string, 24-hour format like \"17:30\" — NEVER use AM/PM),\n"
                f"  outbound_arrive (string, 24-hour format like \"20:15\" — NEVER use AM/PM),\n"
                f"  return_depart (string, 24-hour format like \"17:00\" — NEVER use AM/PM),\n"
                f"  return_arrive (string, 24-hour format like \"19:30\" — NEVER use AM/PM),\n"
                f"  stops (number, 0 if direct/express),\n"
                f"  duration_mins (number, one-way duration in minutes),\n"
                f"  destination (\"{dest_city}\"),\n"
                f"  outbound_date (\"{outbound_date}\"), return_date (\"{return_date}\")\n\n"
                f"IMPORTANT: All times MUST be in 24-hour HH:MM format.\n"
                f"If multiple fare tiers exist, include the cheapest option.\n"
                f"If this is a fixed fare (like SEPTA), create one entry with typical weekend times.\n\n"
                f"Page text (trimmed):\n{raw[:3500]}"
            )

            try:
                response = call_llm(SYSTEM_PROMPT, user_prompt)
                parsed = extract_json(response)
                if isinstance(parsed, dict):
                    parsed = [parsed]
                if isinstance(parsed, list):
                    for t in parsed:
                        if isinstance(t, dict):
                            t["source"] = source_name
                            t["transport_type"] = "train"
                            # Map operator to airline field for compatibility
                            t["airline"] = t.get("operator", source_name.title())
                            # Map stops to layovers for scorer compatibility
                            t["layovers"] = t.get("stops", 0)
                            t["is_nonstop"] = t.get("stops", 0) == 0
                            all_trains.append(t)
            except Exception as exc:
                print(f"[TrainAgent] LLM parse failed for {source_name}/{dest_city}: {exc}")

        return all_trains

    def passes_constraints(self, train: dict) -> bool:
        """Return True if the train meets budget and timing constraints."""
        required = ["price_usd", "outbound_depart", "outbound_date", "return_arrive"]
        if any(k not in train for k in required):
            return False

        c = self.constraints
        max_price = c.get("budget", {}).get("max_train_roundtrip",
                    c.get("budget", {}).get("max_flight_roundtrip", 300))

        if train["price_usd"] > max_price:
            return False

        # Timing: same windows as flights but trains can leave a bit earlier
        # (no airport security overhead)
        depart = train["outbound_depart"]
        day_of_week = datetime.strptime(train["outbound_date"], "%Y-%m-%d").strftime("%A")

        if day_of_week == "Friday" and depart < "16:00":  # Trains: 16:00 vs flights 17:00
            return False
        if day_of_week == "Saturday" and depart > "10:00":  # Trains: 10:00 vs flights 09:00
            return False

        if train.get("return_arrive", "23:59") > "23:00":  # Trains: 23:00 vs flights 22:00
            return False

        hours = self.calc_hours_at_destination(train)
        min_hours = c.get("timing", {}).get("min_hours_at_destination", 24)
        if hours < min_hours:
            return False

        return True

    def calc_hours_at_destination(self, train: dict) -> float:
        """Calculate hours between arrival and return departure."""
        try:
            arrive = datetime.strptime(
                f"{train['outbound_date']} {train['outbound_arrive']}", "%Y-%m-%d %H:%M"
            )
            depart = datetime.strptime(
                f"{train['return_date']} {train['return_depart']}", "%Y-%m-%d %H:%M"
            )
            return (depart - arrive).total_seconds() / 3600
        except (KeyError, ValueError, TypeError):
            return 0.0

    async def run(self, destinations: list[dict]) -> list[dict]:
        """Search train options for all destinations across upcoming weekends."""
        pairs = self.get_weekend_pairs()
        seen: set[str] = set()
        valid: list[dict] = []

        for dest in destinations:
            city = dest["city"]
            # Check if this city is reachable by train
            if not amtrak.get_station_code(city) and not septa.get_septa_info(city):
                continue

            for outbound, ret in pairs:
                print(f"[TrainAgent] Checking {city} {outbound}...")
                trains = await self.scrape_and_parse("Philadelphia", city, outbound, ret)
                for t in trains:
                    if not self.passes_constraints(t):
                        continue
                    dedup_key = f"{t.get('operator', t.get('airline', ''))}-{t.get('price_usd')}-{t.get('outbound_date')}-{t.get('destination', city)}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    t["hours_at_destination"] = self.calc_hours_at_destination(t)
                    # Ensure destination field is set
                    t.setdefault("destination", city)
                    t.setdefault("iata", dest.get("iata", ""))
                    valid.append(t)

        valid.sort(key=lambda t: t.get("price_usd", 9999))
        print(f"[TrainAgent] {len(valid)} valid train options found")
        return valid
