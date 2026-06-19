"""LinkedIn job search through the user's existing logged-in Chrome session."""

from __future__ import annotations

import json
import logging
import platform
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from ..config import load_preferences
from ..human import BETWEEN_SEARCHES, FEED_BREAK_CHANCE, human_pause
from ..models import Job
from ..search_plan import SearchPlanItem, build_search_plan, is_profile_aligned

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchQuery:
    keyword: str
    remote_only: bool = False
    time_filter: str = "r604800"
    location: str = ""


DEFAULT_SEARCHES: list[SearchQuery] = []


_EXTRACT_CARDS_JS = """
(function() {
    var cards = document.querySelectorAll(
        ".scaffold-layout__list-item, li.ember-view.occludable-update"
    );
    var results = [];
    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var titleEl = card.querySelector(
            "a.job-card-container__link, a.job-card-list__title--link, a[class*='job-card']"
        );
        var companyEl = card.querySelector(
            ".artdeco-entity-lockup__subtitle, .job-card-container__primary-description"
        );
        var locationEl = card.querySelector(
            ".artdeco-entity-lockup__caption, .job-card-container__metadata-item"
        );
        var title = titleEl ? titleEl.textContent.trim().replace(/\\s+/g, " ").substring(0, 120) : "";
        var href = titleEl ? titleEl.href : "";
        var company = companyEl ? companyEl.textContent.trim().replace(/\\s+/g, " ").substring(0, 100) : "";
        var location = locationEl ? locationEl.textContent.trim().replace(/\\s+/g, " ").substring(0, 100) : "";
        var isEasy = card.textContent.indexOf("Easy Apply") > -1;
        if (title) {
            results.push({
                title: title,
                company: company,
                location: location,
                easy_apply: isEasy,
                url: href
            });
        }
    }
    return JSON.stringify(results);
})()
"""


class LinkedInSearcher:
    """Search LinkedIn using the user's existing Google Chrome app/profile."""

    def __init__(self, workspace: Path, browser_profile_path: Path | None = None):
        self.workspace = workspace
        self.browser_profile = browser_profile_path

    def search(self, queries: list[SearchQuery] | None = None) -> list[Job]:
        if platform.system() != "Darwin":
            raise SystemExit("LinkedIn active-Chrome search currently requires macOS.")
        if queries is None:
            try:
                queries = [query_from_plan(item) for item in build_search_plan(self.workspace)]
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

        preferences = load_preferences(self.workspace)
        found_jobs: list[Job] = []
        seen_keys: set[str] = set()

        for qi, query in enumerate(queries):
            if self._rate_limited():
                wait = random.uniform(300, 600)
                logger.warning("Rate limit detected, waiting %.0f seconds...", wait)
                time.sleep(wait)
                if self._rate_limited():
                    logger.error("Still rate-limited, stopping search.")
                    break

            url = self._build_url(query)
            tag = "remote" if query.remote_only else "any"
            logger.info("[%d/%d] Searching: '%s' (%s)", qi + 1, len(queries), query.keyword, tag)

            opened = self._open_url_in_existing_chrome(url)
            if not opened.startswith("http"):
                raise SystemExit(opened)

            card_count = self._wait_for_cards()
            if card_count == 0:
                logger.info("No results for '%s', skipping.", query.keyword)
                human_pause(5, 15)
                continue

            self._scroll_job_list(random.randint(2, 5))
            human_pause(2, 4)

            cards = self._extract_cards()
            new_count = 0
            for card in cards:
                job = Job.from_dict(card, source="linkedin-search")
                if not is_profile_aligned(job, preferences):
                    logger.info("Filtered off-profile result: %s", job.title)
                    continue
                key = (card["title"][:50] + card["company"][:30]).lower()
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                found_jobs.append(job)
                new_count += 1

            logger.info("Found %d cards, %d new jobs (total: %d)", len(cards), new_count, len(found_jobs))

            if qi > 0 and random.random() < FEED_BREAK_CHANCE:
                self._open_url_in_existing_chrome("https://www.linkedin.com/feed/")
                self._scroll_page(random.randint(3, 8))

            human_pause(*BETWEEN_SEARCHES)

        return found_jobs

    def _build_url(self, query: SearchQuery) -> str:
        wt = "&f_WT=2" if query.remote_only else ""
        tpr = f"&f_TPR={query.time_filter}" if query.time_filter else ""
        location = f"&location={quote(query.location)}" if query.location else ""
        keyword = quote(query.keyword)
        return f"https://www.linkedin.com/jobs/search/?f_AL=true{wt}{tpr}{location}&keywords={keyword}&sortBy=DD"

    def _open_url_in_existing_chrome(self, url: str) -> str:
        script = f'''
        tell application "Google Chrome"
            activate
            if (count of windows) = 0 then
                return "No existing Chrome window. Open logged-in Chrome first."
            end if

            repeat with wi from 1 to count of windows
                set w to window wi
                repeat with ti from 1 to count of tabs of w
                    if URL of tab ti of w contains "linkedin.com" then
                        set active tab index of w to ti
                        set index of w to 1
                        set URL of tab ti of w to "{self._as_applescript_string(url)}"
                        return URL of tab ti of w
                    end if
                end repeat
            end repeat

            tell front window
                make new tab with properties {{URL:"{self._as_applescript_string(url)}"}}
                set active tab index to (count of tabs)
                return URL of active tab
            end tell
        end tell
        '''
        return self._osascript(script, timeout=20)

    def _wait_for_cards(self, max_wait: int = 20) -> int:
        for _ in range(max_wait // 3):
            human_pause(2, 4)
            try:
                raw = self._js(
                    'document.querySelectorAll(".scaffold-layout__list-item, li.ember-view.occludable-update").length.toString()',
                    timeout=10,
                )
                if raw and raw.isdigit() and int(raw) > 0:
                    return int(raw)
            except Exception:
                continue
        return 0

    def _scroll_job_list(self, times: int) -> None:
        for _ in range(times):
            amount = random.randint(200, 600)
            self._js(
                'var l=document.querySelector(".jobs-search-results-list,.scaffold-layout__list");'
                f"if(l)l.scrollBy(0,{amount});",
                timeout=10,
            )
            human_pause(1.5, 4)

    def _scroll_page(self, times: int) -> None:
        for _ in range(times):
            amount = random.randint(150, 500)
            self._js(f"window.scrollBy(0,{amount});", timeout=10)
            human_pause(1.5, 4)

    def _rate_limited(self) -> bool:
        try:
            text = self._js('document.body ? document.body.innerText.substring(0, 5000) : ""', timeout=10).lower()
        except Exception:
            return False
        return "429" in text or "rate limit" in text or "let's do a quick security check" in text

    def _extract_cards(self) -> list[dict]:
        try:
            raw = self._js(_EXTRACT_CARDS_JS, timeout=20)
            if not raw:
                return []
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("Failed to extract cards: %s", exc)
            return []

    def _js(self, code: str, timeout: int = 30) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write(code)
            js_path = handle.name
        script = (
            'tell application "Google Chrome" to tell active tab of front window '
            f'to execute javascript (read POSIX file "{js_path}" as text)'
        )
        result = self._osascript(script, timeout=timeout)
        return "" if result == "missing value" else result

    def _osascript(self, script: str, timeout: int = 30) -> str:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "AppleScript failed."
            raise RuntimeError(message)
        return result.stdout.strip()

    def _as_applescript_string(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')


def query_from_plan(item: SearchPlanItem) -> SearchQuery:
    return SearchQuery(
        keyword=item.keyword,
        remote_only=item.remote_only,
        time_filter=item.time_filter,
        location=item.location,
    )
