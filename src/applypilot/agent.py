from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .applications import ApplicationHistory, ApplicationRecord
from .connectors.apply import get_application_connector
from .models import Evaluation, Job
from .policy import load_policy
from .scoring import score_jobs
from .storage import Store


@dataclass(slots=True)
class AgentCycleSummary:
    scored: int = 0
    eligible: int = 0
    attempted: int = 0
    applied: int = 0
    skipped: int = 0
    blocked: int = 0
    failed: int = 0
    prepared: int = 0


def run_cycle(workspace: Path, provider_name: str = "rules", connector_name: str = "none") -> AgentCycleSummary:
    store = Store(workspace)
    jobs = store.load_jobs()
    if not jobs:
        return AgentCycleSummary()

    evaluations = score_jobs(workspace, jobs, provider_name=provider_name)
    store.save_evaluations(evaluations)

    policy = load_policy(workspace)
    history = ApplicationHistory(workspace)
    completed_ids = history.completed_job_ids()
    applied_today = history.applied_today_count()
    connector = get_application_connector(connector_name, workspace)

    jobs_by_id = {job.id: job for job in jobs}
    sorted_evaluations = sorted(evaluations, key=lambda item: item.score, reverse=True)
    summary = AgentCycleSummary(scored=len(evaluations))

    for evaluation in sorted_evaluations:
        job = jobs_by_id.get(evaluation.job_id)
        if not job or job.id in completed_ids:
            continue
        if not is_eligible(job, evaluation, policy):
            continue
        summary.eligible += 1
        if applied_today >= policy.max_applications_per_day:
            history.append(ApplicationRecord(
                job_id=job.id,
                status="blocked",
                reason="Daily auto-submit limit reached.",
                score=evaluation.score,
                mode=policy.mode,
                connector=connector.name,
            ))
            summary.blocked += 1
            break

        record = connector.apply(job, evaluation, policy)
        history.append(record)
        summary.attempted += 1

        if record.status == "applied":
            summary.applied += 1
            applied_today += 1
        elif record.status == "skipped":
            summary.skipped += 1
        elif record.status == "blocked":
            summary.blocked += 1
        elif record.status == "prepared":
            summary.prepared += 1
        else:
            summary.failed += 1

    return summary


def run_forever(
    workspace: Path,
    provider_name: str,
    connector_name: str,
    interval_seconds: int,
    max_cycles: int | None = None,
) -> None:
    cycle = 0
    while True:
        cycle += 1
        summary = run_cycle(workspace, provider_name=provider_name, connector_name=connector_name)
        print(format_summary(cycle, summary), flush=True)
        if max_cycles is not None and cycle >= max_cycles:
            return
        time.sleep(interval_seconds)


def is_eligible(job: Job, evaluation: Evaluation, policy) -> bool:
    if evaluation.score < policy.min_score_to_submit:
        return False
    if policy.require_easy_apply and not job.easy_apply:
        return False
    if policy.mode not in {"fill-only", "auto-submit"}:
        return False
    return True


def format_summary(cycle: int, summary: AgentCycleSummary) -> str:
    return (
        f"Cycle {cycle}: scored={summary.scored}, eligible={summary.eligible}, "
        f"attempted={summary.attempted}, applied={summary.applied}, prepared={summary.prepared}, "
        f"skipped={summary.skipped}, blocked={summary.blocked}, failed={summary.failed}"
    )

