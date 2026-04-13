"""Rate limiter — adds polite delays between scraper requests to avoid IP bans."""

import asyncio
import random
import time


class RateLimiter:
    """Enforce minimum delays between requests to the same domain."""

    def __init__(self, min_delay: float = 3.0, max_delay: float = 7.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_request: dict[str, float] = {}

    async def wait(self, domain: str) -> None:
        """Wait until enough time has passed since the last request to this domain."""
        now = time.monotonic()
        last = self._last_request.get(domain, 0)
        delay = random.uniform(self.min_delay, self.max_delay)
        elapsed = now - last
        if elapsed < delay:
            wait_time = delay - elapsed
            print(f"[rate_limiter] Waiting {wait_time:.1f}s before hitting {domain}")
            await asyncio.sleep(wait_time)
        self._last_request[domain] = time.monotonic()


# Global instance shared across agents
limiter = RateLimiter()
