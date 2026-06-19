from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .dashboard import build_dashboard_data


DEFAULT_ENDPOINT = "http://127.0.0.1:8787"
AUTH_FILE = "saas_auth.json"


def auth_file(workspace: Path) -> Path:
    return workspace / AUTH_FILE


def save_auth(workspace: Path, auth: dict[str, Any]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    auth_file(workspace).write_text(json.dumps(auth, indent=2), encoding="utf-8")


def load_auth(workspace: Path) -> dict[str, Any]:
    path = auth_file(workspace)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def default_device_id() -> str:
    return socket.gethostname() or "applypilot-desktop"


def activate_device(
    endpoint: str,
    license_key: str,
    device_id: str | None = None,
    device_name: str | None = None,
) -> dict[str, Any]:
    payload = {
        "license_key": license_key,
        "device_id": device_id or default_device_id(),
        "device_name": device_name or default_device_id(),
    }
    return post_json(endpoint, "/api/v1/devices/activate", payload)


def sync_workspace(workspace: Path, endpoint: str, token: str) -> dict[str, Any]:
    dashboard = build_dashboard_data(workspace)
    return post_json(endpoint, "/api/v1/sync/dashboard", dashboard, token=token)


def fetch_me(endpoint: str, token: str) -> dict[str, Any]:
    return get_json(endpoint, "/api/v1/me", token=token)


def fetch_dashboard(endpoint: str, token: str) -> dict[str, Any]:
    return get_json(endpoint, "/api/v1/dashboard", token=token)


def get_json(endpoint: str, path: str, token: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url_for(endpoint, path), method="GET", headers=headers(token))
    return send(request)


def post_json(endpoint: str, path: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url_for(endpoint, path),
        data=body,
        method="POST",
        headers=headers(token) | {"Content-Type": "application/json"},
    )
    return send(request)


def send(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SaaS API error {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"SaaS API unavailable: {exc.reason}") from exc
    return json.loads(raw) if raw else {}


def headers(token: str | None = None) -> dict[str, str]:
    values = {"Accept": "application/json"}
    if token:
        values["Authorization"] = f"Bearer {token}"
    return values


def url_for(endpoint: str, path: str) -> str:
    return endpoint.rstrip("/") + "/" + path.lstrip("/")
