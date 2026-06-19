from __future__ import annotations

from .rules import RulesProvider
from ..models import Evaluation, Job, Preferences


class ManagedPreviewProvider:
    """No-key managed-plan preview.

    Real hosted model routing belongs server-side behind the SaaS license. Until
    that route is live, this gives managed-plan users a safe no-key path using
    the deterministic rules scorer.
    """

    name = "managed_preview"

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        evaluation = RulesProvider().evaluate(profile_text, preferences, job)
        evaluation.provider = self.name
        evaluation.reason = f"Managed preview (rules-backed): {evaluation.reason}"
        return evaluation
