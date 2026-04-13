"""Recommendation agent — generates weekend itinerary suggestions via LLM."""

from datetime import datetime

from utils.llm import call_llm

SYSTEM_PROMPT = (
    "You are a weekend travel guide. Be specific, practical, and concise. "
    "Focus on what is actually achievable in the time given."
)


class RecommendationAgent:
    """Generate human-readable weekend trip recommendations for scored deals."""

    def generate(self, deal: dict) -> dict:
        """Add LLM-generated recommendations to a single deal dict."""
        city = deal.get("destination", deal.get("iata", "Unknown"))
        arrive_time = deal.get("outbound_arrive", "evening")
        depart_time = deal.get("return_depart", "evening")
        hours = deal.get("hours_at_destination", 24)

        try:
            outbound_day = datetime.strptime(
                deal.get("outbound_date", ""), "%Y-%m-%d"
            ).strftime("%A")
        except (ValueError, TypeError):
            outbound_day = "Friday"

        user_prompt = (
            f"I'm flying into {city} and arriving around {arrive_time} on {outbound_day}. "
            f"I need to depart at {depart_time} on Sunday. I have ~{hours:.0f} hours total.\n\n"
            f"Give me exactly:\n"
            f"1. TOP 3 ACTIVITIES (name, ~time needed, ~cost in USD)\n"
            f"2. BEST NEIGHBORHOOD TO STAY (1 sentence why)\n"
            f"3. 2 RESTAURANTS (one budget under $20, one mid-range $30-60, with cuisine type)\n"
            f"4. ONE PRO TIP specific to this city for a short trip\n\n"
            f"Be realistic — if I only have 24 hours, don't suggest 6 things."
        )

        response = call_llm(SYSTEM_PROMPT, user_prompt)
        deal["recommendations"] = response
        deal["recommendations_city"] = city
        return deal

    def generate_batch(self, deals: list[dict]) -> list[dict]:
        """Generate recommendations for each deal, handling errors gracefully."""
        for deal in deals:
            try:
                self.generate(deal)
            except Exception as exc:
                print(f"[RecommendationAgent] WARNING: failed for {deal.get('destination')}: {exc}")
                deal["recommendations"] = "Could not generate recommendations."
                deal["recommendations_city"] = deal.get("destination", "Unknown")
        return deals
