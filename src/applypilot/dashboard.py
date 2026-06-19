from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .applications import ApplicationHistory
from .legacy_agent import sync_native_logs, totals_for_runs
from .models import Evaluation, Job
from .policy import load_policy
from .storage import Store


def build_dashboard_data(workspace: Path) -> dict[str, Any]:
    store = Store(workspace)
    jobs = store.load_jobs()
    evaluations = store.load_evaluations()
    history = ApplicationHistory(workspace).load()
    policy = load_policy(workspace)

    native_runs = sync_native_logs(workspace)
    legacy_report = load_json(workspace / "reports" / "legacy_runs.json")
    legacy_runs = list(legacy_report.get("runs") or [])
    legacy_totals = dict(legacy_report.get("totals") or {})
    native_totals = totals_for_runs(native_runs)
    profile_applied_total = (
        int(native_totals.get("linkedin_applied") or 0)
        + int(native_totals.get("naukri_applied") or 0)
    )
    imported_history_total = (
        int(legacy_totals.get("linkedin_applied") or 0)
        + int(legacy_totals.get("naukri_applied") or 0)
    )

    jobs_by_id = {job.id: job for job in jobs}
    evals_by_id = {evaluation.job_id: evaluation for evaluation in evaluations}
    completed_jobs = {record.job_id for record in history if record.status in {"applied", "skipped"}}
    shortlist = [item for item in evaluations if item.score >= policy.min_score_to_submit]
    today = datetime.now(timezone.utc).date().isoformat()
    applied_today = sum(1 for record in history if record.status == "applied" and record.created_at.startswith(today))

    provider_counts = Counter(item.provider for item in evaluations)
    decision_counts = Counter(item.decision for item in evaluations)
    status_counts = Counter(record.status for record in history)

    all_runs = [normalize_run(item, "native") for item in native_runs]
    all_runs.extend(normalize_run_dict(item, "legacy") for item in legacy_runs)
    all_runs = [item for item in all_runs if item]
    all_runs.sort(key=lambda item: item.get("completed_at") or "", reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "policy": policy.to_dict(),
        "summary": {
            "jobs": len(jobs),
            "evaluations": len(evaluations),
            "shortlisted": len(shortlist),
            "easy_apply_jobs": sum(1 for job in jobs if job.easy_apply),
            "application_records": len(history),
            "completed_jobs": len(completed_jobs),
            "applied_today": applied_today,
            "native_linkedin_applied": native_totals.get("linkedin_applied", 0),
            "native_naukri_applied": native_totals.get("naukri_applied", 0),
            "legacy_linkedin_applied": legacy_totals.get("linkedin_applied", 0),
            "legacy_naukri_applied": legacy_totals.get("naukri_applied", 0),
            "profile_applied_total": profile_applied_total,
            "imported_history_total": imported_history_total,
            "leads": native_totals.get("leads", 0) + legacy_totals.get("leads", 0),
            "lead_emails": native_totals.get("lead_emails", 0) + legacy_totals.get("lead_emails", 0),
        },
        "sources": source_rows(native_totals, legacy_totals),
        "runs": all_runs[:24],
        "series": run_series(all_runs),
        "jobs": job_rows(jobs, evals_by_id)[:40],
        "providers": [{"name": name or "unknown", "count": count} for name, count in provider_counts.most_common()],
        "decisions": [{"name": name or "unknown", "count": count} for name, count in decision_counts.most_common()],
        "statuses": [{"name": name or "unknown", "count": count} for name, count in status_counts.most_common()],
        "commands": [
            {"label": "LinkedIn", "command": "PYTHONPATH=src python3 -m applypilot --workspace . daily --mode linkedin"},
            {"label": "Naukri", "command": "PYTHONPATH=src python3 -m applypilot --workspace . daily --mode naukri"},
            {"label": "Apply", "command": "PYTHONPATH=src python3 -m applypilot --workspace . daily --mode apply"},
            {"label": "All", "command": "PYTHONPATH=src python3 -m applypilot --workspace . daily --mode all"},
            {"label": "Sync", "command": "PYTHONPATH=src python3 -m applypilot --workspace . sync-legacy"},
        ],
    }


def write_dashboard_data(workspace: Path, out: Path) -> dict[str, Any]:
    data = build_dashboard_data(workspace)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalize_run(run, origin: str) -> dict[str, Any]:
    return {
        "origin": origin,
        "source": run.source,
        "applied": run.applied,
        "skipped": run.skipped,
        "leads": run.leads,
        "lead_emails": run.with_email,
        "status": run.status,
        "completed_at": run.completed_at,
        "log_file": run.log_file,
    }


def normalize_run_dict(run: dict[str, Any], origin: str) -> dict[str, Any]:
    if not run:
        return {}
    return {
        "origin": origin,
        "source": run.get("source", ""),
        "applied": int(run.get("applied") or 0),
        "skipped": int(run.get("skipped") or 0),
        "leads": int(run.get("leads") or 0),
        "lead_emails": int(run.get("with_email") or 0),
        "status": run.get("status", ""),
        "completed_at": run.get("completed_at", ""),
        "log_file": run.get("log_file", ""),
    }


def source_rows(native_totals: dict[str, Any], legacy_totals: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": "LinkedIn",
            "native": int(native_totals.get("linkedin_applied") or 0),
            "legacy": int(legacy_totals.get("linkedin_applied") or 0),
            "leads": 0,
        },
        {
            "name": "Naukri",
            "native": int(native_totals.get("naukri_applied") or 0),
            "legacy": int(legacy_totals.get("naukri_applied") or 0),
            "leads": 0,
        },
        {
            "name": "Lead Hunter",
            "native": int(native_totals.get("leads") or 0),
            "legacy": int(legacy_totals.get("leads") or 0),
            "leads": int(native_totals.get("lead_emails") or 0) + int(legacy_totals.get("lead_emails") or 0),
        },
    ]


def run_series(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"applied": 0, "leads": 0, "runs": 0})
    for run in runs:
        day = (run.get("completed_at") or "")[:10] or "unknown"
        buckets[day]["applied"] += int(run.get("applied") or 0)
        buckets[day]["leads"] += int(run.get("leads") or 0)
        buckets[day]["runs"] += 1
    rows = [{"date": day, **values} for day, values in buckets.items() if day != "unknown"]
    rows.sort(key=lambda item: item["date"])
    return rows[-14:]


def job_rows(jobs: list[Job], evals_by_id: dict[str, Evaluation]) -> list[dict[str, Any]]:
    rows = []
    for job in jobs:
        evaluation = evals_by_id.get(job.id)
        rows.append({
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "source": job.source,
            "easy_apply": job.easy_apply,
            "score": evaluation.score if evaluation else 0,
            "decision": evaluation.decision if evaluation else "unscored",
            "reason": evaluation.reason if evaluation else "",
            "provider": evaluation.provider if evaluation else "",
            "url": job.url,
        })
    rows.sort(key=lambda item: item["score"], reverse=True)
    return rows
