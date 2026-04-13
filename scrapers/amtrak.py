"""Amtrak scraper — fetches train search results page text via Playwright."""

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

# Amtrak station codes for cities reachable from Philadelphia (30th St Station = PHL)
STATION_CODES = {
    "Philadelphia": "PHL",
    "New York": "NYP",       # Penn Station
    "Washington DC": "WAS",  # Union Station
    "Boston": "BOS",         # South Station
    "Baltimore": "BAL",      # Penn Station
    "Pittsburgh": "PGH",     # Union Station
    "Harrisburg": "HAR",
    "Newark": "NWK",
    "Wilmington": "WIL",
    "Richmond": "RVR",
    "Norfolk": "NFK",
    "Raleigh": "RGH",
    "Charlotte": "CLT",
    "Savannah": "SAV",
    "Charleston": "CHS",
    "Albany": "ALB",
    "Providence": "PVD",
    "New Haven": "NHV",
    "Trenton": "TRE",
    "Lancaster": "LNC",
}


def get_station_code(city: str) -> str | None:
    """Return the Amtrak station code for a city, or None if not served."""
    for name, code in STATION_CODES.items():
        if name.lower() in city.lower() or city.lower() in name.lower():
            return code
    return None


def build_url(origin_code: str, dest_code: str, outbound_date: str, return_date: str) -> str:
    """Construct an Amtrak search URL.

    Dates should be MM/DD/YYYY for Amtrak's URL format.
    """
    # Convert YYYY-MM-DD to MM/DD/YYYY
    parts = outbound_date.split("-")
    out_fmt = f"{parts[1]}%2F{parts[2]}%2F{parts[0]}"
    parts_r = return_date.split("-")
    ret_fmt = f"{parts_r[1]}%2F{parts_r[2]}%2F{parts_r[0]}"

    return (
        f"https://www.amtrak.com/tickets/departure.html"
        f"?journeyOrigin={origin_code}&journeyDestination={dest_code}"
        f"&journeyDepartDate={out_fmt}&journeyReturnDate={ret_fmt}"
        f"&numOfAdults=1&sortby=price"
    )


async def fetch_raw(origin_city: str, dest_city: str, outbound_date: str, return_date: str) -> str:
    """Launch a headless browser, navigate to Amtrak, and return body text.

    Returns an empty string on anti-bot detection, timeout, or if route not served.
    """
    origin_code = get_station_code(origin_city)
    dest_code = get_station_code(dest_city)
    if not origin_code or not dest_code:
        print(f"[amtrak] No station code for {origin_city} or {dest_city}, skipping")
        return ""

    url = build_url(origin_code, dest_code, outbound_date, return_date)
    browser = None

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=STEALTH_ARGS,
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except PlaywrightTimeout:
                print(f"[amtrak] WARNING: navigation timed out for {dest_city}")
                return ""

            # Amtrak's site is JS-heavy, needs longer render time
            await asyncio.sleep(8)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

            text = await page.inner_text("body")

            blockers = ("captcha", "access denied", "unusual activity",
                        "verify you are human", "please wait")
            if any(kw in text.lower() for kw in blockers):
                print(f"[amtrak] WARNING: anti-bot page detected for {dest_city}")
                return ""

            return text

        finally:
            if browser:
                await browser.close()
