from __future__ import annotations

import json
import re

from .base import decision_for_score
from ..models import Evaluation, Job, Preferences


def build_scoring_prompt(profile_text: str, preferences: Preferences, job: Job) -> str:
    return f"""Score this job for the candidate.

Return ONLY valid JSON with this shape:
{{"score": 0-100, "decision": "shortlist|review|reject", "reason": "short reason", "matching_terms": ["term"], "missing_terms": ["term"]}}

Candidate profile:
{profile_text[:6000]}

Target roles:
{", ".join(preferences.target_roles)}

Preferred skills:
{", ".join(preferences.preferred_skills)}

Avoid:
{", ".join(preferences.avoid_keywords)}

Job:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}
- Easy Apply: {job.easy_apply}
- Description: {job.description[:4000] or "Not available"}
"""


def parse_llm_evaluation(text: str, job: Job, preferences: Preferences, provider: str) -> Evaluation:
    payload = extract_json(text)
    score = int(payload.get("score", 0))
    score = max(0, min(100, score))
    decision = str(payload.get("decision") or decision_for_score(score, preferences)).lower()
    if decision not in {"shortlist", "review", "reject"}:
        decision = decision_for_score(score, preferences)
    return Evaluation(
        job_id=job.id,
        score=score,
        decision=decision,
        reason=str(payload.get("reason") or "LLM returned no reason.")[:500],
        matching_terms=list(payload.get("matching_terms") or []),
        missing_terms=list(payload.get("missing_terms") or []),
        provider=provider,
    )


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if not match:
            raise ValueError("Provider did not return JSON.")
        return json.loads(match.group())

