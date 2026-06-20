from __future__ import annotations

import json
import os
import re

from ..config import load_preferences
from ..career import load_profile_answers
from ..form_filler import AIFormFiller, load_profile
from ..models import Job
from ..policy import load_policy
from ..providers import get_provider
from ..providers.rules import RulesProvider
from .runtime import workspace


def _profile_text() -> str:
    text = load_profile(workspace())
    return text or "Candidate profile is incomplete."


def _provider():
    name = os.environ.get("APPLYPILOT_PROVIDER", "auto")
    try:
        return get_provider(name)
    except SystemExit:
        return RulesProvider()


def evaluate_job(job_title: str, company: str, job_description: str, location: str = "") -> dict:
    """Compatibility shape for the original working-agent scripts."""
    job = Job(
        id=f"{job_title.lower()}::{company.lower()}::{location.lower()}",
        title=job_title,
        company=company,
        location=location,
        description=job_description or job_title,
        easy_apply=True,
    )
    try:
        evaluation = _provider().evaluate(_profile_text(), load_preferences(workspace()), job)
    except Exception:
        evaluation = RulesProvider().evaluate(_profile_text(), load_preferences(workspace()), job)
    policy = load_policy(workspace())
    return {
        "apply": evaluation.score >= policy.min_score_to_submit,
        "score": evaluation.score,
        "minimum_score": policy.min_score_to_submit,
        "reason": evaluation.reason,
        "matching_skills": evaluation.matching_terms,
        "missing_skills": evaluation.missing_terms,
    }


def answer_form_question(question: str, options: list[str] | None = None) -> str:
    answer = _default_answer(question, options)
    if answer:
        return answer
    filler = AIFormFiller(_profile_text(), provider_name=os.environ.get("APPLYPILOT_FORM_PROVIDER", "auto"))
    ai_answer = filler.answer(question, options=options)
    return ai_answer or _fallback_option(options)


def ask_claude(prompt: str, max_tokens: int = 2048) -> str:
    """Legacy name kept for lead_hunter compatibility.

    Uses the configured ApplyPilot form provider when available. Returns empty
    if no provider key is configured, so lead extraction still works.
    """
    filler = AIFormFiller(_profile_text(), provider_name=os.environ.get("APPLYPILOT_FORM_PROVIDER", "auto"))
    return filler.answer(prompt) or ""


def _default_answer(question: str, options: list[str] | None = None) -> str:
    q = (question or "").lower()
    option_text = " ".join(options or []).lower()
    has_yes_no = "yes" in option_text and "no" in option_text
    answers = _profile_answers()

    if "sponsor" in q or "visa" in q:
        saved = answers.get("sponsorship_needed")
        return saved or ("No" if has_yes_no or not options else _fallback_option(options))
    if "authorized" in q or "legally" in q or "relocate" in q:
        key = "willing_to_relocate" if "relocate" in q else "authorized_to_work"
        saved = answers.get(key)
        return saved or ("Yes" if has_yes_no or not options else _fallback_option(options))
    if "notice" in q:
        return answers.get("notice_period", "")
    if "experience" in q or "years" in q:
        return answers.get("years_experience", "")
    if "current ctc" in q:
        return answers.get("current_ctc", "")
    if "expected ctc" in q:
        return answers.get("expected_ctc", "")
    if "phone" in q or "mobile" in q:
        return os.environ.get("APPLYPILOT_PHONE", "") or answers.get("phone", "")
    if "email" in q:
        return os.environ.get("APPLYPILOT_EMAIL", "") or answers.get("email", "")
    if "linkedin" in q:
        return os.environ.get("APPLYPILOT_LINKEDIN_URL", "") or answers.get("linkedin_url", "")
    if "github" in q or "portfolio" in q or "website" in q:
        return os.environ.get("APPLYPILOT_WEBSITE", "") or answers.get("website", "")
    if re.search(r"\b(first name|given name)\b", q):
        return os.environ.get("APPLYPILOT_FIRST_NAME", "") or answers.get("first_name", "")
    if re.search(r"\b(last name|surname)\b", q):
        return os.environ.get("APPLYPILOT_LAST_NAME", "") or answers.get("last_name", "")
    return ""


def _fallback_option(options: list[str] | None = None) -> str:
    if not options:
        return ""
    for preferred in ("Yes", "No"):
        for option in options:
            if option.strip().lower() == preferred.lower():
                return option
    return options[0] if options else ""


def _profile_answers() -> dict[str, str]:
    return load_profile_answers(workspace())
