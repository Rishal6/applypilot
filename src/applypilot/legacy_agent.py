from __future__ import annotations

import json
import importlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import utc_now


LEGACY_SCRIPT_SETS = {
    "linkedin": ["auto_apply_chrome.py"],
    "naukri": ["auto_apply_naukri.py"],
    "leads": ["lead_hunter.py"],
    "apply": ["auto_apply_chrome.py", "auto_apply_naukri.py"],
    "all": ["auto_apply_chrome.py", "auto_apply_naukri.py", "lead_hunter.py"],
}

NATIVE_MODULE_SETS = {
    "linkedin": ["applypilot.working_agent.auto_apply_chrome"],
    "naukri": ["applypilot.working_agent.auto_apply_naukri"],
    "leads": ["applypilot.working_agent.lead_hunter"],
    "apply": [
        "applypilot.working_agent.auto_apply_chrome",
        "applypilot.working_agent.auto_apply_naukri",
    ],
    "all": [
        "applypilot.working_agent.auto_apply_chrome",
        "applypilot.working_agent.auto_apply_naukri",
        "applypilot.working_agent.lead_hunter",
    ],
}


@dataclass(slots=True)
class LegacyRunSummary:
    source: str
    log_file: str
    applied: int = 0
    skipped: int = 0
    leads: int = 0
    with_email: int = 0
    with_profile: int = 0
    drafts: int = 0
    completed_at: str = ""
    status: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "log_file": self.log_file,
            "applied": self.applied,
            "skipped": self.skipped,
            "leads": self.leads,
            "with_email": self.with_email,
            "with_profile": self.with_profile,
            "drafts": self.drafts,
            "completed_at": self.completed_at,
            "status": self.status,
        }


def resolve_legacy_dir(workspace: Path, override: str | Path | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    if os.environ.get("APPLYPILOT_LEGACY_AGENT_DIR"):
        return Path(os.environ["APPLYPILOT_LEGACY_AGENT_DIR"]).expanduser().resolve()
    return (workspace.parent.parent / "linkedin-agent").resolve()


def validate_legacy_dir(legacy_dir: Path) -> None:
    required = ["auto_apply_chrome.py", "auto_apply_naukri.py", "lead_hunter.py", "run_all.py"]
    missing = [name for name in required if not (legacy_dir / name).exists()]
    if missing:
        raise SystemExit(f"Legacy agent directory is missing: {', '.join(missing)}")


def scripts_for_mode(mode: str) -> list[str]:
    normalized = (mode or "all").strip().lower()
    if normalized not in LEGACY_SCRIPT_SETS:
        allowed = ", ".join(sorted(LEGACY_SCRIPT_SETS))
        raise SystemExit(f"Unknown daily mode: {mode}. Use one of: {allowed}")
    return list(LEGACY_SCRIPT_SETS[normalized])


def modules_for_mode(mode: str) -> list[str]:
    normalized = (mode or "all").strip().lower()
    if normalized not in NATIVE_MODULE_SETS:
        allowed = ", ".join(sorted(NATIVE_MODULE_SETS))
        raise SystemExit(f"Unknown daily mode: {mode}. Use one of: {allowed}")
    return list(NATIVE_MODULE_SETS[normalized])


def run_native_agent(mode: str, workspace: Path, dry_run: bool = False) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    env = os.environ.copy()
    env["APPLYPILOT_WORKSPACE"] = str(workspace)

    src_dir = Path(__file__).resolve().parents[1]
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(src_dir) if not current_pythonpath else f"{src_dir}{os.pathsep}{current_pythonpath}"
    )

    for module in modules_for_mode(mode):
        if dry_run:
            results.append((module, 0))
            continue
        if "__compiled__" in globals():
            previous_workspace = os.environ.get("APPLYPILOT_WORKSPACE")
            os.environ["APPLYPILOT_WORKSPACE"] = str(workspace)
            try:
                imported = importlib.import_module(module)
                imported.main()
                return_code = 0
            except SystemExit as exc:
                return_code = int(exc.code or 0)
            except Exception:
                return_code = 1
            finally:
                if previous_workspace is None:
                    os.environ.pop("APPLYPILOT_WORKSPACE", None)
                else:
                    os.environ["APPLYPILOT_WORKSPACE"] = previous_workspace
        else:
            completed = subprocess.run([sys.executable, "-m", module], cwd=workspace.parent, env=env)
            return_code = completed.returncode
        results.append((module, return_code))
        if return_code != 0:
            break
    return results


