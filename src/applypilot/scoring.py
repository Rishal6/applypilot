from __future__ import annotations

from pathlib import Path

from .config import load_preferences
from .models import Evaluation, Job
from .providers import get_provider


def load_profile(workspace: Path) -> str:
    profile_file = workspace / "profile.md"
    if not profile_file.exists():
        return ""
    return profile_file.read_text(encoding="utf-8")


def score_jobs(workspace: Path, jobs: list[Job], provider_name: str = "rules") -> list[Evaluation]:
    preferences = load_preferences(workspace)
    profile_text = load_profile(workspace)
    provider = get_provider(provider_name)
    results = []
    for job in jobs:
        try:
            results.append(provider.evaluate(profile_text, preferences, job))
        except Exception:
            results.append(Evaluation(
                job_id=job.id, score=0, decision="reject",
                reason="Scoring failed", provider=provider_name,
            ))
    return results

