"""Airbnb scraper — fetches accommodation search results page text via Playwright."""

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
    """Construct an Airbnb search URL for the given city and dates."""
    return (
        f"https://www.airbnb.com/s/{city}/homes"
        f"?checkin={checkin}&checkout={checkout}"
        f"&adults=1&price_max=200&sort_by=price_low_to_high"
    )


async def fetch_raw(city: str, checkin: str, checkout: str) -> str:
    """Launch a headless browser, navigate to Airbnb, and return body text.

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
                print(f"[airbnb] WARNING: navigation timed out for {url}")
                return ""

            await asyncio.sleep(5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

            text = await page.inner_text("body")

            blockers = ("captcha", "verify", "access denied", "robot",
                        "something went wrong")
            if any(kw in text.lower() for kw in blockers):
                print(f"[airbnb] WARNING: anti-bot page detected for {city}")
                return ""

            return text

        finally:
            if browser:
                await browser.close()
