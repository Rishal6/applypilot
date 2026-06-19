from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROVIDER_ENV_FILE = "provider.env"

PROVIDERS: dict[str, dict[str, Any]] = {
    "rules": {
        "label": "Rules",
        "mode": "free",
        "description": "No key, no network. Good for safe first-pass filtering.",
        "required": [],
    },
    "ollama": {
        "label": "Ollama local model",
        "mode": "local",
        "description": "Runs on the customer's machine. No API key leaves the device.",
        "required": ["OLLAMA_MODEL"],
        "defaults": {"OLLAMA_BASE_URL": "http://localhost:11434", "OLLAMA_MODEL": "llama3.1"},
    },
    "openai": {
        "label": "OpenAI-compatible API",
        "mode": "byok",
        "description": "Customer provides an OpenAI or compatible gateway key.",
        "required": ["OPENAI_API_KEY", "OPENAI_MODEL"],
        "defaults": {"OPENAI_BASE_URL": "https://api.openai.com"},
    },
    "groq": {
        "label": "Groq API",
        "mode": "byok",
        "description": "Customer provides a Groq API key.",
        "required": ["GROQ_API_KEY"],
        "defaults": {"GROQ_MODEL": "llama-3.1-8b-instant"},
    },
    "gemini": {
        "label": "Gemini API",
        "mode": "byok",
        "description": "Customer provides a Gemini API key.",
        "required": ["GEMINI_API_KEY"],
        "defaults": {"GEMINI_MODEL": "gemini-1.5-flash"},
    },
    "auto": {
        "label": "Auto BYOK fallback",
        "mode": "byok",
        "description": "Tries configured BYOK providers in order: Groq, Gemini, then OpenAI.",
        "required_any": ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"],
    },
    "managed_preview": {
        "label": "ApplyPilot managed preview",
        "mode": "managed",
        "description": "No customer key. Preview path for managed plans; currently rules-backed until hosted model routing is enabled.",
        "required": [],
    },
}

SECRET_KEYS = {"OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"}
ALLOWED_ENV_KEYS = {
    "APPLYPILOT_PROVIDER",
    "APPLYPILOT_FORM_PROVIDER",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
}


def provider_env_path(workspace: Path) -> Path:
    return workspace / PROVIDER_ENV_FILE


