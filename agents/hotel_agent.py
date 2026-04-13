"""Hotel agent — scrapes Booking.com and uses LLM to extract structured data."""

from scrapers.booking import fetch_raw
from utils.json_extractor import extract_json
from utils.llm import call_llm

SYSTEM_PROMPT = (
    "You are a hotel listing extraction agent. Extract all visible "
    "accommodation listings from the page text. Return ONLY a valid JSON "
    "array. No markdown, no preamble."
)


class HotelAgent:
    """Search for hotel options that meet rating and budget requirements."""

    def __init__(self, constraints: dict):
        self.constraints = constraints

    async def scrape_and_parse(self, city: str, checkin: str, checkout: str, source: str) -> list[dict]:
        """Fetch raw hotel page text, extract structured data via LLM, filter and normalize."""
        raw = await fetch_raw(city, checkin, checkout)
        if not raw:
            return []

        user_prompt = (
            f"Extract every accommodation listing from this search results text.\n"
            f"City: {city}, Check-in: {checkin}, Check-out: {checkout}\n\n"
            f"For each listing return a JSON object with these exact keys:\n"
            f"  name (string), price_per_night (number, USD), total_price (number, USD),\n"
            f"  rating (number, normalize to 5.0 scale), review_count (number),\n"
            f'  type ("hotel" | "hostel" | "apartment" | "other"),\n'
            f"  neighborhood (string or null), source (\"{source}\")\n\n"
            f"Page text (trimmed):\n{raw[:3500]}"
        )

        response = call_llm(SYSTEM_PROMPT, user_prompt)
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
        """For each flight deal, find matching hotels and enrich the deal dict."""
        enriched = []

        for deal in flight_deals:
            city = deal.get("destination", deal.get("iata", ""))
            checkin = deal.get("outbound_date", "")
            checkout = deal.get("return_date", "")

            stays = await self.scrape_and_parse(city, checkin, checkout, "booking.com")

            if not stays:
                print(f"[HotelAgent] No stays for {city} {checkin}, skipping")
                continue

            # Sort by rating desc, then total_price asc
            stays.sort(key=lambda h: (-h.get("rating", 0), h.get("total_price", 9999)))

            deal["best_stay"] = stays[0]
            deal["all_stays"] = stays[:5]
            deal["hotel_search_performed"] = True
            deal["total_trip_cost"] = deal.get("price_usd", 0) + stays[0].get("total_price", 0)
            enriched.append(deal)

        return enriched
