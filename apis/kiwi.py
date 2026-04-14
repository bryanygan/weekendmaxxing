"""Kiwi.com Tequila API client for flight search."""

from datetime import datetime

import requests

from orchestrator.quota_manager import has_quota, record_api_call

_SEARCH_URL = "https://api.tequila.kiwi.com/v2/search"
API_NAME = "kiwi"


def _fmt_time(iso_str: str) -> str:
    """Extract HH:MM from an ISO-like datetime string."""
    try:
        # Handles '2026-04-17T18:00:00.000Z' and similar
        dt = iso_str.replace("Z", "").split(".")[0]
        return dt[11:16]
    except (TypeError, IndexError):
        return ""


def _to_kiwi_date(yyyy_mm_dd: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY for the Kiwi API."""
    try:
        d = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return yyyy_mm_dd


class KiwiClient:
    """Client for the Kiwi.com Tequila flight search API."""

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
        if not has_quota(API_NAME):
            return []

        date_from = _to_kiwi_date(depart_date)
        date_to = _to_kiwi_date(depart_date)
        return_from = _to_kiwi_date(return_date)
        return_to = _to_kiwi_date(return_date)

        try:
            resp = requests.get(
                _SEARCH_URL,
                headers={"apikey": self.api_key},
                params={
                    "fly_from": origin,
                    "fly_to": destination,
                    "date_from": date_from,
                    "date_to": date_to,
                    "return_from": return_from,
                    "return_to": return_to,
                    "flight_type": "round",
                    "curr": "USD",
                    "limit": 10,
                },
                timeout=15,
            )
        except Exception:
            return []

        if resp.status_code != 200:
            return []

        record_api_call(API_NAME)
        results = []
        for item in resp.json().get("data", []):
            try:
                price_usd = item["price"]
                airlines = item.get("airlines", [])
                airline = airlines[0] if airlines else ""
                route = item.get("route", [])
                booking_link = item.get("deep_link")

                # Split outbound vs return legs
                # Outbound: legs going from origin to destination
                # Return: legs going back
                out_legs = [s for s in route if s.get("flyFrom") != destination]
                ret_legs = [s for s in route if s.get("flyFrom") == destination]

                # Fallback: split in half if heuristic fails
                if not out_legs or not ret_legs:
                    mid = len(route) // 2
                    out_legs = route[:mid] if mid else route[:1]
                    ret_legs = route[mid:] if mid else route[1:]

                out_dep = out_legs[0].get("local_departure", "") if out_legs else ""
                out_arr = out_legs[-1].get("local_arrival", "") if out_legs else ""
                ret_dep = ret_legs[0].get("local_departure", "") if ret_legs else ""
                ret_arr = ret_legs[-1].get("local_arrival", "") if ret_legs else ""

                layovers = (len(out_legs) - 1) + (len(ret_legs) - 1)
                duration_info = item.get("duration", {})
                duration_mins = (
                    duration_info.get("departure", 0) // 60
                    + duration_info.get("return", 0) // 60
                )

                results.append({
                    "price_usd": price_usd,
                    "airline": airline,
                    "outbound_depart": _fmt_time(out_dep),
                    "outbound_arrive": _fmt_time(out_arr),
                    "return_depart": _fmt_time(ret_dep),
                    "return_arrive": _fmt_time(ret_arr),
                    "layovers": layovers,
                    "duration_mins": duration_mins,
                    "is_nonstop": layovers == 0,
                    "destination": destination,
                    "iata": destination,
                    "outbound_date": depart_date,
                    "return_date": return_date,
                    "source": API_NAME,
                    "booking_link": booking_link,
                    "price_confidence": "high",
                })
            except (KeyError, IndexError, ValueError, TypeError):
                continue

        return results
