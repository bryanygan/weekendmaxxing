"""Hotel agent — scrapes Booking.com and Airbnb, uses LLM to extract structured data."""

import scrapers.airbnb as airbnb
import scrapers.booking as booking
from utils.json_extractor import extract_json
from utils.llm import call_llm
from utils.rate_limiter import limiter

SYSTEM_PROMPT = (
    "You are a hotel listing extraction agent. Extract all visible "
    "accommodation listings from the page text. Return ONLY a valid JSON "
    "array. No markdown, no preamble."
)

STAY_SOURCES = [
    ("booking.com", booking),
    ("airbnb", airbnb),
]


class HotelAgent:
    """Search for hotel and Airbnb options that meet rating and budget requirements."""

    def __init__(self, constraints: dict):
        self.constraints = constraints

    async def scrape_and_parse(self, city: str, checkin: str, checkout: str, source: str) -> list[dict]:
        """Fetch raw page text from a single source, extract structured data via LLM, filter and normalize."""
        # Determine which module to use
        source_module = None
        for name, mod in STAY_SOURCES:
            if name == source:
                source_module = mod
                break
        if source_module is None:
            source_module = booking  # fallback

        await limiter.wait(source)
        try:
            raw = await source_module.fetch_raw(city, checkin, checkout)
        except Exception as exc:
            print(f"[HotelAgent] {source} scrape failed for {city}: {exc}")
            return []

        if not raw:
            return []

        user_prompt = (
            f"Extract every accommodation listing from this {source} search results text.\n"
            f"City: {city}, Check-in: {checkin}, Check-out: {checkout}\n\n"
            f"For each listing return a JSON object with these exact keys:\n"
            f"  name (string),\n"
            f"  price_per_night (number, USD, just the number like 89),\n"
            f"  total_price (number, USD, total for the stay like 178),\n"
            f"  rating (number, on a 5.0 scale — just the number like 4.5, NOT \"4.5/5\"),\n"
            f"  review_count (number),\n"
            f'  type ("hotel" | "hostel" | "apartment" | "other"),\n'
            f"  neighborhood (string or null),\n"
            f"  source (\"{source}\")\n\n"
            f"IMPORTANT: All number fields must be plain numbers, NOT strings.\n"
            f"Rating must be a single number on a 5-point scale (e.g. 4.2, not \"4.2/5\").\n\n"
            f"Page text (trimmed):\n{raw[:3500]}"
        )

        try:
            response = call_llm(SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            print(f"[HotelAgent] LLM failed for {source}/{city}: {exc}")
            return []

        parsed = extract_json(response)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            return []

        min_rating = self.constraints.get("hotel_min_rating", 3.5)
        results = []
        for hotel in parsed:
            if not isinstance(hotel, dict):
                continue
            # Normalize 10-point ratings to 5-point
            rating = hotel.get("rating", 0)
            if isinstance(rating, (int, float)) and rating > 5:
                rating = rating / 2
                hotel["rating"] = rating
            # Filter
            total = hotel.get("total_price", 0)
            if not isinstance(total, (int, float)) or total <= 0:
                continue
            if not isinstance(rating, (int, float)) or rating < min_rating:
                continue
            results.append(hotel)

        return results

    async def run(self, flight_deals: list[dict]) -> list[dict]:
        """For each flight deal, find matching hotels/Airbnbs and enrich the deal dict."""
        enriched = []

        for deal in flight_deals:
            city = deal.get("destination", deal.get("iata", ""))
            checkin = deal.get("outbound_date", "")
            checkout = deal.get("return_date", "")

            # Search all accommodation sources
            all_stays: list[dict] = []
            for source_name, _ in STAY_SOURCES:
                stays = await self.scrape_and_parse(city, checkin, checkout, source_name)
                all_stays.extend(stays)

            if not all_stays:
                print(f"[HotelAgent] No stays for {city} {checkin}, skipping")
                continue

            # Sort by rating desc, then total_price asc
            all_stays.sort(key=lambda h: (-h.get("rating", 0), h.get("total_price", 9999)))

            deal["best_stay"] = all_stays[0]
            deal["all_stays"] = all_stays[:5]
            deal["hotel_search_performed"] = True
            deal["total_trip_cost"] = deal.get("price_usd", 0) + all_stays[0].get("total_price", 0)
            enriched.append(deal)

        return enriched
