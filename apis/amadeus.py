"""Amadeus Self-Service API client for flights and hotels."""

import re
import time
from typing import Optional

import requests

from orchestrator.quota_manager import has_quota, record_api_call

_TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
_FLIGHT_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
_HOTEL_URL = "https://test.api.amadeus.com/v2/shopping/hotel-offers"

API_NAME = "amadeus"


def _parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration like PT1H25M into total minutes."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration_str or "")
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def _fmt_time(iso_str: str) -> str:
    """Extract HH:MM from an ISO datetime string like 2026-04-17T18:00:00."""
    try:
        return iso_str[11:16]
    except (TypeError, IndexError):
        return ""


class AmadeusClient:
    """Client for the Amadeus Self-Service flight and hotel APIs."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _get_token(self) -> Optional[str]:
        """Obtain an OAuth2 bearer token, caching until expiry."""
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token

        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.api_secret,
            },
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        self._token = data.get("access_token")
        expires_in = data.get("expires_in", 1799)
        self._token_expires_at = now + expires_in - 60  # 60-s safety margin
        return self._token

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

        token = self._get_token()
        if not token:
            return []

        try:
            resp = requests.get(
                _FLIGHT_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "originLocationCode": origin,
                    "destinationLocationCode": destination,
                    "departureDate": depart_date,
                    "returnDate": return_date,
                    "adults": 1,
                    "currencyCode": "USD",
                    "max": 10,
                },
                timeout=15,
            )
        except Exception:
            return []

        if resp.status_code != 200:
            return []

        record_api_call(API_NAME)
        results = []
        for offer in resp.json().get("data", []):
            try:
                price_usd = float(offer["price"]["total"])
                itin = offer.get("itineraries", [])
                out_segs = itin[0]["segments"] if len(itin) > 0 else []
                ret_segs = itin[1]["segments"] if len(itin) > 1 else []

                out_dep = out_segs[0]["departure"]["at"] if out_segs else ""
                out_arr = out_segs[-1]["arrival"]["at"] if out_segs else ""
                ret_dep = ret_segs[0]["departure"]["at"] if ret_segs else ""
                ret_arr = ret_segs[-1]["arrival"]["at"] if ret_segs else ""

                airline = out_segs[0].get("carrierCode", "") if out_segs else ""
                layovers = (len(out_segs) - 1) + (len(ret_segs) - 1)
                out_dur = sum(_parse_iso_duration(s.get("duration", "")) for s in out_segs)
                ret_dur = sum(_parse_iso_duration(s.get("duration", "")) for s in ret_segs)
                duration_mins = out_dur + ret_dur

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
                    "booking_link": None,
                    "price_confidence": "high",
                })
            except (KeyError, IndexError, ValueError, TypeError):
                continue

        return results

    def search_hotels(
        self,
        city_code: str,
        checkin: str,
        checkout: str,
    ) -> list[dict]:
        """Search hotels and return a normalised list of dicts."""
        if not has_quota(API_NAME):
            return []

        token = self._get_token()
        if not token:
            return []

        try:
            resp = requests.get(
                _HOTEL_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "cityCode": city_code,
                    "checkInDate": checkin,
                    "checkOutDate": checkout,
                    "adults": 1,
                    "currency": "USD",
                    "bestRateOnly": True,
                },
                timeout=15,
            )
        except Exception:
            return []

        if resp.status_code != 200:
            return []

        record_api_call(API_NAME)

        # Compute number of nights for per-night price
        try:
            from datetime import date
            d1 = date.fromisoformat(checkin)
            d2 = date.fromisoformat(checkout)
            nights = max((d2 - d1).days, 1)
        except ValueError:
            nights = 1

        results = []
        for item in resp.json().get("data", []):
            try:
                hotel = item.get("hotel", {})
                offers = item.get("offers", [])
                if not offers:
                    continue
                total_price = float(offers[0]["price"]["total"])
                results.append({
                    "name": hotel.get("name", ""),
                    "price_per_night": round(total_price / nights, 2),
                    "total_price": total_price,
                    "rating": hotel.get("rating", ""),
                    "review_count": None,
                    "type": "hotel",
                    "neighborhood": hotel.get("address", {}).get("cityName", ""),
                    "source": API_NAME,
                })
            except (KeyError, IndexError, ValueError, TypeError):
                continue

        return results
