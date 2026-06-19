from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .career import load_career_profile, split_locations, split_target_roles
from .config import load_preferences
from .models import Job, Preferences


GENERIC_ROLE_WORDS = {
    "associate",
    "consultant",
    "developer",
    "engineer",
    "expert",
    "lead",
    "manager",
    "principal",
    "remote",
    "senior",
    "specialist",
    "staff",
}


@dataclass(slots=True, frozen=True)
class SearchPlanItem:
    keyword: str
    remote_only: bool = False
    time_filter: str = "r604800"
    location: str = ""


def build_search_plan(workspace: Path, max_queries: int = 12) -> list[SearchPlanItem]:
    profile = load_career_profile(workspace)
    roles = dedupe(split_target_roles(profile.get("target") or ""))
    if not roles:
        raise ValueError("Complete your target role in the ApplyPilot profile before searching.")

    location_text = str(profile.get("location") or "")
    locations = split_locations(location_text)
    remote = "remote" in location_text.casefold()
    physical_location = next(
        (item for item in locations if "remote" not in item.casefold() and not relocation_phrase(item)),
        "",
    )

    plan: list[SearchPlanItem] = []
    for role in roles[:8]:
        plan.append(SearchPlanItem(keyword=role, location=physical_location))

    if remote:
        for role in roles[: min(4, len(roles))]:
            plan.append(SearchPlanItem(keyword=role, remote_only=True))

    return dedupe_plan(plan)[:max_queries]


def is_profile_aligned(job: Job, preferences: Preferences) -> bool:
    title = normalize(job.title)
    description = normalize(job.description)
    searchable = f"{title} {description}".strip()
    if not title:
        return False

    avoid_hits = [term for term in preferences.avoid_keywords if normalize(term) in searchable]
    if avoid_hits:
        return False

    role_phrases = [normalize(role) for role in preferences.target_roles if normalize(role)]
    if any(phrase in searchable for phrase in role_phrases):
        return True

    title_tokens = token_set(title)
    role_tokens = {
        token
        for role in preferences.target_roles
        for token in token_set(role)
        if token not in GENERIC_ROLE_WORDS
    }
    if role_tokens and title_tokens.intersection(role_tokens):
        return True

    skill_tokens = {
        token
        for skill in preferences.preferred_skills
        for token in token_set(skill)
        if len(token) >= 3
    }
    occupation_tokens = {"developer", "engineer", "scientist", "architect", "analyst", "specialist"}
    return bool(title_tokens.intersection(skill_tokens) and title_tokens.intersection(occupation_tokens))


def filter_profile_aligned(jobs: list[Job], preferences: Preferences) -> list[Job]:
    return [job for job in jobs if is_profile_aligned(job, preferences)]


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def token_set(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]{2,}", normalize(value)))


def relocation_phrase(value: str) -> bool:
    lowered = value.casefold()
    return "relocat" in lowered or lowered in {"anywhere", "any location"}


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", value).strip()
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def dedupe_plan(items: list[SearchPlanItem]) -> list[SearchPlanItem]:
    seen: set[tuple[str, bool, str]] = set()
    output: list[SearchPlanItem] = []
    for item in items:
        key = (item.keyword.casefold(), item.remote_only, item.location.casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
