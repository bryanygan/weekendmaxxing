"""SEPTA Regional Rail scraper — fetches schedule/fare info via Playwright."""

import asyncio

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]

# SEPTA regional rail destinations from Philadelphia (short trips, <2 hours)
# These connect to Amtrak hubs or are destinations themselves
SEPTA_DESTINATIONS = {
    "Trenton": {"zone": 4, "peak_fare": 10.00, "off_peak_fare": 7.25, "duration_min": 60},
    "Newark": {"zone": "NJT", "peak_fare": 15.75, "off_peak_fare": 11.25, "duration_min": 80},
    "Wilmington": {"zone": "DART", "peak_fare": 10.00, "off_peak_fare": 7.25, "duration_min": 45},
    "Doylestown": {"zone": 5, "peak_fare": 11.25, "off_peak_fare": 8.00, "duration_min": 70},
    "Norristown": {"zone": 3, "peak_fare": 7.25, "off_peak_fare": 5.50, "duration_min": 35},
    "Lansdale": {"zone": 4, "peak_fare": 10.00, "off_peak_fare": 7.25, "duration_min": 45},
    "West Chester": {"zone": 4, "peak_fare": 10.00, "off_peak_fare": 7.25, "duration_min": 50},
}


def get_septa_info(city: str) -> dict | None:
    """Return SEPTA fare/schedule info for a city, or None if not served."""
    for name, info in SEPTA_DESTINATIONS.items():
        if name.lower() in city.lower() or city.lower() in name.lower():
            return {"station": name, **info}
    return None


def build_url(origin: str, destination: str, date: str) -> str:
    """Construct a SEPTA trip planner URL."""
    return (
        f"https://www.septa.org/schedules/rail/"
        f"?orig={origin}&dest={destination}&date={date}"
    )


async def fetch_raw(origin_city: str, dest_city: str, outbound_date: str, return_date: str) -> str:
    """Fetch SEPTA schedule information.

    For SEPTA, we use a hybrid approach: known fare data for regional rail
    (SEPTA publishes fixed zone-based fares) combined with schedule scraping.
    Returns structured text that the LLM can parse, or fare info directly.
    """
    info = get_septa_info(dest_city)
    if not info:
        return ""

    # SEPTA has fixed zone fares — we can return structured text directly
    # without needing to scrape (fares are published and stable)
    station = info["station"]
    peak = info["peak_fare"]
    off_peak = info["off_peak_fare"]
    duration = info["duration_min"]
    roundtrip_peak = peak * 2
    roundtrip_off_peak = off_peak * 2

    # Build a structured text blob that the LLM can parse
    text = (
        f"SEPTA Regional Rail Schedule - Philadelphia to {station}\n"
        f"Route: Philadelphia 30th Street Station → {station}\n"
        f"Duration: approximately {duration} minutes each way\n"
        f"Fares (one-way):\n"
        f"  Peak (weekday rush): ${peak:.2f}\n"
        f"  Off-Peak (weekends, holidays): ${off_peak:.2f}\n"
        f"Round-trip fares:\n"
        f"  Peak round-trip: ${roundtrip_peak:.2f}\n"
        f"  Off-Peak round-trip: ${roundtrip_off_peak:.2f}\n"
        f"Weekend service: Trains run approximately every 60 minutes on weekends\n"
        f"First train Saturday: approximately 06:00\n"
        f"Last train Sunday: approximately 23:00\n"
        f"Outbound date: {outbound_date}\n"
        f"Return date: {return_date}\n"
        f"Stops: 0 (direct service)\n"
        f"Operator: SEPTA Regional Rail\n"
    )

    # Also try scraping the real schedule page for more specific times
    browser = None
    url = build_url("30th+Street+Station", station.replace(" ", "+"), outbound_date)

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
                schedule_text = await page.inner_text("body")
                text += f"\n\nSchedule details:\n{schedule_text[:2000]}"
            except (PlaywrightTimeout, Exception) as exc:
                print(f"[septa] Schedule scrape failed for {station}: {exc}")
                # Still return the fare info we have

        finally:
            if browser:
                await browser.close()

    return text
