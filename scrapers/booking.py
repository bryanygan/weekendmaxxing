"""Booking.com scraper — fetches hotel search results page text via Playwright."""

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


def build_url(city: str, checkin: str, checkout: str) -> str:
    """Construct a Booking.com search URL for the given city and dates."""
    return (
        f"https://www.booking.com/searchresults.html"
        f"?ss={city}&checkin={checkin}&checkout={checkout}"
        f"&group_adults=1&no_rooms=1&order=price"
    )


async def fetch_raw(city: str, checkin: str, checkout: str) -> str:
    """Launch a headless browser, navigate to Booking.com, and return body text.

    Returns an empty string on anti-bot detection or navigation timeout.
    """
    url = build_url(city, checkin, checkout)
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
                print(f"[booking] WARNING: navigation timed out for {url}")
                return ""

            await asyncio.sleep(4)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

            text = await page.inner_text("body")

            if any(kw in text.lower() for kw in ("access denied", "are you a robot", "captcha")):
                print(f"[booking] WARNING: anti-bot page detected for {city}")
                return ""

            return text

        finally:
            if browser:
                await browser.close()
