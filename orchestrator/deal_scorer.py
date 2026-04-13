"""Deal scorer — assigns a composite 0-100 score to each deal."""


def score_deal(deal: dict, constraints: dict) -> float:
    """Return a 0.0–100.0 composite score for the given deal bundle.

    Scores trains and flights using the same formula but with transport-aware
    budget caps. Trains get a small bonus for convenience (no airport overhead).
    Returns 0.0 if any required key is missing rather than crashing.
    """
    try:
        total_trip_cost = deal["total_trip_cost"]
        layovers = deal["layovers"]
        best_stay = deal["best_stay"]
        return_arrive = deal["return_arrive"]
        is_train = deal.get("transport_type") == "train"

        max_transport = (
            constraints["budget"].get("max_train_roundtrip", 200) if is_train
            else constraints["budget"]["max_flight_roundtrip"]
        )
        max_hotel = constraints["budget"]["max_hotel_per_night_usd"]

        # PRICE SCORE (40 points)
        budget_cap = max_transport + (max_hotel * 2)
        price_ratio = total_trip_cost / budget_cap
        price_score = max(0, 40 * (1 - price_ratio))

        # NONSTOP / DIRECT SCORE (20 points)
        # Trains: stops are less penalizing (no disembarking/rebooking)
        if layovers == 0:
            nonstop_score = 20
        elif layovers == 1:
            nonstop_score = 15 if is_train else 10
        elif layovers == 2 and is_train:
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
        # Trains arrive at 30th St Station (no baggage claim), so tighter buffer is fine
        max_arrive = 23.0 if is_train else 22.0
        buffer = max(0, max_arrive - arrive_hour)
        buffer_score = min(10, buffer * 2.5)

        # TRAIN CONVENIENCE BONUS (up to 5 extra points, capped at 100 total)
        # No airport security, city center departure, more legroom
        convenience_bonus = 5 if is_train else 0

        raw = price_score + nonstop_score + hotel_score + time_score + buffer_score + convenience_bonus
        return round(min(100.0, raw), 1)

    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 0.0
