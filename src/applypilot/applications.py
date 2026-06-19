from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import utc_now


COMPLETED_STATUSES = {"applied", "skipped"}


@dataclass(slots=True)
class ApplicationRecord:
    job_id: str
    status: str
    reason: str = ""
    score: int = 0
    mode: str = ""
    connector: str = ""
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "reason": self.reason,
            "score": self.score,
            "mode": self.mode,
            "connector": self.connector,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ApplicationRecord":
        return cls(
            job_id=str(raw.get("job_id") or ""),
            status=str(raw.get("status") or ""),
            reason=str(raw.get("reason") or ""),
            score=int(raw.get("score") or 0),
            mode=str(raw.get("mode") or ""),
            connector=str(raw.get("connector") or ""),
            created_at=str(raw.get("created_at") or utc_now()),
            metadata=dict(raw.get("metadata") or {}),
        )


class ApplicationHistory:
    def __init__(self, workspace: Path):
        self.path = workspace / "queues" / "applications.json"

    def load(self) -> list[ApplicationRecord]:
        if not self.path.exists():
            return []
        with self.path.open() as f:
            raw = json.load(f)
        return [ApplicationRecord.from_dict(item) for item in raw.get("applications", [])]

    def append(self, record: ApplicationRecord) -> None:
        records = self.load()
        records.append(record)
        self.save(records)

    def save(self, records: list[ApplicationRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"applications": [record.to_dict() for record in records]}, indent=2),
            encoding="utf-8",
        )

    def completed_job_ids(self) -> set[str]:
        return {
            record.job_id for record in self.load()
            if record.status in COMPLETED_STATUSES and record.job_id
        }

    def applied_today_count(self) -> int:
        today = utc_now()[:10]
        return len([
            record for record in self.load()
            if record.status == "applied" and record.created_at.startswith(today)
        ])