def run_legacy_agent(mode: str, legacy_dir: Path, dry_run: bool = False) -> list[tuple[str, int]]:
    validate_legacy_dir(legacy_dir)
    results: list[tuple[str, int]] = []
    for script in scripts_for_mode(mode):
        if dry_run:
            results.append((script, 0))
            continue
        completed = subprocess.run([sys.executable, str(legacy_dir / script)], cwd=legacy_dir)
        results.append((script, completed.returncode))
        if completed.returncode != 0:
            break
    return results


def sync_native_logs(workspace: Path) -> list[LegacyRunSummary]:
    summaries = parse_legacy_logs(workspace / "logs")
    report = {
        "updated_at": utc_now(),
        "native_dir": str(workspace),
        "totals": totals_for_runs(summaries),
        "runs": [summary.to_dict() for summary in summaries],
    }
    out = workspace / "reports" / "native_runs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return summaries


def sync_legacy_logs(workspace: Path, legacy_dir: Path) -> list[LegacyRunSummary]:
    validate_legacy_dir(legacy_dir)
    summaries = parse_legacy_logs(legacy_dir / "logs")
    report = {
        "updated_at": utc_now(),
        "legacy_dir": str(legacy_dir),
        "totals": totals_for_runs(summaries),
        "runs": [summary.to_dict() for summary in summaries],
    }
    out = workspace / "reports" / "legacy_runs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return summaries


def parse_legacy_logs(logs_dir: Path) -> list[LegacyRunSummary]:
    if not logs_dir.exists():
        return []
    summaries = [parse_legacy_log(path) for path in sorted(logs_dir.glob("*.log"))]
    return [summary for summary in summaries if summary.status != "unknown"]


def parse_legacy_log(path: Path) -> LegacyRunSummary:
    text = path.read_text(encoding="utf-8", errors="ignore")
    source = source_for_log(path.name)
    completed_at = completed_at_from_name(path.name)
    summary = LegacyRunSummary(
        source=source,
        log_file=str(path),
        completed_at=completed_at,
        status="unknown",
    )
    if source not in {"linkedin", "naukri", "leads"}:
        return summary

    applied_match = re.search(r"SESSION COMPLETE.*?Applied:\s*(\d+)", text, re.IGNORECASE)
    if applied_match:
        summary.applied = int(applied_match.group(1))
        summary.status = "complete"

    skipped_match = re.search(r"SESSION COMPLETE.*?Skipped:\s*(\d+)", text, re.IGNORECASE)
    if skipped_match:
        summary.skipped = int(skipped_match.group(1))

    leads_match = re.search(r"Total leads found:\s*(\d+)", text, re.IGNORECASE)
    if leads_match:
        summary.leads = int(leads_match.group(1))
        summary.status = "complete"

    email_match = re.search(r"With email:\s*(\d+)", text, re.IGNORECASE)
    if email_match:
        summary.with_email = int(email_match.group(1))

    profile_match = re.search(r"With profile:\s*(\d+)", text, re.IGNORECASE)
    if profile_match:
        summary.with_profile = int(profile_match.group(1))

    drafts_match = re.search(r"Drafts written:\s*(\d+)", text, re.IGNORECASE)
    if drafts_match:
        summary.drafts = int(drafts_match.group(1))

    if source == "linkedin" and summary.applied == 0:
        summary.applied = count_submissions(text)
        if summary.applied:
            summary.status = "partial"

    return summary


def source_for_log(name: str) -> str:
    if name.startswith("apply_"):
        return "linkedin"
    if name.startswith("naukri_"):
        return "naukri"
    if name.startswith("leads_"):
        return "leads"
    if name.startswith("service_") or name == "stdout.log":
        return "service"
    return "unknown"


def completed_at_from_name(name: str) -> str:
    match = re.search(r"(\d{8})_(\d{6})", name)
    if not match:
        return ""
    date, time_part = match.groups()
    return (
        f"{date[0:4]}-{date[4:6]}-{date[6:8]}T"
        f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}"
    )


def count_submissions(text: str) -> int:
    return len(re.findall(r">>\s*(?:APPLICATION\s+)?SUBMITTED", text, re.IGNORECASE))


def totals_for_runs(summaries: list[LegacyRunSummary]) -> dict:
    return {
        "linkedin_applied": sum(item.applied for item in summaries if item.source == "linkedin"),
        "naukri_applied": sum(item.applied for item in summaries if item.source == "naukri"),
        "leads": sum(item.leads for item in summaries if item.source == "leads"),
        "lead_emails": sum(item.with_email for item in summaries if item.source == "leads"),
        "runs": len(summaries),
    }
