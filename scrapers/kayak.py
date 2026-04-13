"""Kayak scraper — fetches flight search results page text via Playwright."""

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


def build_url(origin: str, dest_iata: str, outbound_date: str, return_date: str) -> str:
    """Construct a Kayak flight search URL."""
    return (
        f"https://www.kayak.com/flights/{origin}-{dest_iata}"
        f"/{outbound_date}/{return_date}?sort=price_a"
    )


async def fetch_raw(origin: str, dest_iata: str, outbound_date: str, return_date: str) -> str:
    """Launch a headless browser, navigate to Kayak, and return body text.

    Returns an empty string on anti-bot detection or navigation timeout.
    """
    url = build_url(origin, dest_iata, outbound_date, return_date)
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
                print(f"[kayak] WARNING: navigation timed out for {url}")
                return ""

            # Kayak is JS-heavy, needs longer wait
            await asyncio.sleep(6)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

            text = await page.inner_text("body")

            blockers = ("complete a security check", "captcha", "verify you are a human",
                        "access denied", "please wait")
            if any(kw in text.lower() for kw in blockers):
                print(f"[kayak] WARNING: anti-bot page detected for {dest_iata}")
                return ""

            return text

        finally:
            if browser:
                await browser.close()
