"""Naukri.com job search through the user's existing logged-in Chrome session."""

from __future__ import annotations

import json
import logging
import platform
import random
import subprocess
import tempfile
import time
from pathlib import Path

from ..config import load_preferences
from ..human import BETWEEN_SEARCHES, human_pause
from ..models import Job
from ..search_plan import is_profile_aligned

logger = logging.getLogger(__name__)

DEFAULT_NAUKRI_QUERIES: list[str] = [
    "AI Engineer",
    "GenAI Engineer",
    "LLM Engineer",
    "Prompt Engineer",
    "AI ML Engineer",
    "RAG Engineer",
    "AI Agent Developer",
    "AI Platform Engineer",
    "NLP Engineer",
    "Applied AI Engineer",
    "Python AI Developer",
    "Machine Learning Engineer",
    "Generative AI Developer",
    "AI Backend Engineer",
    "LangChain Developer",
]

_EXTRACT_LISTINGS_JS = """
(function() {
    var links = document.querySelectorAll('a');
    var jobs = [];
    for (var i = 0; i < links.length; i++) {
        var href = links[i].href || '';
        if (href.indexOf('job-listings') > -1 && href.indexOf('naukri.com') > -1) {
            var title = links[i].textContent.trim();
            if (title.length > 3 && title.length < 100 && jobs.length < 20) {
                jobs.push({title: title, url: href});
            }
        }
    }
    // Deduplicate by URL
    var seen = {};
    var unique = [];
    for (var j = 0; j < jobs.length; j++) {
        if (!seen[jobs[j].url]) {
            seen[jobs[j].url] = true;
            unique.push(jobs[j]);
        }
    }
    return JSON.stringify(unique);
})()
"""


class NaukriSearcher:
    """Search Naukri.com using the user's existing Google Chrome app/profile."""

    def __init__(self, workspace: Path, queries: list[str] | None = None):
        self.workspace = workspace
        self.queries = queries or list(DEFAULT_NAUKRI_QUERIES)

    def search(self) -> list[Job]:
        if platform.system() != "Darwin":
            raise SystemExit("Naukri active-Chrome search currently requires macOS.")

        preferences = load_preferences(self.workspace)
        found_jobs: list[Job] = []
        seen_urls: set[str] = set()

        queries = list(self.queries)
        random.shuffle(queries)

        for qi, query in enumerate(queries):
            url = self._build_url(query)
            logger.info("[%d/%d] Searching Naukri: '%s'", qi + 1, len(queries), query)

            self._navigate(url)
            human_pause(4, 7)

            cards = self._extract_listings()
            new_count = 0
            for card in cards:
                card_url = card.get("url", "")
                if card_url in seen_urls:
                    continue
                seen_urls.add(card_url)

                job = Job.from_dict(
                    {
                        "title": card.get("title", ""),
                        "url": card_url,
                        "company": card.get("company", ""),
                        "location": card.get("location", ""),
                        "easy_apply": True,  # Naukri apply is always direct
                    },
                    source="naukri-search",
                )
                if not is_profile_aligned(job, preferences):
                    logger.info("Filtered off-profile result: %s", job.title)
                    continue
                found_jobs.append(job)
                new_count += 1

            logger.info("Found %d listings, %d new jobs (total: %d)", len(cards), new_count, len(found_jobs))
            human_pause(*BETWEEN_SEARCHES)

        return found_jobs

    def _build_url(self, query: str) -> str:
        slug = query.lower().replace(" ", "-")
        keyword = query.replace(" ", "+")
        return f"https://www.naukri.com/{slug}-jobs?k={keyword}&experience=3&jobAge=7"

    def _navigate(self, url: str) -> None:
        escaped = self._as_applescript_string(url)
        self._osascript(
            f'tell application "Google Chrome" to set URL of active tab of front window to "{escaped}"',
            timeout=20,
        )

    def _extract_listings(self) -> list[dict]:
        try:
            raw = self._js_file(_EXTRACT_LISTINGS_JS, timeout=20)
            if not raw:
                return []
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to extract Naukri listings: %s", exc)
            return []

    def _js_file(self, code: str, timeout: int = 30) -> str:
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
