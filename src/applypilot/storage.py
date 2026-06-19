from __future__ import annotations

import json
from pathlib import Path

from .models import Evaluation, Job


class Store:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.queues_dir = workspace / "queues"
        self.reports_dir = workspace / "reports"
        self.jobs_file = self.queues_dir / "jobs.json"
        self.evaluations_file = self.queues_dir / "evaluations.json"

    def ensure(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.queues_dir.mkdir(exist_ok=True)
        self.reports_dir.mkdir(exist_ok=True)

    def load_jobs(self) -> list[Job]:
        if not self.jobs_file.exists():
            return []
        with self.jobs_file.open() as f:
            raw = json.load(f)
        return [Job.from_dict(item, source=item.get("source", "store")) for item in raw.get("jobs", [])]

    def save_jobs(self, jobs: list[Job]) -> None:
        self.ensure()
        payload = {"jobs": [job.to_dict() for job in dedupe_jobs(jobs)]}
        self.jobs_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def add_jobs(self, jobs: list[Job]) -> int:
        existing = self.load_jobs()
        before = len(existing)
        self.save_jobs(existing + jobs)
        return len(self.load_jobs()) - before

    def load_evaluations(self) -> list[Evaluation]:
        if not self.evaluations_file.exists():
            return []
        with self.evaluations_file.open() as f:
            raw = json.load(f)
        return [Evaluation.from_dict(item) for item in raw.get("evaluations", [])]

    def save_evaluations(self, evaluations: list[Evaluation]) -> None:
        self.ensure()
        by_job = {evaluation.job_id: evaluation for evaluation in evaluations}
        payload = {"evaluations": [item.to_dict() for item in by_job.values()]}
        self.evaluations_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def dedupe_jobs(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    out: list[Job] = []
    for job in jobs:
        key = job.id or f"{job.title.lower()}::{job.company.lower()}::{job.location.lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(job)
    return out

