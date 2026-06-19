"""Human-like browser behaviour to avoid LinkedIn automation detection.

Ported from the working linkedin-agent. All functions accept a Playwright page
object and introduce realistic delays, scrolling, and typing patterns.
"""

from __future__ import annotations

import random
import time

# ─── Timing configs ──────────────────────────────────────────────────────────
READING_TIME = (4, 12)
BETWEEN_JOBS = (10, 25)
BETWEEN_SEARCHES = (15, 40)
SCROLL_PAUSE = (1.5, 4)
TYPING_DELAY = (0.03, 0.12)  # seconds per character
FEED_BREAK_CHANCE = 0.25
FEED_BREAK_DURATION = (30, 90)


def human_pause(lo: float, hi: float) -> None:
    """Sleep a random duration like a human would."""
    time.sleep(random.uniform(lo, hi))


def human_scroll(page, times: int | None = None) -> None:
    """Scroll like a person reading -- variable speed, sometimes back up."""
    if times is None:
        times = random.randint(2, 5)
    for _ in range(times):
        px = random.randint(150, 500)
        # 15% chance to scroll back up a bit
        if random.random() < 0.15:
            px = -random.randint(50, 200)
        page.evaluate(f"window.scrollBy(0, {px})")
        human_pause(*SCROLL_PAUSE)


def human_scroll_job_list(page, times: int | None = None) -> None:
    """Scroll the LinkedIn job sidebar list."""
    if times is None:
        times = random.randint(2, 4)
    for _ in range(times):
        px = random.randint(200, 600)
        page.evaluate(
            f'var l=document.querySelector(".jobs-search-results-list,.scaffold-layout__list");'
            f"if(l)l.scrollBy(0,{px})"
        )
        human_pause(*SCROLL_PAUSE)


def browse_feed(page) -> None:
    """Take a break -- go to LinkedIn feed, scroll around, come back."""
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
    human_pause(5, 10)
    human_scroll(page, random.randint(3, 8))
    human_pause(*FEED_BREAK_DURATION)
    # Scroll a bit more like casually reading
    human_scroll(page, random.randint(1, 3))


def slow_type(page, element, text: str) -> None:
    """Type text character by character with random delays, like a human."""
    element.click()
    element.fill("")  # clear existing
    for ch in text:
        element.type(ch, delay=0)
        time.sleep(random.uniform(*TYPING_DELAY))


def check_rate_limit(page) -> bool:
    """Check if LinkedIn is showing rate limit or security check signals."""
    try:
        text = page.evaluate("document.body ? document.body.textContent.substring(0, 5000) : ''")
    except Exception:
        return False
    if not text:
        return False
    lower = text.lower()
    if "429" in text or "rate limit" in lower or "let's do a quick security check" in lower:
        return True
    return False
