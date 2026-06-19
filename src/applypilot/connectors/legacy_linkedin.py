from __future__ import annotations

import json
from pathlib import Path

from ..models import Job


def load_legacy_jobs(path: str | Path) -> list[Job]:
    source = Path(path).expanduser()
    with source.open() as f:
        raw = json.load(f)

    if isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
        rows = raw["jobs"]
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    return [Job.from_dict(item, source="legacy_linkedin") for item in rows if isinstance(item, dict)]

