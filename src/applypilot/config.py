from __future__ import annotations

import json
from pathlib import Path

from .models import Preferences


DEFAULT_WORKSPACE = ".applypilot"


def workspace_path(root: str | Path | None = None) -> Path:
    base = Path(root or ".").expanduser().resolve()
    return base if base.name == DEFAULT_WORKSPACE else base / DEFAULT_WORKSPACE


def load_preferences(workspace: Path) -> Preferences:
    config_file = workspace / "config.json"
    if not config_file.exists():
        return Preferences.defaults()
    with config_file.open() as f:
        raw = json.load(f)
    return Preferences.from_dict(raw.get("preferences", raw))


def write_default_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "queues").mkdir(exist_ok=True)
    (workspace / "reports").mkdir(exist_ok=True)

    profile_file = workspace / "profile.md"
    if not profile_file.exists():
        profile_file.write_text(
            "# Candidate Profile\n\n"
            "Replace this with the user's resume summary, skills, target roles, "
            "location preferences, compensation preferences, and constraints.\n",
            encoding="utf-8",
        )

    config_file = workspace / "config.json"
    if not config_file.exists():
        config_file.write_text(
            json.dumps({
                "product_mode": "review_first",
                "default_provider": "rules",
                "preferences": Preferences.defaults().to_dict(),
                "automation": {
                    "mode": "review-only",
                    "max_applications_per_day": 10,
                    "min_score_to_submit": 70,
                    "require_easy_apply": True,
                    "require_explicit_opt_in": True,
                    "can_auto_submit": False,
                    "should_stop_before_submit": True
                },
                "profile_answers": {
                    "first_name": "",
                    "last_name": "",
                    "email": "",
                    "phone": "",
                    "city": "",
                    "linkedin_url": "",
                    "website": "",
                    "years_experience": "",
                    "authorized_to_work": "Yes",
                    "sponsorship_needed": "No",
                    "willing_to_relocate": "Yes",
                    "notice_period": ""
                }
            }, indent=2),
            encoding="utf-8",
        )
