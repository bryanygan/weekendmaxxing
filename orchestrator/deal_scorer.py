"""Deal scorer — assigns a composite 0-100 score to each deal."""


def score_deal(deal: dict, constraints: dict) -> float:
    """Return a 0.0–100.0 composite score for the given deal bundle.

    Returns 0.0 if any required key is missing rather than crashing.
    """
    try:
        # Extract required values
        total_trip_cost = deal["total_trip_cost"]
        layovers = deal["layovers"]
        best_stay = deal["best_stay"]
        return_arrive = deal["return_arrive"]

        max_flight = constraints["budget"]["max_flight_roundtrip"]
        max_hotel = constraints["budget"]["max_hotel_per_night_usd"]

        # PRICE SCORE (40 points)
        budget_cap = max_flight + (max_hotel * 2)
        price_ratio = total_trip_cost / budget_cap
        price_score = max(0, 40 * (1 - price_ratio))

        # NONSTOP SCORE (20 points)
        if layovers == 0:
            nonstop_score = 20
        elif layovers == 1:
            nonstop_score = 10
        else:
            nonstop_score = 0

        # HOTEL QUALITY SCORE (20 points)
        rating = best_stay.get("rating", 3.0)
        hotel_score = (rating / 5.0) * 20

        # TIME AT DESTINATION SCORE (10 points)
        hours = deal.get("hours_at_destination", 24)
        time_score = min(10, (hours / 48) * 10)

        # RETURN BUFFER SCORE (10 points)
        parts = return_arrive.split(":")
        arrive_hour = int(parts[0]) + int(parts[1]) / 60
        buffer = max(0, 22.0 - arrive_hour)
        buffer_score = min(10, buffer * 2.5)

        return round(price_score + nonstop_score + hotel_score + time_score + buffer_score, 1)

    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 0.0
