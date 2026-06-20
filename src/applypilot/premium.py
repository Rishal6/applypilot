"""Premium Features — LinkedIn InMail, profile viewer auto-connect, Naukri status.

Uses Playwright to automate premium LinkedIn and Naukri features with
human-like delays and daily rate limits.
"""

from __future__ import annotations

import csv
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from .human import human_pause, human_scroll

logger = logging.getLogger(__name__)

MAX_INMAILS_PER_DAY = 10
MAX_CONNECTS_PER_DAY = 20

RELEVANT_VIEWER_KEYWORDS = [
    "recruit", "talent", "hiring", "hr", "engineer", "ai",
    "ml", "genai", "cto", "founder", "lead", "manager",
]

HIRING_MANAGER_SEARCHES = [
    "AI Engineer hiring manager India",
    "GenAI recruiter India",
    "Machine Learning hiring India",
    "talent acquisition AI",
]


class PremiumFeatures:
    """Runs premium LinkedIn + Naukri features via Playwright."""

    def __init__(self, workspace: Path, max_inmails: int = MAX_INMAILS_PER_DAY, max_connects: int = MAX_CONNECTS_PER_DAY):
        self.workspace = workspace
        self.max_inmails = max_inmails
        self.max_connects = max_connects
        self._page = None
        self._connects_sent = 0
        self._inmails_sent = 0

    def run(self, page) -> dict[str, Any]:
        """Run all premium features. Expects a Playwright page logged into LinkedIn."""
        self._page = page
        self._connects_sent = 0
        self._inmails_sent = 0

        # Feature 1: Auto-connect with profile viewers
        viewers = self._get_profile_viewers()
        self._process_viewers(viewers)

        # Feature 2: InMail hiring managers
        hiring_people = self._search_hiring_managers()
        self._send_inmails(hiring_people)

        # Feature 3: Naukri application status
        naukri_views = self._check_naukri_status()

        summary = {
            "profile_viewers_found": len(viewers),
            "connections_sent": self._connects_sent,
            "inmails_sent": self._inmails_sent,
            "naukri_activity": len(naukri_views),
        }
        logger.info(
            "Premium features complete: viewers=%d, connects=%d, inmails=%d, naukri=%d",
            len(viewers), self._connects_sent, self._inmails_sent, len(naukri_views),
        )
        return summary

    # ═══════════════════════════════════════════════════════════════
    # Feature 1: Profile Viewers → Auto-Connect
    # ═══════════════════════════════════════════════════════════════

    def _get_profile_viewers(self) -> list[dict[str, str]]:
        """Get list of people who viewed your profile (Premium feature)."""
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
        """Auto-connect with relevant profile viewers."""
        for viewer in viewers[: self.max_connects]:
            headline_lower = viewer.get("headline", "").lower()
            relevant = any(kw in headline_lower for kw in RELEVANT_VIEWER_KEYWORDS)
            if not relevant:
                continue

            result = self._connect_with_viewer(viewer)
            if result == "connected":
                self._connects_sent += 1
                self._save_csv("connections_sent.csv", {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "name": viewer["name"],
                    "headline": viewer.get("headline", ""),
                    "profile_url": viewer.get("profile_url", ""),
                    "note": "Auto-connected (viewed profile)",
                }, ["date", "name", "headline", "profile_url", "note"])

            human_pause(10, 20)

            if self._connects_sent >= self.max_connects:
                logger.info("  Hit daily connect limit (%d)", self.max_connects)
                break

    def _connect_with_viewer(self, viewer: dict[str, str]) -> str:
        """Send connection request to someone who viewed your profile."""
        profile_url = viewer.get("profile_url", "")
        if not profile_url:
            return "no_url"

        self._page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        human_pause(3, 5)

        # Check if already connected
        body_text = self._page.evaluate("document.body ? document.body.innerText.substring(0, 3000) : ''")
        if "Message" in (body_text or "") and "Connect" not in (body_text or ""):
            logger.debug("    Already connected with %s", viewer["name"])
            return "already_connected"

        # Click Connect button
        clicked = self._page.evaluate("""
        (() => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                const aria = btn.getAttribute('aria-label') || '';
                if (text === 'Connect' || aria.indexOf('Connect') > -1) {
                    btn.click();
                    return 'clicked_connect';
                }
            }
            // Try "More" dropdown
            for (const btn of btns) {
                if (btn.textContent.trim() === 'More') {
                    btn.click();
                    return 'clicked_more';
                }
            }
            return 'no_connect_button';
        })()
        """)

        if clicked == "clicked_more":
            human_pause(1, 2)
            self._page.evaluate("""
            (() => {
                const items = document.querySelectorAll('[role="menuitem"], li');
                for (const item of items) {
                    if (item.textContent.indexOf('Connect') > -1) {
                        item.click();
                        return 'clicked';
                    }
                }
                return 'not_found';
            })()
            """)
            human_pause(1, 2)

        if "clicked" in (clicked or ""):
            human_pause(1, 2)
            note = self._generate_connect_note(viewer)

            # Click "Add a note"
            add_note = self._page.evaluate("""
            (() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.indexOf('Add a note') > -1) {
                        btn.click();
                        return 'note_opened';
                    }
                }
                return 'no_note_option';
            })()
            """)

            if add_note == "note_opened":
                human_pause(1, 2)
                # Type connection note
                self._page.evaluate(f"""
                (() => {{
                    const ta = document.querySelector('textarea#custom-message, textarea');
                    if (ta) {{
                        ta.value = {json.dumps(note)};
                        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }}
                }})()
                """)
                human_pause(1, 2)

            # Click Send
            self._page.evaluate("""
            (() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    const text = btn.textContent.trim();
                    if (text === 'Send' || text === 'Send now') {
                        btn.click();
                        return 'sent';
                    }
                }
                return 'no_send';
            })()
            """)
            logger.info("    Connected with %s", viewer["name"])
            return "connected"

        logger.debug("    Could not connect with %s (%s)", viewer["name"], clicked)
        return "failed"

    @staticmethod
    def _generate_connect_note(viewer: dict[str, str]) -> str:
        """Generate short personalized connection note."""
        headline = viewer.get("headline", "").lower()
        if any(kw in headline for kw in ["recruit", "talent", "hiring"]):
            return (
                "Hi! I noticed you viewed my profile. I'm an AI Engineer at Amazon "
                "(GenAI, RAG, multi-agent systems). Would love to connect and explore "
                "any relevant opportunities. - Rishal"
            )
        elif any(kw in headline for kw in ["engineer", "developer"]):
            return (
                "Hi! Saw you checked out my profile. I work on LLM systems and AI agents "
                "at Amazon. Would be great to connect with a fellow engineer. - Rishal"
            )
        else:
            return (
                "Hi! Thanks for viewing my profile. I'm an AI Engineer working on GenAI "
                "and LLM systems. Would love to connect! - Rishal"
            )

    # ═══════════════════════════════════════════════════════════════
    # Feature 2: InMail to Hiring Managers
    # ═══════════════════════════════════════════════════════════════

    def _search_hiring_managers(self) -> list[dict[str, str]]:
        """Find hiring managers/recruiters posting AI jobs."""
        logger.info("Premium Feature 2: InMail to Hiring Managers")
        all_people: list[dict[str, str]] = []

        for query in HIRING_MANAGER_SEARCHES[:2]:
            encoded = query.replace(" ", "%20")
            self._page.goto(
                f"https://www.linkedin.com/search/results/people/?keywords={encoded}&openToHire=true",
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
                    const nameEl = card.querySelector('.entity-result__title-text a span span');
                    const headlineEl = card.querySelector('.entity-result__primary-subtitle');
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
        """Send InMail to relevant people."""
        for person in people[: self.max_inmails]:
            headline_lower = person.get("headline", "").lower()
            relevant = any(kw in headline_lower for kw in [
                "recruit", "talent", "hiring", "hr", "ai", "genai",
                "machine learning", "engineering manager",
            ])
            if not relevant:
                continue

            result = self._send_inmail(person)
            if result == "sent":
                self._inmails_sent += 1
                self._save_csv("inmails_sent.csv", {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "name": person["name"],
                    "headline": person.get("headline", ""),
                    "profile_url": person.get("profile_url", ""),
                }, ["date", "name", "headline", "profile_url"])

            human_pause(15, 30)

            if self._inmails_sent >= self.max_inmails:
                logger.info("  Hit InMail daily limit (%d)", self.max_inmails)
                break

    def _send_inmail(self, person: dict[str, str]) -> str:
        """Send InMail to a person (Premium feature)."""
        profile_url = person.get("profile_url", "")
        if not profile_url:
            return "no_url"

        self._page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        human_pause(3, 5)

        # Click Message button
        clicked = self._page.evaluate("""
        (() => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                const aria = btn.getAttribute('aria-label') || '';
                if (text === 'Message' || aria.indexOf('Message') > -1 || aria.indexOf('InMail') > -1) {
                    btn.click();
                    return 'clicked';
                }
            }
            return 'no_message_button';
        })()
        """)

        if clicked != "clicked":
            return "no_button"

        human_pause(2, 4)
        message = self._generate_inmail(person)

        # Type subject if available
        self._page.evaluate("""
        (() => {
            const subj = document.querySelector('input[name=subject], input[placeholder*=Subject]');
            if (subj) {
                subj.value = 'AI Engineer - Interested in Opportunities';
                subj.dispatchEvent(new Event('input', {bubbles: true}));
            }
        })()
        """)
        human_pause(0.5, 1)

        # Type message body
        self._page.evaluate(f"""
        (() => {{
            const msgBox = document.querySelector('.msg-form__contenteditable, [role="textbox"], textarea[name*="message"]');
            if (msgBox) {{
                msgBox.focus();
                msgBox.textContent = {json.dumps(message)};
                msgBox.dispatchEvent(new Event('input', {{bubbles: true}}));
                return 'typed';
            }}
            return 'no_textbox';
        }})()
        """)
        human_pause(1, 2)

        # Click Send
        sent = self._page.evaluate("""
        (() => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                const text = btn.textContent.trim().toLowerCase();
                if (text === 'send' && !btn.disabled) {
                    btn.click();
                    return 'sent';
                }
            }
            return 'no_send';
        })()
        """)

        if sent == "sent":
            logger.info("    InMail sent to %s", person["name"])
            return "sent"
        return "failed"

    @staticmethod
    def _generate_inmail(person: dict[str, str]) -> str:
        """Generate personalized InMail message."""
        headline = person.get("headline", "").lower()
        first_name = person.get("name", "").split()[0] if person.get("name") else "Hi"

        if any(kw in headline for kw in ["recruit", "talent"]):
            return (
                f"Hi {first_name},\n\n"
                "I'm an AI Engineer at Amazon building production LLM systems "
                "(10K+ daily executions, RAG, multi-agent orchestration). "
                "I'm exploring new opportunities in GenAI/AI Engineering.\n\n"
                "Would love to chat if you have any relevant roles open.\n\n"
                "Best,\nRishal V S\n+91 97154 78366"
            )
        else:
            return (
                f"Hi {first_name},\n\n"
                "Noticed you're in the AI space. I'm currently at Amazon building LLM-powered systems "
                "and exploring my next move in GenAI/AI Engineering.\n\n"
                "Would be great to connect and learn about what your team is working on.\n\n"
                "Best,\nRishal V S"
            )

    # ═══════════════════════════════════════════════════════════════
    # Feature 3: Naukri Application Status
    # ═══════════════════════════════════════════════════════════════

    def _check_naukri_status(self) -> list[str]:
        """Check Naukri application status — who viewed your resume."""
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

        if not raw or not isinstance(raw, list) or len(raw) == 0:
            # Try alternative page
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

        # Filter for recruiter activity
        viewed: list[str] = []
        for line in raw:
            line_lower = line.lower() if isinstance(line, str) else ""
            if any(kw in line_lower for kw in ["viewed", "shortlisted", "recruiter"]):
                viewed.append(str(line).strip()[:200])

        if viewed:
            logger.info("  Found %d applications with recruiter activity", len(viewed))
            for v in viewed[:10]:
                self._save_csv("naukri_status.csv", {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "status": v[:200],
                    "action": "follow_up_needed",
                }, ["date", "status", "action"])
        else:
            logger.info("  No recruiter views detected yet")

        return viewed

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

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
