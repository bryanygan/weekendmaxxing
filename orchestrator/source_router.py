"""Source router — tries APIs first, falls back to scrapers + LLM extraction."""

import asyncio
import logging
from typing import Optional

from config import settings
from apis.amadeus import AmadeusClient
from apis.kiwi import KiwiClient
from apis.serpapi_flights import SerpApiClient
from utils.llm import call_llm
from utils.json_extractor import extract_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client factories — return None when the required API key is not configured
# ---------------------------------------------------------------------------

def _get_amadeus_client() -> Optional[AmadeusClient]:
    """Return an AmadeusClient if both key and secret are configured, else None."""
    if settings.AMADEUS_API_KEY and settings.AMADEUS_API_SECRET:
        return AmadeusClient(settings.AMADEUS_API_KEY, settings.AMADEUS_API_SECRET)
    return None


def _get_kiwi_client() -> Optional[KiwiClient]:
    """Return a KiwiClient if the API key is configured, else None."""
    if settings.KIWI_API_KEY:
        return KiwiClient(settings.KIWI_API_KEY)
    return None


def _get_serpapi_client() -> Optional[SerpApiClient]:
    """Return a SerpApiClient if the API key is configured, else None."""
    if settings.SERPAPI_API_KEY:
        return SerpApiClient(settings.SERPAPI_API_KEY)
    return None


# ---------------------------------------------------------------------------
# Scraper fallback helpers
# ---------------------------------------------------------------------------

def _scraper_fetch_flights(
    origin: str,
    dest_iata: str,
    depart_date: str,
    return_date: str,
) -> list[dict]:
    """Fetch flights via Playwright scrapers and parse with LLM.

    Tries Google Flights then Kayak. Marks results with price_confidence='low'.
    Returns [] if all scrapers fail or LLM extraction yields nothing.
    """
    from scrapers import google_flights as gf_scraper
    from scrapers import kayak as kayak_scraper

    raw = ""

    # Try Google Flights first
    try:
        raw = asyncio.run(gf_scraper.fetch_raw(origin, dest_iata, depart_date, return_date))
    except Exception as exc:
        logger.warning("[source_router] google_flights scraper error: %s", exc)

    # Fall back to Kayak if Google Flights returned nothing
    if not raw:
        try:
            raw = asyncio.run(kayak_scraper.fetch_raw(origin, dest_iata, depart_date, return_date))
        except Exception as exc:
            logger.warning("[source_router] kayak scraper error: %s", exc)

    if not raw:
        return []

    system_prompt = (
        "You are a flight data extraction assistant. "
        "Extract flight offers from the raw page text below and return a JSON array. "
        "Each element must have: price_usd (number), airline (string), "
        "outbound_depart (HH:MM), outbound_arrive (HH:MM), "
        "return_depart (HH:MM), return_arrive (HH:MM), "
        "layovers (int), is_nonstop (bool), source (string, e.g. 'google_flights'). "
        "Return [] if no flights are found."
    )
    user_prompt = f"Extract flights from this page text:\n\n{raw[:6000]}"

    try:
        llm_output = call_llm(system_prompt, user_prompt)
        results = extract_json(llm_output)
    except Exception as exc:
        logger.warning("[source_router] LLM extraction failed for flights: %s", exc)
        return []

    if not isinstance(results, list):
        return []

    # Stamp low confidence and fill missing fields
    for item in results:
        item.setdefault("price_confidence", "low")
        item.setdefault("destination", dest_iata)
        item.setdefault("iata", dest_iata)
        item.setdefault("outbound_date", depart_date)
        item.setdefault("return_date", return_date)
        item.setdefault("booking_link", None)
        item["price_confidence"] = "low"

    return results


def _scraper_fetch_hotels(
    city: str,
    checkin: str,
    checkout: str,
) -> list[dict]:
    """Fetch hotels via Playwright scraper (Booking.com) and parse with LLM.

    Marks results with price_confidence='low'.
    Returns [] if scraper fails or LLM extraction yields nothing.
    """
    from scrapers import booking as booking_scraper

    raw = ""
    try:
        raw = asyncio.run(booking_scraper.fetch_raw(city, checkin, checkout))
    except Exception as exc:
        logger.warning("[source_router] booking scraper error: %s", exc)

    if not raw:
        return []

    system_prompt = (
        "You are a hotel data extraction assistant. "
        "Extract hotel listings from the raw page text below and return a JSON array. "
        "Each element must have: name (string), price_per_night (number), "
        "total_price (number), rating (string or number), type ('hotel'), "
        "neighborhood (string), source ('booking.com'). "
        "Return [] if no hotels are found."
    )
    user_prompt = f"Extract hotels from this page text:\n\n{raw[:6000]}"

    try:
        llm_output = call_llm(system_prompt, user_prompt)
        results = extract_json(llm_output)
    except Exception as exc:
        logger.warning("[source_router] LLM extraction failed for hotels: %s", exc)
        return []

    if not isinstance(results, list):
        return []

    for item in results:
        item.setdefault("price_confidence", "low")
        item["price_confidence"] = "low"

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_flights(
    origin: str,
    dest_iata: str,
    depart_date: str,
    return_date: str,
) -> list[dict]:
    """Fetch flights using API-first strategy with scraper fallback.

    Order: Amadeus -> Kiwi -> SerpApi -> scrapers (Google Flights / Kayak + LLM).
    Returns results from the first source that yields at least one result.
    """
    # --- Amadeus ---
    amadeus = _get_amadeus_client()
    if amadeus is not None:
        try:
            results = amadeus.search_flights(origin, dest_iata, depart_date, return_date)
            if results:
                return results
        except Exception as exc:
            logger.warning("[source_router] Amadeus search_flights failed: %s", exc)

    # --- Kiwi ---
    kiwi = _get_kiwi_client()
    if kiwi is not None:
        try:
            results = kiwi.search_flights(origin, dest_iata, depart_date, return_date)
            if results:
                return results
        except Exception as exc:
            logger.warning("[source_router] Kiwi search_flights failed: %s", exc)

    # --- SerpApi ---
    serpapi = _get_serpapi_client()
    if serpapi is not None:
        try:
            results = serpapi.search_flights(origin, dest_iata, depart_date, return_date)
            if results:
                return results
        except Exception as exc:
            logger.warning("[source_router] SerpApi search_flights failed: %s", exc)

    # --- Scraper fallback ---
    return _scraper_fetch_flights(origin, dest_iata, depart_date, return_date)


def fetch_hotels(
    city_code: str,
    city_name: str,
    checkin: str,
    checkout: str,
) -> list[dict]:
    """Fetch hotels using API-first strategy with scraper fallback.

    Order: Amadeus hotels -> scraper (Booking.com + LLM).
    Returns results from the first source that yields at least one result.
    """
    # --- Amadeus ---
    amadeus = _get_amadeus_client()
    if amadeus is not None:
        try:
            results = amadeus.search_hotels(city_code, checkin, checkout)
            if results:
                return results
        except Exception as exc:
            logger.warning("[source_router] Amadeus search_hotels failed: %s", exc)

    # --- Scraper fallback ---
    return _scraper_fetch_hotels(city_name, checkin, checkout)
