"""Lead Hunter — find hiring leads from LinkedIn hashtags using Playwright.

Searches configurable hashtags, extracts emails/phones from posts,
identifies people with hiring badges, and uses the configured AI provider
to draft personalized outreach emails.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import random
import re
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .career import load_career_profile
from .config import load_preferences
from .human import human_pause, human_scroll, BETWEEN_SEARCHES
from .models import Lead
from .search_plan import normalize

logger = logging.getLogger(__name__)

DEFAULT_HASHTAGS = [
    "hiring GenAI Engineer",
    "hiring AI Engineer",
    "hiring LLM Engineer",
    "hiring Prompt Engineer",
    "hiring AI Agent Developer",
    "hiring Python AI",
    "hiring ML Engineer India",
    "hiring Remote AI",
    "GenAI jobs India",
    "AI Engineer immediate joiner",
    "LLM developer hiring",
    "RAG engineer hiring",
    "agentic AI hiring",
]

HIRING_SIGNALS = [
    "hiring", "we are looking", "join our team", "open position",
    "apply now", "send resume", "send cv", "dm me", "reach out",
    "immediate joiner", "looking for", "openings", "vacancy",
    "job opportunity", "we need", "urgent requirement",
    "walk-in", "interview scheduled", "#hiring",
]

RELEVANT_KEYWORDS = [
    "ai", "ml", "genai", "llm", "generative", "nlp", "python",
    "machine learning", "deep learning", "rag", "langchain",
    "prompt engineer", "agent", "data scientist", "fastapi",
]


class LeadHunter:
    """Searches LinkedIn for hiring leads using Playwright."""

    def __init__(self, workspace: Path, hashtags: list[str] | None = None, max_searches: int = 8):
        self.workspace = workspace
        self.profile = load_career_profile(workspace)
        self.preferences = load_preferences(workspace)
        self.hashtags = hashtags or self._load_hashtags()
        self.max_searches = max_searches
        self._page = None

    def _load_hashtags(self) -> list[str]:
        """Load hashtags from workspace config or use defaults."""
        config_file = self.workspace / "config.json"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
                tags = config.get("lead_hashtags")
                if tags:
                    return list(tags)
            except (json.JSONDecodeError, KeyError):
                pass

        profile_queries: list[str] = []
        for role in self.preferences.target_roles[:8]:
            profile_queries.append(f"hiring {role}")
            profile_queries.append(f"{role} jobs")
        for skill in self.preferences.preferred_skills[:6]:
            profile_queries.append(f"{skill} hiring")
        return _dedupe(profile_queries)[:20] or list(DEFAULT_HASHTAGS)

    def run(self, page) -> list[Lead]:
        """Run the full lead hunting cycle. Expects a Playwright page already logged into LinkedIn."""
        self._page = page
        all_leads: list[Lead] = []

        # Phase 1: Hashtag search
        logger.info("Lead Hunter: Phase 1 — Hashtag search (%d queries)", self.max_searches)
        shuffled = list(self.hashtags)
        random.shuffle(shuffled)

        for i, query in enumerate(shuffled[: self.max_searches]):
            logger.info("  [%d/%d] Searching: '%s'", i + 1, self.max_searches, query)
            posts = self._search_posts(query)
            logger.info("    Found %d posts", len(posts))

            for post in posts:
                if not self._is_job_post(post["text"]):
                    continue
                if not self._is_relevant_job(post["text"]):
                    continue

                emails = self._extract_emails(post["text"])
                phone = self._extract_phone(post["text"])

                if emails or phone or post.get("profile_url"):
                    lead = Lead(
                        name=post.get("author", ""),
                        headline=post.get("headline", ""),
                        email=emails[0] if emails else "",
                        phone=phone,
                        profile_url=post.get("profile_url", ""),
                        source="hashtag",
                        post_snippet=post.get("text", "")[:200],
                    )
                    # Draft outreach email if we have an email
                    if emails:
                        draft = self._draft_email(lead)
                        lead.draft_email = draft
                        logger.info("    LEAD: %s | %s", lead.name, lead.email)
                    else:
                        logger.info("    LEAD: %s (no email, has profile)", lead.name)

                    all_leads.append(lead)

            human_pause(*BETWEEN_SEARCHES)

        # Phase 2: Hiring badge people
        logger.info("Lead Hunter: Phase 2 — Hiring badge search")
        badge_leads = self._find_hiring_badges()
        logger.info("  Found %d people with hiring badges", len(badge_leads))
        all_leads.extend(badge_leads)

        # Save results
        self._save_leads(all_leads)

        logger.info(
            "Lead Hunt complete: %d leads (%d with email, %d with profile)",
            len(all_leads),
            sum(1 for l in all_leads if l.email),
            sum(1 for l in all_leads if l.profile_url),
        )
        return all_leads

    def _search_posts(self, query: str) -> list[dict[str, str]]:
        """Search LinkedIn for posts matching query."""
        encoded = query.replace(" ", "%20").replace("#", "%23")
        url = f"https://www.linkedin.com/search/results/content/?keywords={encoded}&sortBy=%22date_posted%22"
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        human_pause(4, 7)
        human_scroll(self._page, times=3)

        raw = self._page.evaluate("""
        (() => {
            const results = [];
            const seen = new Set();
            const textBlocks = document.querySelectorAll(
                '.feed-shared-text, .update-components-text__text-view, span[dir="ltr"]'
            );
            for (const block of textBlocks) {
                const text = block.innerText.trim();
                if (text.length > 50 && text.length < 3000 && !seen.has(text.substring(0, 50))) {
                    seen.add(text.substring(0, 50));
                    const parent = block.closest('.feed-shared-update-v2, [data-urn]');
                    const authorEl = parent ? parent.querySelector(
                        '.update-components-actor__name span, .feed-shared-actor__name span'
                    ) : null;
                    const headlineEl = parent ? parent.querySelector(
                        '.update-components-actor__description span, .feed-shared-actor__description span'
                    ) : null;
                    const linkEl = parent ? parent.querySelector('a[href*="/in/"]') : null;
                    results.push({
                        author: authorEl ? authorEl.textContent.trim() : '',
                        headline: headlineEl ? headlineEl.textContent.trim() : '',
                        text: text.substring(0, 1000),
                        profile_url: linkEl ? linkEl.href.split('?')[0] : '',
                    });
                }
            }
            return results;
        })()
        """)
        return raw if isinstance(raw, list) else []

    def _find_hiring_badges(self) -> list[Lead]:
        """Search for people with #Hiring badge on their profile."""
        self._page.goto(
            f"https://www.linkedin.com/search/results/people/?keywords={quote(self._people_search_query())}&openToHire=true",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        human_pause(4, 7)
        human_scroll(self._page, times=2)

        raw = self._page.evaluate("""
        (() => {
            const results = [];
            const cards = document.querySelectorAll('.entity-result, .reusable-search__result-container');
            for (let i = 0; i < Math.min(cards.length, 15); i++) {
                const card = cards[i];
                const nameEl = card.querySelector('.entity-result__title-text a span span, .app-aware-link span');
                const headlineEl = card.querySelector('.entity-result__primary-subtitle, .entity-result__summary');
                const linkEl = card.querySelector('a[href*="/in/"]');
                const name = nameEl ? nameEl.textContent.trim() : '';
                const headline = headlineEl ? headlineEl.textContent.trim() : '';
                const url = linkEl ? linkEl.href.split('?')[0] : '';
                const isHiring = card.textContent.indexOf('Hiring') > -1;
                if (name && name.length > 2) {
                    results.push({ name, headline, profile_url: url, hiring: isHiring });
                }
            }
            return results;
        })()
        """)
        leads: list[Lead] = []
        if not isinstance(raw, list):
            return leads

        for person in raw:
            if person.get("hiring") or "hiring" in person.get("headline", "").lower():
                leads.append(Lead(
                    name=person["name"],
                    headline=person.get("headline", ""),
                    profile_url=person.get("profile_url", ""),
                    source="hiring_badge",
                    post_snippet=f"Hiring badge - {person.get('headline', '')}",
                ))
        return leads

    def _draft_email(self, lead: Lead) -> str:
        """Use the configured AI provider to draft a personalized outreach email."""
        profile_summary = self._profile_summary()
        signature = self._contact_signature()
        prompt = (
            "Write a SHORT outreach email (5-6 lines max) for a job opportunity.\n\n"
            "Candidate profile facts:\n"
            f"{profile_summary}\n\n"
            f"Lead info:\n"
            f"- Person: {lead.name or 'Hiring Manager'}\n"
            f"- Their role: {lead.headline}\n"
            f"- Post/context: {lead.post_snippet[:200]}\n"
            f"- Email: {lead.email}\n\n"
            "Write a personalized, human email (not generic). Mention something specific "
            "from their post/role.\n"
            "Format: Subject line first, then body. Keep it under 6 lines.\n"
            f"End with this exact candidate contact line if available: {signature}\n"
            "Do NOT invent employers, years of experience, phone numbers, degrees, salary, "
            "metrics, or achievements that are not in the profile facts.\n"
            "Do NOT use bullet points. Write like a real person."
        )
        return self._ask_ai(prompt)

    def _ask_ai(self, prompt: str) -> str:
        """Call the configured AI provider for text generation."""
        from .provider_config import load_local_provider_env

        load_local_provider_env(self.workspace)

        # Try Groq first, then Gemini, then OpenAI
        groq_key = os.environ.get("GROQ_API_KEY", "")
        if groq_key:
            return self._call_groq(prompt, groq_key)

        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if gemini_key:
            return self._call_gemini(prompt, gemini_key)

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            return self._call_openai(prompt, openai_key)

        logger.warning("No AI provider configured for lead email drafting.")
        return ""

    def _call_groq(self, prompt: str, api_key: str) -> str:
        model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 400,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("Groq call failed for email draft: %s", exc)
            return ""

    def _call_gemini(self, prompt: str, api_key: str) -> str:
        model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            logger.warning("Gemini call failed for email draft: %s", exc)
            return ""

    def _call_openai(self, prompt: str, api_key: str) -> str:
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 400,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("OpenAI call failed for email draft: %s", exc)
            return ""

    @staticmethod
    def _is_job_post(text: str) -> bool:
        text_lower = text.lower()
        return any(signal in text_lower for signal in HIRING_SIGNALS)

    def _is_relevant_job(self, text: str) -> bool:
        text_normalized = normalize(text)
        if not text_normalized:
            return False

        avoid_hits = [
            term for term in self.preferences.avoid_keywords
            if normalize(term) and normalize(term) in text_normalized
        ]
        if avoid_hits:
            return False

        terms = [
            *self.preferences.target_roles,
            *self.preferences.preferred_skills,
            str(self.profile.get("target") or ""),
            " ".join(str(item) for item in self.profile.get("skills") or []),
        ]
        if any(normalize(term) and normalize(term) in text_normalized for term in terms):
            return True
        return any(kw in text_normalized for kw in RELEVANT_KEYWORDS)

    @staticmethod
    def _extract_emails(text: str) -> list[str]:
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(pattern, text)
        return [
            e for e in emails
            if not any(x in e.lower() for x in ["noreply", "no-reply", "support", "info@linkedin", "notifications"])
        ]

    @staticmethod
    def _extract_phone(text: str) -> str:
        patterns = [
            r"\+91[\s-]?\d{5}[\s-]?\d{5}",
            r"\d{10}",
            r"\+\d{2}[\s-]?\d{5}[\s-]?\d{5}",
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group()
        return ""

    def _save_leads(self, leads: list[Lead]) -> None:
        """Save leads to both JSON and CSV in workspace."""
        output_dir = self.workspace / "leads"
        output_dir.mkdir(parents=True, exist_ok=True)

        # JSON
        json_file = output_dir / "leads.json"
        existing: list[dict[str, Any]] = []
        if json_file.exists():
            try:
                existing = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                existing = []
        existing.extend(lead.to_dict() for lead in leads)
        json_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        # CSV
        csv_file = output_dir / "leads.csv"
        file_exists = csv_file.exists()
        headers = ["found_at", "source", "name", "headline", "email", "phone", "profile_url", "post_snippet", "draft_email", "status"]
        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()
            for lead in leads:
                writer.writerow({
                    "found_at": lead.found_at,
                    "source": lead.source,
                    "name": lead.name,
                    "headline": lead.headline,
                    "email": lead.email,
                    "phone": lead.phone,
                    "profile_url": lead.profile_url,
                    "post_snippet": lead.post_snippet,
                    "draft_email": lead.draft_email,
                    "status": lead.status,
                })

        logger.info("Saved %d leads to %s", len(leads), output_dir)

    def _people_search_query(self) -> str:
        role = next((item for item in self.preferences.target_roles if item), "")
        if not role:
            role = str(self.profile.get("target") or "").strip()
        if role:
            return f"{role} recruiter hiring"
        return "recruiter hiring"

    def _profile_summary(self) -> str:
        profile = self.profile
        skills = ", ".join(str(skill) for skill in profile.get("skills") or self.preferences.preferred_skills[:8])
        lines = [
            f"- Name: {profile.get('name') or 'Candidate'}",
            f"- Target: {profile.get('target') or ', '.join(self.preferences.target_roles[:3]) or 'Not provided'}",
            f"- Skills: {skills or 'Not provided'}",
            f"- Location preference: {profile.get('location') or 'Not provided'}",
            f"- Background: {profile.get('background') or 'Not provided'}",
        ]
        contact = self._contact_signature()
        if contact:
            lines.append(f"- Contact line: {contact}")
        return "\n".join(lines)

    def _contact_signature(self) -> str:
        profile = self.profile
        parts = [
            str(profile.get("name") or "").strip() or "Candidate",
            str(profile.get("email") or "").strip(),
            str(profile.get("phone") or "").strip(),
            str(profile.get("linkedin_url") or "").strip(),
            str(profile.get("website") or "").strip(),
        ]
        return " | ".join(part for part in parts if part)


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
