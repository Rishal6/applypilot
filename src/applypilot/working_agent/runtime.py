from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def workspace() -> Path:
    configured = os.environ.get("APPLYPILOT_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    cwd = Path.cwd().resolve()
    return cwd if cwd.name == ".applypilot" else cwd / ".applypilot"


def logs_dir() -> Path:
    path = workspace() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir() -> Path:
    path = workspace() / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file(prefix: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return logs_dir() / f"{prefix}_{stamp}.log"
