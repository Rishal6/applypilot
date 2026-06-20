"""Premium discovery helpers for LinkedIn and Naukri.

This module intentionally drafts outreach only. It may inspect profile viewers,
search hiring-manager profiles, and read Naukri status pages, but it must not
click LinkedIn Connect, Message, InMail, or Send buttons. Sending stays a manual
customer action unless a separate, explicit automation policy supports it.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .career import load_career_profile, split_target_roles
from .config import load_preferences
from .human import human_pause
from .search_plan import normalize

logger = logging.getLogger(__name__)

MAX_INMAILS_PER_DAY = 10
MAX_CONNECTS_PER_DAY = 20

RELEVANT_VIEWER_KEYWORDS = [
    "recruit", "talent", "hiring", "hr", "engineer", "developer",
    "cto", "founder", "lead", "manager",
]

DEFAULT_HIRING_MANAGER_SEARCHES = [
    "recruiter hiring",
    "talent acquisition hiring",
    "engineering manager hiring",
    "founder hiring",
]


class PremiumFeatures:
    """Draft premium LinkedIn outreach and inspect Naukri activity."""

    def __init__(self, workspace: Path, max_inmails: int = MAX_INMAILS_PER_DAY, max_connects: int = MAX_CONNECTS_PER_DAY):
        self.workspace = workspace
        self.max_inmails = max_inmails
        self.max_connects = max_connects
        self.profile = load_career_profile(workspace)
        self.preferences = load_preferences(workspace)
        self._page = None
        self._connect_drafts = 0
        self._inmail_drafts = 0

    def run(self, page) -> dict[str, Any]:
        """Run premium discovery. Expects a Playwright page logged into LinkedIn."""
        self._page = page
        self._connect_drafts = 0
        self._inmail_drafts = 0

        viewers = self._get_profile_viewers()
        self._process_viewers(viewers)

        hiring_people = self._search_hiring_managers()
        self._send_inmails(hiring_people)

        naukri_views = self._check_naukri_status()

        summary = {
            "profile_viewers_found": len(viewers),
            "connection_drafts": self._connect_drafts,
            "inmail_drafts": self._inmail_drafts,
            "connections_sent": 0,
            "inmails_sent": 0,
            "naukri_activity": len(naukri_views),
        }
        logger.info(
            "Premium discovery complete: viewers=%d, connection_drafts=%d, inmail_drafts=%d, naukri=%d",
            len(viewers), self._connect_drafts, self._inmail_drafts, len(naukri_views),
        )
        return summary

    # ═══════════════════════════════════════════════════════════════
    # Feature 1: Profile Viewers → Connection Drafts
    # ═══════════════════════════════════════════════════════════════

    def _get_profile_viewers(self) -> list[dict[str, str]]:
        """Get people who viewed the profile. This is read-only."""
        logger.info("Premium Feature 1: Profile Viewers")
        self._page.goto(
            "https://www.linkedin.com/me/profile-views/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        human_pause(4, 7)

        raw = self._page.evaluate("""
        (() => {
            const results = [];
            const viewers = document.querySelectorAll(
                '.profile-views__list-item, .entity-result, [class*="profile-view"]'
            );
            for (const viewer of viewers) {
                const nameEl = viewer.querySelector('a[href*="/in/"] span, .profile-views__actor-name');
                const headlineEl = viewer.querySelector('.profile-views__actor-headline, [class*="headline"]');
                const linkEl = viewer.querySelector('a[href*="/in/"]');
                const timeEl = viewer.querySelector('.profile-views__view-date, time');
                const name = nameEl ? nameEl.textContent.trim() : '';
                const headline = headlineEl ? headlineEl.textContent.trim() : '';
                const url = linkEl ? linkEl.href.split('?')[0] : '';
                const viewTime = timeEl ? timeEl.textContent.trim() : '';
                if (name && name.length > 2 && name !== 'LinkedIn Member') {
                    results.push({ name, headline, profile_url: url, viewed_time: viewTime });
                }
            }
            return results;
        })()
        """)
        viewers = raw if isinstance(raw, list) else []
        logger.info("  Found %d profile viewers", len(viewers))
        return viewers

    def _process_viewers(self, viewers: list[dict[str, str]]) -> None:
        """Save connection-note drafts for relevant profile viewers."""
        for viewer in viewers:
            if self._connect_drafts >= self.max_connects:
                logger.info("  Hit daily connection draft limit (%d)", self.max_connects)
                break
            if not self._is_relevant_person(viewer):
                continue

            note = self._generate_connect_note(viewer)
            self._connect_drafts += 1
            self._save_csv("connection_drafts.csv", {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "name": viewer.get("name", ""),
                "headline": viewer.get("headline", ""),
                "profile_url": viewer.get("profile_url", ""),
                "note": note,
                "status": "draft",
            }, ["date", "name", "headline", "profile_url", "note", "status"])
            human_pause(1, 3)

    def _connect_with_viewer(self, viewer: dict[str, str]) -> str:
        """Disabled guard: this module drafts only and never sends requests."""
        logger.info("Connection sending is disabled; saved a draft instead for %s", viewer.get("name", "viewer"))
        return "blocked"

    def _generate_connect_note(self, viewer: dict[str, str]) -> str:
        """Generate a short personalized connection note from customer profile facts."""
        first_name = (viewer.get("name") or "").split()[0]
        greeting = f"Hi {first_name}," if first_name else "Hi,"
        target = self._target_summary()
        skills = self._skills_summary(max_items=3)
        skills_part = f" with {skills}" if skills else ""
        note = (
            f"{greeting} thanks for viewing my profile. "
            f"I'm {self._candidate_name_or_phrase()}, targeting {target}{skills_part}. "
            "Would be glad to connect."
        )
        return _trim(note, 290)

    # ═══════════════════════════════════════════════════════════════
    # Feature 2: Hiring Managers → InMail Drafts
    # ═══════════════════════════════════════════════════════════════

    def _search_hiring_managers(self) -> list[dict[str, str]]:
        """Find hiring managers/recruiters using profile-driven search terms."""
        logger.info("Premium Feature 2: Hiring Manager Search")
        all_people: list[dict[str, str]] = []

        for query in self._hiring_searches()[:3]:
            self._page.goto(
                f"https://www.linkedin.com/search/results/people/?keywords={quote(query)}&openToHire=true",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            human_pause(4, 7)

            raw = self._page.evaluate("""
            (() => {
                const results = [];
                const cards = document.querySelectorAll('.entity-result, .reusable-search__result-container');
                for (let i = 0; i < Math.min(cards.length, 10); i++) {
                    const card = cards[i];
                    const nameEl = card.querySelector('.entity-result__title-text a span span, .app-aware-link span');
                    const headlineEl = card.querySelector('.entity-result__primary-subtitle, .entity-result__summary');
                    const linkEl = card.querySelector('a[href*="/in/"]');
                    const inmailBtn = card.querySelector('button[aria-label*="InMail"], button[aria-label*="Message"]');
                    const name = nameEl ? nameEl.textContent.trim() : '';
                    const headline = headlineEl ? headlineEl.textContent.trim() : '';
                    const url = linkEl ? linkEl.href.split('?')[0] : '';
                    const hasInmail = inmailBtn ? 'yes' : 'no';
                    if (name && name.length > 2) {
                        results.push({ name, headline, profile_url: url, has_inmail: hasInmail });
                    }
                }
                return results;
            })()
            """)
            if isinstance(raw, list):
                all_people.extend(raw)
            human_pause(5, 10)

        logger.info("  Found %d potential contacts", len(all_people))
        return all_people

    def _send_inmails(self, people: list[dict[str, str]]) -> None:
        """Save InMail drafts for relevant people. Kept name for CLI compatibility."""
        for person in people:
            if self._inmail_drafts >= self.max_inmails:
                logger.info("  Hit daily InMail draft limit (%d)", self.max_inmails)
                break
            if not self._is_relevant_person(person):
                continue

            message = self._generate_inmail(person)
            self._inmail_drafts += 1
            self._save_csv("inmail_drafts.csv", {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "name": person.get("name", ""),
                "headline": person.get("headline", ""),
                "profile_url": person.get("profile_url", ""),
                "subject": f"{self._target_summary()} - quick intro",
                "message": message,
                "status": "draft",
            }, ["date", "name", "headline", "profile_url", "subject", "message", "status"])
            human_pause(1, 3)

    def _send_inmail(self, person: dict[str, str]) -> str:
        """Disabled guard: this module drafts only and never sends InMail."""
        logger.info("InMail sending is disabled; saved a draft instead for %s", person.get("name", "contact"))
        return "blocked"

    def _generate_inmail(self, person: dict[str, str]) -> str:
        """Generate a personalized InMail draft from customer profile facts."""
        first_name = person.get("name", "").split()[0] if person.get("name") else "there"
        target = self._target_summary()
        skills = self._skills_summary(max_items=5)
        background = _first_sentence(self.profile.get("background") or "")
        signature = self._contact_signature()

        body = [
            f"Hi {first_name},",
            "",
            f"I noticed your profile while looking at {target} opportunities.",
        ]
        if background:
            body.append(f"My background: {background}")
        elif skills:
            body.append(f"My relevant skills include {skills}.")
        body.extend([
            "",
            "If you are hiring for a role where my profile fits, I would be happy to share my resume.",
            "",
            f"Best,\n{signature}",
        ])
        return "\n".join(body)

    # ═══════════════════════════════════════════════════════════════
    # Feature 3: Naukri Application Status
    # ═══════════════════════════════════════════════════════════════

    def _check_naukri_status(self) -> list[str]:
        """Check Naukri application status — who viewed the resume."""
        logger.info("Premium Feature 3: Naukri Application Status")

        self._page.goto("https://www.naukri.com", wait_until="domcontentloaded", timeout=30000)
        human_pause(3, 5)
        self._page.goto(
            "https://www.naukri.com/mnjuser/applicationStatusTracking",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        human_pause(4, 7)

        raw = self._page.evaluate("""
        (() => {
            const results = [];
            const items = document.querySelectorAll('[class*="application"], [class*="status"], .tuple, .card');
            for (let i = 0; i < Math.min(items.length, 20); i++) {
                const text = items[i].innerText.trim();
                if (text.length > 20 && text.length < 500) {
                    results.push(text.replace(/\\n/g, ' | ').substring(0, 300));
                }
            }
            return results;
        })()
        """)

        if not raw or not isinstance(raw, list):
            self._page.goto(
                "https://www.naukri.com/mnjuser/profile",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            human_pause(3, 5)
            raw = self._page.evaluate("""
            (() => {
                const text = document.body ? document.body.innerText.substring(0, 3000) : '';
                return text.split('\\n').filter(l => l.length > 20);
            })()
            """)
            raw = raw if isinstance(raw, list) else []

        viewed: list[str] = []
        for line in raw:
            line_lower = line.lower() if isinstance(line, str) else ""
            if any(kw in line_lower for kw in ["viewed", "shortlisted", "recruiter"]):
                viewed.append(str(line).strip()[:200])

        for status in viewed[:10]:
            self._save_csv("naukri_status.csv", {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "status": status[:200],
                "action": "review_follow_up",
            }, ["date", "status", "action"])

        logger.info("  Found %d applications with recruiter activity", len(viewed))
        return viewed

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    def _is_relevant_person(self, person: dict[str, str]) -> bool:
        searchable = normalize(" ".join([
            str(person.get("name") or ""),
            str(person.get("headline") or ""),
        ]))
        if not searchable:
            return False
        terms = [
            *RELEVANT_VIEWER_KEYWORDS,
            *self.preferences.target_roles,
            *self.preferences.preferred_skills[:8],
        ]
        return any(normalize(term) and normalize(term) in searchable for term in terms)

    def _hiring_searches(self) -> list[str]:
        roles = list(self.preferences.target_roles)
        if not roles:
            roles = split_target_roles(str(self.profile.get("target") or ""))
        searches: list[str] = []
        for role in roles[:4]:
            searches.append(f"{role} recruiter hiring")
            searches.append(f"{role} hiring manager")
        for skill in self.preferences.preferred_skills[:3]:
            searches.append(f"{skill} recruiter hiring")
        return _dedupe(searches) or list(DEFAULT_HIRING_MANAGER_SEARCHES)

    def _target_summary(self) -> str:
        return (
            str(self.profile.get("target") or "").strip()
            or ", ".join(self.preferences.target_roles[:2])
            or "relevant roles"
        )

    def _skills_summary(self, max_items: int = 4) -> str:
        skills = self.profile.get("skills") or self.preferences.preferred_skills
        return ", ".join(str(skill) for skill in skills[:max_items] if str(skill).strip())

    def _candidate_name_or_phrase(self) -> str:
        name = str(self.profile.get("name") or "").strip()
        return name if name else "a candidate"

    def _contact_signature(self) -> str:
        parts = [
            str(self.profile.get("name") or "").strip() or "Candidate",
            str(self.profile.get("email") or "").strip(),
            str(self.profile.get("phone") or "").strip(),
            str(self.profile.get("linkedin_url") or "").strip(),
            str(self.profile.get("website") or "").strip(),
        ]
        return " | ".join(part for part in parts if part)

    def _save_csv(self, filename: str, row: dict[str, str], headers: list[str]) -> None:
        """Append a row to a CSV file in workspace."""
        output_dir = self.workspace / "premium"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        file_exists = filepath.exists()
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split())
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _first_sentence(value: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        return ""
    for sep in [". ", "\n"]:
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0]
            break
    return _trim(cleaned, 260)


def _trim(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
