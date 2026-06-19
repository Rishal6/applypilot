from __future__ import annotations

import re

from .base import decision_for_score
from ..models import Evaluation, Job, Preferences


class RulesProvider:
    name = "rules"

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        haystack = " ".join([
            job.title,
            job.company,
            job.location,
            job.description,
            " ".join(str(v) for v in job.metadata.values() if isinstance(v, str)),
        ]).lower()

        title_haystack = " ".join([job.title, job.company]).lower()
        avoid_hits = find_terms(preferences.avoid_keywords, title_haystack)
        role_terms = expand_role_terms(preferences.target_roles)
        role_hits = find_terms(role_terms, haystack)
        skill_hits = find_terms(preferences.preferred_skills, haystack)
        location_hits = find_terms(preferences.preferred_locations, haystack)

        score = 10
        score += min(45, len(role_hits) * 10)
        score += min(35, len(skill_hits) * 5)
        score += min(10, len(location_hits) * 5)
        score += 5 if job.easy_apply else 0
        score -= min(45, len(avoid_hits) * 22)

        strong_title = re.search(
            r"\b(genai|generative ai|llm|rag|ai/ml|machine learning|ai engineer|agent)\b",
            job.title.lower(),
        )
        target_text = " ".join(preferences.target_roles).lower()
        targets_ai = bool(re.search(r"\b(ai|ml|llm|rag|nlp|machine learning|genai|agent)\b", target_text))
        if strong_title and targets_ai:
            score += 12
        if re.search(r"\bsenior\b|\bstaff\b|\bprincipal\b", job.title.lower()):
            score += 5
        if not job.description and len(role_hits) <= 1 and len(skill_hits) <= 1:
            score -= 10

        score = max(0, min(100, score))
        decision = decision_for_score(score, preferences)

        if avoid_hits:
            reason = f"Matched avoid keywords: {', '.join(avoid_hits[:3])}."
        elif decision == "shortlist":
            reason = f"Strong role/skill overlap: {', '.join((role_hits + skill_hits)[:5])}."
        elif decision == "review":
            reason = "Partial fit; review before spending application effort."
        else:
            reason = "Weak role or skill overlap for the current profile."

        return Evaluation(
            job_id=job.id,
            score=score,
            decision=decision,
            reason=reason,
            matching_terms=role_hits + skill_hits + location_hits,
            missing_terms=[term for term in preferences.preferred_skills if term.lower() not in haystack][:8],
            provider=self.name,
        )


def find_terms(terms: list[str], text: str) -> list[str]:
    hits: list[str] = []
    for term in terms:
        normalized = term.lower()
        if normalized in text:
            hits.append(term)
    return hits


def expand_role_terms(target_roles: list[str]) -> list[str]:
    terms = list(target_roles)
    target_text = " ".join(target_roles).lower()
    if re.search(r"\b(ai|ml|llm|rag|nlp|machine learning|genai|agent)\b", target_text):
        terms.extend([
            "ai",
            "ai/ml",
            "genai",
            "generative ai",
            "llm",
            "large language model",
            "rag",
            "nlp",
            "machine learning",
            "ml engineer",
            "prompt",
            "agent",
            "agentic",
            "applied ai",
            "ai platform",
            "ai automation",
        ])
    generic = {"engineer", "developer", "manager", "lead", "senior", "staff", "specialist"}
    for role in target_roles:
        terms.extend(
            token
            for token in re.findall(r"[a-z0-9+#.]{3,}", role.lower())
            if token not in generic
        )
    return dedupe_case_insensitive(terms)


def dedupe_case_insensitive(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out
