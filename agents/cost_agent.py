"""Cost agent — estimates total trip costs including transit, food, and activities."""

from utils.json_extractor import extract_json
from utils.llm import call_llm

SYSTEM_PROMPT = (
    "You are a travel cost estimator. Always respond with ONLY valid JSON. "
    "No markdown, no explanation."
)

DEFAULTS = {
    "airport_transit_one_way": 15,
    "rideshare_one_way": 35,
    "daily_food_budget_low": 40,
    "daily_food_budget_mid": 65,
    "avg_activity_cost": 25,
    "public_transit_day_pass": 10,
}

CLAMP_RANGES = {
    "airport_transit_one_way": (2, 100),
    "rideshare_one_way": (10, 120),
    "daily_food_budget_low": (20, 100),
    "daily_food_budget_mid": (40, 150),
    "avg_activity_cost": (0, 200),
    "public_transit_day_pass": (0, 100),
}


class CostAgent:
    """Aggregate flight, hotel, and incidental costs into a total trip estimate."""

    def estimate_transit(self, city: str) -> dict:
        """Use LLM to estimate transit, food, and activity costs for a city."""
        user_prompt = (
            f"For a weekend trip to {city} from a major US airport, estimate costs "
            f"in USD as a JSON object with these exact keys:\n"
            f"airport_transit_one_way (cheapest public transit option, number),\n"
            f"rideshare_one_way (Uber/Lyft estimate, number),\n"
            f"daily_food_budget_low (number), daily_food_budget_mid (number),\n"
            f"avg_activity_cost (one typical paid activity, number),\n"
            f"public_transit_day_pass (number or null if city has no good transit)"
        )

        try:
            response = call_llm(SYSTEM_PROMPT, user_prompt)
            parsed = extract_json(response)
        except Exception:
            parsed = None

        if not isinstance(parsed, dict) or not all(k in parsed for k in DEFAULTS):
            return dict(DEFAULTS)

        # Clamp values
        for key, (lo, hi) in CLAMP_RANGES.items():
            val = parsed.get(key)
            if val is None or not isinstance(val, (int, float)):
                parsed[key] = DEFAULTS[key]
            else:
                parsed[key] = max(lo, min(hi, val))

        return parsed

    def compute_full_budget(self, deal: dict) -> dict:
        """Add transit estimates and total estimated cost to the deal dict."""
        city = deal.get("destination", deal.get("iata", ""))
        transit = self.estimate_transit(city)

        extras = (
            transit["airport_transit_one_way"] * 2
            + transit["daily_food_budget_mid"] * 2
            + transit["avg_activity_cost"]
        )

        deal["transit_estimates"] = transit
        deal["estimated_extras"] = round(extras, 2)
        deal["estimated_total"] = round(deal.get("total_trip_cost", 0) + extras, 2)
        return deal
