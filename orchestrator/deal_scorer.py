"""Deal scorer — assigns a composite 0-100 score to each deal."""

from datetime import datetime


def _parse_hour(time_str: str) -> float:
    """Parse HH:MM string to float hours."""
    parts = time_str.split(":")
    return int(parts[0]) + int(parts[1]) / 60


def _timing_fit_score(outbound_date: str, outbound_depart: str) -> float:
    """Return 0-10 points based on how well departure timing fits ideal weekend window."""
    try:
        date = datetime.strptime(outbound_date, "%Y-%m-%d")
        day_of_week = date.strftime("%A")  # Monday, Tuesday, etc.
        hour = _parse_hour(outbound_depart)
    except (ValueError, AttributeError):
        return 0.0

    if day_of_week == "Friday":
        if hour >= 17.0:
            return 10.0
        elif hour >= 16.0:
            return 8.0
        elif hour >= 15.0:
            return 6.0
        elif hour >= 14.0:
            return 4.0
        elif hour >= 13.0:
            return 2.0
        elif hour >= 12.0:
            return 1.0
        else:
            return 0.0
    elif day_of_week == "Saturday":
        if hour < 9.0:
            return 10.0
        elif hour < 10.0:
            return 7.0
        elif hour < 11.0:
            return 4.0
        elif hour < 12.0:
            return 2.0
        else:
            return 0.0
    else:
        return 0.0


def score_deal(deal: dict, constraints: dict) -> float:
    """Return a 0.0–100.0 composite score for the given deal bundle.

    Uses a soft scoring formula where bad timing lowers the score rather than
    rejecting the deal outright. Absolute floors still return 0.0.
    Returns 0.0 if any required key is missing rather than crashing.
    """
    try:
        total_trip_cost = deal["total_trip_cost"]
        layovers = deal["layovers"]
        best_stay = deal["best_stay"]
        return_arrive = deal["return_arrive"]
        outbound_depart = deal["outbound_depart"]
        outbound_date = deal["outbound_date"]

        is_train = deal.get("transport_type") == "train"

        # ── ABSOLUTE FLOORS ──────────────────────────────────────────────────
        # Check departure day/time floors
        try:
            date = datetime.strptime(outbound_date, "%Y-%m-%d")
            day_of_week = date.strftime("%A")
            depart_hour = _parse_hour(outbound_depart)
        except (ValueError, AttributeError):
            return 0.0

        # Friday before noon = floor
        if day_of_week == "Friday" and depart_hour < 12.0:
            return 0.0
        # Saturday after noon = floor
        if day_of_week == "Saturday" and depart_hour > 12.0:
            return 0.0

        # Return after midnight Sunday
        return_hour = _parse_hour(return_arrive)
        if return_arrive > "23:59":
            return 0.0

        # Over budget absolute cap
        if total_trip_cost > 800:
            return 0.0

        # Too few hours at destination
        hours = deal.get("hours_at_destination", 24)
        if hours < 12:
            return 0.0

        # ── SCORING FORMULA ──────────────────────────────────────────────────

        max_transport = (
            constraints["budget"].get("max_train_roundtrip", 200) if is_train
            else constraints["budget"]["max_flight_roundtrip"]
        )
        max_hotel = constraints["budget"]["max_hotel_per_night_usd"]

        # PRICE SCORE (35 points)
        budget_cap = max_transport + (max_hotel * 2)
        price_score = max(0.0, 35.0 * (1 - total_trip_cost / budget_cap))

        # NONSTOP / DIRECT SCORE (15 points)
        if layovers == 0:
            nonstop_score = 15.0
        elif layovers == 1:
            nonstop_score = 12.0 if is_train else 10.0
        else:
            nonstop_score = 3.0

        # HOTEL QUALITY SCORE (15 points)
        rating = best_stay.get("rating", 3.0)
        hotel_score = (rating / 5.0) * 15.0

        # TIME AT DESTINATION SCORE (10 points)
        time_score = min(10.0, (hours / 48.0) * 10.0)

        # RETURN BUFFER SCORE (5 points)
        arrive_hour = _parse_hour(return_arrive)
        max_arrive = 23.0 if is_train else 22.0
        buffer_score = min(5.0, max(0.0, (max_arrive - arrive_hour) * 1.5))

        # TIMING FIT SCORE (10 points)
        timing_score = _timing_fit_score(outbound_date, outbound_depart)

        # PRICE CONFIDENCE SCORE (5 points)
        confidence = deal.get("price_confidence", "missing")
        confidence_map = {"high": 5.0, "medium": 3.0, "low": 1.0}
        confidence_score = confidence_map.get(confidence, 1.0)

        # USER PREFERENCE SCORE (5 points)
        preference_score = min(5.0, deal.get("preference_boost", 0))

        # TRAIN BONUS (+5, capped at 100)
        train_bonus = 5.0 if is_train else 0.0

        raw = (
            price_score
            + nonstop_score
            + hotel_score
            + time_score
            + buffer_score
            + timing_score
            + confidence_score
            + preference_score
            + train_bonus
        )
        return round(min(100.0, raw), 1)

    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 0.0
