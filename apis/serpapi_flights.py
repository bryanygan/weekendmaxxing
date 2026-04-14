"""Serpapi Google Flights client for flight search."""

import requests

from orchestrator.quota_manager import has_quota, record_api_call

_SEARCH_URL = "https://serpapi.com/search"
API_NAME = "serpapi"


def _fmt_time(time_str: str) -> str:
    """Extract HH:MM from a datetime string like '2026-04-17 18:00'."""
    try:
        parts = time_str.strip().split(" ")
        return parts[1][:5] if len(parts) > 1 else parts[0][:5]
    except (TypeError, IndexError, AttributeError):
        return ""


class SerpApiClient:
    """Client for the Serpapi Google Flights search engine."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search_flights(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str,
    ) -> list[dict]:
        """Search round-trip flights and return a normalised list of dicts."""
        if not self.api_key:
            return []

        if not has_quota(API_NAME):
            return []

        try:
            resp = requests.get(
                _SEARCH_URL,
                params={
                    "engine": "google_flights",
                    "departure_id": origin,
                    "arrival_id": destination,
                    "outbound_date": depart_date,
                    "return_date": return_date,
                    "currency": "USD",
                    "hl": "en",
                    "api_key": self.api_key,
                },
                timeout=15,
            )
        except Exception:
            return []

        if resp.status_code != 200:
            return []

        record_api_call(API_NAME)
        data = resp.json()
        raw_flights = data.get("best_flights", []) + data.get("other_flights", [])

        results = []
        for offer in raw_flights:
            try:
                price_usd = offer["price"]
                flights = offer.get("flights", [])
                layovers = offer.get("layovers", [])
                total_duration = offer.get("total_duration", 0)

                out_dep = flights[0]["departure_airport"]["time"] if flights else ""
                out_arr = flights[-1]["arrival_airport"]["time"] if flights else ""
                airline = flights[0].get("airline", "") if flights else ""

                results.append({
                    "price_usd": price_usd,
                    "airline": airline,
                    "outbound_depart": _fmt_time(out_dep),
                    "outbound_arrive": _fmt_time(out_arr),
                    "return_depart": "",
                    "return_arrive": "",
                    "layovers": len(layovers),
                    "duration_mins": total_duration,
                    "is_nonstop": len(layovers) == 0,
                    "destination": destination,
                    "iata": destination,
                    "outbound_date": depart_date,
                    "return_date": return_date,
                    "source": API_NAME,
                    "booking_link": None,
                    "price_confidence": "high",
                })
            except (KeyError, IndexError, ValueError, TypeError):
                continue

        return results
