from __future__ import annotations

from typing import Protocol

from ..applications import ApplicationRecord
from ..models import Evaluation, Job
from ..policy import AutomationPolicy


class ApplicationConnector(Protocol):
    name: str

    def apply(self, job: Job, evaluation: Evaluation, policy: AutomationPolicy) -> ApplicationRecord:
        """Apply or prepare an application according to local policy."""


class NoopConnector:
    name = "none"

    def apply(self, job: Job, evaluation: Evaluation, policy: AutomationPolicy) -> ApplicationRecord:
        return ApplicationRecord(
            job_id=job.id,
            status="blocked",
            reason="No application connector configured. Use --connector linkedin-browser on the user's desktop.",
            score=evaluation.score,
            mode=policy.mode,
            connector=self.name,
        )


def get_application_connector(name: str, workspace):
    normalized = (name or "none").strip().lower()
    if normalized in {"none", "noop"}:
        return NoopConnector()
    if normalized in {"linkedin-browser", "linkedin", "desktop-browser"}:
        from .linkedin_browser import LinkedInBrowserConnector

        return LinkedInBrowserConnector(workspace)
    raise SystemExit(f"Unknown application connector: {name}")