def load_local_provider_env(workspace: Path, override: bool = True) -> dict[str, str]:
    values = read_env_file(provider_env_path(workspace))
    for key, value in values.items():
        if key not in ALLOWED_ENV_KEYS:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Local ApplyPilot AI provider settings.",
        "# This file stays on the customer's machine. Do not commit it.",
    ]
    for key in sorted(ALLOWED_ENV_KEYS):
        value = values.get(key, "").strip()
        if value:
            lines.append(f"{key}={escape_env_value(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def escape_env_value(value: str) -> str:
    if any(ch.isspace() for ch in value) or any(ch in value for ch in ['"', "'", "#"]):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def configured_provider(workspace: Path) -> str:
    values = load_local_provider_env(workspace)
    provider = values.get("APPLYPILOT_PROVIDER") or os.environ.get("APPLYPILOT_PROVIDER", "rules")
    return normalize_provider(provider)


def normalize_provider(provider: str) -> str:
    normalized = (provider or "rules").strip().lower().replace("-", "_")
    aliases = {
        "managed": "managed_preview",
        "managed_api": "managed_preview",
        "hosted_model": "managed_preview",
        "hybrid": "managed_preview",
        "openai_compatible": "openai",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    return normalized


def save_provider_config(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    provider = normalize_provider(str(payload.get("provider") or "rules"))
    current = read_env_file(provider_env_path(workspace))
    values = {key: value for key, value in current.items() if key in ALLOWED_ENV_KEYS}
    values["APPLYPILOT_PROVIDER"] = provider
    values["APPLYPILOT_FORM_PROVIDER"] = form_provider_for(provider)

    defaults = dict(PROVIDERS[provider].get("defaults") or {})
    for key, value in defaults.items():
        values.setdefault(key, str(value))

    submitted = normalize_payload_values(provider, payload)
    for key, value in submitted.items():
        if key not in ALLOWED_ENV_KEYS:
            continue
        if key in SECRET_KEYS and not value:
            continue
        if value:
            values[key] = value
        elif key not in SECRET_KEYS:
            values.pop(key, None)

    write_env_file(provider_env_path(workspace), values)
    load_local_provider_env(workspace, override=True)
    return provider_status(workspace)


def form_provider_for(provider: str) -> str:
    if provider in {"openai", "groq", "gemini", "auto"}:
        return provider
    return "auto"


def normalize_payload_values(provider: str, payload: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    api_key = str(payload.get("api_key") or "").strip()
    model = str(payload.get("model") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    if provider == "ollama":
        if model:
            values["OLLAMA_MODEL"] = model
        if base_url:
            values["OLLAMA_BASE_URL"] = base_url.rstrip("/")
    elif provider == "openai":
        if api_key:
            values["OPENAI_API_KEY"] = api_key
        if model:
            values["OPENAI_MODEL"] = model
        if base_url:
            values["OPENAI_BASE_URL"] = base_url.rstrip("/")
    elif provider == "groq":
        if api_key:
            values["GROQ_API_KEY"] = api_key
        if model:
            values["GROQ_MODEL"] = model
    elif provider == "gemini":
        if api_key:
            values["GEMINI_API_KEY"] = api_key
        if model:
            values["GEMINI_MODEL"] = model
    return values


def provider_status(workspace: Path) -> dict[str, Any]:
    local_values = load_local_provider_env(workspace)
    selected = configured_provider(workspace)
    rows = []
    for name, definition in PROVIDERS.items():
        rows.append(status_row(name, definition, local_values))
    return {
        "selected": selected,
        "provider_env_file": str(provider_env_path(workspace)),
        "providers": rows,
    }


def status_row(name: str, definition: dict[str, Any], local_values: dict[str, str]) -> dict[str, Any]:
    required = list(definition.get("required") or [])
    required_any = list(definition.get("required_any") or [])
    configured = all(has_value(key, local_values) for key in required)
    if required_any:
        configured = any(has_value(key, local_values) for key in required_any)
    if not required and not required_any:
        configured = True

    row = {
        "name": name,
        "label": definition["label"],
        "mode": definition["mode"],
        "description": definition["description"],
        "configured": configured,
        "required": required,
        "required_any": required_any,
        "secrets_present": {key: has_value(key, local_values) for key in SECRET_KEYS if relevant_secret(name, key)},
        "model": model_for(name, local_values),
        "base_url": base_url_for(name, local_values),
    }
    if name == "ollama":
        row["reachable"] = ollama_reachable(str(row["base_url"] or "http://localhost:11434"))
    return row


def has_value(key: str, local_values: dict[str, str]) -> bool:
    return bool(local_values.get(key) or os.environ.get(key))


def relevant_secret(provider: str, key: str) -> bool:
    return (
        provider == "openai" and key == "OPENAI_API_KEY"
        or provider == "groq" and key == "GROQ_API_KEY"
        or provider == "gemini" and key == "GEMINI_API_KEY"
        or provider == "auto"
    )


def model_for(provider: str, local_values: dict[str, str]) -> str:
    keys = {
        "ollama": "OLLAMA_MODEL",
        "openai": "OPENAI_MODEL",
        "groq": "GROQ_MODEL",
        "gemini": "GEMINI_MODEL",
    }
    key = keys.get(provider)
    return str(local_values.get(key or "") or os.environ.get(key or "", ""))


def base_url_for(provider: str, local_values: dict[str, str]) -> str:
    keys = {
        "ollama": "OLLAMA_BASE_URL",
        "openai": "OPENAI_BASE_URL",
    }
    key = keys.get(provider)
    return str(local_values.get(key or "") or os.environ.get(key or "", ""))


def ollama_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=0.8) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False
