from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_MODES = {"review-only", "fill-only", "auto-submit"}


@dataclass(slots=True)
class AutomationPolicy:
    mode: str = "review-only"
    max_applications_per_day: int = 10
    min_score_to_submit: int = 70
    require_easy_apply: bool = True
    require_explicit_opt_in: bool = True

    @property
    def can_auto_submit(self) -> bool:
        return self.mode == "auto-submit"

    @property
    def should_stop_before_submit(self) -> bool:
        return self.mode != "auto-submit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "max_applications_per_day": self.max_applications_per_day,
            "min_score_to_submit": self.min_score_to_submit,
            "require_easy_apply": self.require_easy_apply,
            "require_explicit_opt_in": self.require_explicit_opt_in,
            "can_auto_submit": self.can_auto_submit,
            "should_stop_before_submit": self.should_stop_before_submit,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "AutomationPolicy":
        raw = raw or {}
        mode = str(raw.get("mode") or "review-only")
        if mode not in VALID_MODES:
            mode = "review-only"
        return cls(
            mode=mode,
            max_applications_per_day=int(raw.get("max_applications_per_day", 10)),
            min_score_to_submit=int(raw.get("min_score_to_submit", 70)),
            require_easy_apply=bool(raw.get("require_easy_apply", True)),
            require_explicit_opt_in=bool(raw.get("require_explicit_opt_in", True)),
        )


def load_policy(workspace: Path) -> AutomationPolicy:
    config = load_config(workspace)
    return AutomationPolicy.from_dict(config.get("automation") or config.get("safety"))


def save_policy(workspace: Path, policy: AutomationPolicy) -> None:
    config = load_config(workspace)
    config["automation"] = policy.to_dict()
    config.pop("safety", None)
    config_file(workspace).write_text(json.dumps(config, indent=2), encoding="utf-8")


def update_policy(
    workspace: Path,
    mode: str | None = None,
    daily_limit: int | None = None,
    min_score: int | None = None,
    require_easy_apply: bool | None = None,
) -> AutomationPolicy:
    current = load_policy(workspace)
    next_policy = AutomationPolicy(
        mode=mode or current.mode,
        max_applications_per_day=daily_limit if daily_limit is not None else current.max_applications_per_day,
        min_score_to_submit=min_score if min_score is not None else current.min_score_to_submit,
        require_easy_apply=require_easy_apply if require_easy_apply is not None else current.require_easy_apply,
        require_explicit_opt_in=True,
    )
    if next_policy.mode not in VALID_MODES:
        raise SystemExit(f"Invalid mode: {next_policy.mode}. Use one of: {', '.join(sorted(VALID_MODES))}")
    if next_policy.max_applications_per_day < 1:
        raise SystemExit("Daily limit must be at least 1.")
    if not 0 <= next_policy.min_score_to_submit <= 100:
        raise SystemExit("Minimum submit score must be between 0 and 100.")
    save_policy(workspace, next_policy)
    return next_policy


def load_config(workspace: Path) -> dict[str, Any]:
    path = config_file(workspace)
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def config_file(workspace: Path) -> Path:
    return workspace / "config.json"

