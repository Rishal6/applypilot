from __future__ import annotations

from typing import Protocol

from ..models import Evaluation, Job, Preferences


class ScoringProvider(Protocol):
    name: str

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        """Return a structured job fit evaluation."""


def decision_for_score(score: int, preferences: Preferences) -> str:
    if score >= preferences.min_score_to_shortlist:
        return "shortlist"
    if score >= preferences.min_score_to_review:
        return "review"
    return "reject"

