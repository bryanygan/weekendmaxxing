"""Skyscanner scraper — fetches flight search results page text via Playwright."""

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
    """Construct a Skyscanner flight search URL.

    Skyscanner uses YYMMDD format in URLs.
    """
    out_compact = outbound_date.replace("-", "")[2:]  # "2026-04-17" -> "260417"
    ret_compact = return_date.replace("-", "")[2:]
    return (
        f"https://www.skyscanner.com/transport/flights/{origin.lower()}/{dest_iata.lower()}"
        f"/{out_compact}/{ret_compact}/?adultsv2=1&cabinclass=economy&sortby=price"
    )


async def fetch_raw(origin: str, dest_iata: str, outbound_date: str, return_date: str) -> str:
    """Launch a headless browser, navigate to Skyscanner, and return body text.

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
                print(f"[skyscanner] WARNING: navigation timed out for {url}")
                return ""

            await asyncio.sleep(5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

            text = await page.inner_text("body")

            blockers = ("captcha", "verify you're not a robot", "access denied",
                        "security check", "blocked")
            if any(kw in text.lower() for kw in blockers):
                print(f"[skyscanner] WARNING: anti-bot page detected for {dest_iata}")
                return ""

            return text

        finally:
            if browser:
                await browser.close()
