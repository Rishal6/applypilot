from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import write_default_workspace


PROFILE_FIELDS = {
    "name",
    "email",
    "phone",
    "target",
    "background",
    "location",
    "linkedin_url",
    "website",
    "resume_status",
}


def default_career_profile() -> dict[str, Any]:
    return {
        "name": "",
        "email": "",
        "phone": "",
        "target": "",
        "background": "",
        "skills": [],
        "location": "",
        "linkedin_url": "",
        "website": "",
        "resume_status": "",
    }


def load_career_profile(workspace: Path) -> dict[str, Any]:
    write_default_workspace(workspace)
    config = load_config(workspace)
    saved = config.get("career_profile") or {}
    profile = default_career_profile()
    if isinstance(saved, dict):
        profile.update(normalize_career_profile(saved))

    answers = config.get("profile_answers") or {}
    if not profile["name"]:
        profile["name"] = " ".join(
            item for item in [str(answers.get("first_name") or ""), str(answers.get("last_name") or "")] if item
        ).strip()
    profile["email"] = profile["email"] or str(answers.get("email") or "")
    profile["phone"] = profile["phone"] or str(answers.get("phone") or "")
    profile["location"] = profile["location"] or str(answers.get("city") or "")
    profile["linkedin_url"] = profile["linkedin_url"] or str(answers.get("linkedin_url") or "")
    profile["website"] = profile["website"] or str(answers.get("website") or "")
    return profile


def save_career_profile(workspace: Path, raw: dict[str, Any]) -> dict[str, Any]:
    write_default_workspace(workspace)
    profile = normalize_career_profile(raw)
    config = load_config(workspace)
    config["career_profile"] = profile
    config["preferences"] = merge_preferences(config.get("preferences") or {}, profile)
    config["profile_answers"] = merge_profile_answers(config.get("profile_answers") or {}, profile)
    write_config(workspace, config)
    (workspace / "profile.md").write_text(profile_markdown(profile), encoding="utf-8")
    return profile


def normalize_career_profile(raw: dict[str, Any]) -> dict[str, Any]:
    profile = default_career_profile()
    for field in PROFILE_FIELDS:
        value = raw.get(field)
        if field == "resume_status":
            value = value or raw.get("resumeStatus")
        profile[field] = clean_text(value, limit=8_000 if field == "background" else 500)
    skills_raw = raw.get("skills") or []
    if isinstance(skills_raw, str):
        skills_raw = re.split(r",|\n|·|\band\b", skills_raw, flags=re.IGNORECASE)
    profile["skills"] = dedupe([clean_text(item, limit=80) for item in skills_raw if clean_text(item, limit=80)])[:40]
    return profile


def profile_markdown(profile: dict[str, Any]) -> str:
    name = profile["name"] or "[Name not provided]"
    contact = " · ".join(
        item
        for item in [
            profile["email"],
            profile["phone"],
            profile["location"],
            profile["linkedin_url"],
            profile["website"],
        ]
        if item
    )
    skills = ", ".join(profile["skills"]) or "[Skills not provided]"
    return "\n".join([
        "# Candidate Profile",
        "",
        f"## {name}",
        contact or "[Contact details not provided]",
        "",
        "## Career Target",
        profile["target"] or "[Target role not provided]",
        "",
        "## Skills",
        skills,
        "",
        "## Background, Experience, Projects, and Education",
        profile["background"] or "[Background not provided]",
        "",
        "## Work Preference",
        profile["location"] or "[Location or remote preference not provided]",
        "",
        "> This profile contains candidate-provided facts. Do not invent employers, dates, qualifications, or achievements.",
        "",
    ])


def resume_markdown(profile: dict[str, Any]) -> str:
    name = profile["name"] or "[Your Name]"
    contact = " · ".join(
        item
        for item in [
            profile["email"],
            profile["phone"],
            profile["location"],
            profile["linkedin_url"],
            profile["website"],
        ]
        if item
    )
    skills = " · ".join(profile["skills"]) or "[Add your skills]"
    background_items = background_bullets(profile["background"])
    target = profile["target"] or "[Add target role]"
    summary = (
        f"Candidate targeting {target}, with experience and projects described below."
        if profile["background"]
        else f"[Add a short professional summary for {target}]"
    )
    return "\n".join([
        f"# {name}",
        contact or "[Email] · [Phone] · [Location]",
        "",
        "## Target Role",
        target,
        "",
        "## Professional Summary",
        summary,
        "",
        "## Skills",
        skills,
        "",
        "## Experience, Projects & Education",
        *(f"- {item}" for item in background_items),
        "",
        "## Work Preferences",
        f"- {profile['location'] or '[Add location, remote, or relocation preference]'}",
        "",
        "---",
        "Draft generated from candidate-provided information only. Verify and add dates, employers, qualifications, and measurable outcomes before applying.",
        "",
    ])


def merge_preferences(current: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    updated = dict(current)
    if profile["target"]:
        updated["target_roles"] = split_target_roles(profile["target"])
    if profile["skills"]:
        updated["preferred_skills"] = profile["skills"]
    if profile["location"]:
        updated["preferred_locations"] = split_locations(profile["location"])
    return updated


def merge_profile_answers(current: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    updated = dict(current)
    first_name, last_name = split_name(profile["name"])
    updated.update({
        "first_name": first_name,
        "last_name": last_name,
        "email": profile["email"],
        "phone": profile["phone"],
        "city": profile["location"],
        "linkedin_url": profile["linkedin_url"],
        "website": profile["website"],
    })
    return updated


def split_target_roles(value: str) -> list[str]:
    values = re.split(r",|/|\bor\b|\band\b", value, flags=re.IGNORECASE)
    cleaned = [clean_text(item, limit=120) for item in values if clean_text(item, limit=120)]
    return dedupe(cleaned or [clean_text(value, limit=120)])[:15]


def split_locations(value: str) -> list[str]:
    values = re.split(r",|/|\bor\b|\band\b", value, flags=re.IGNORECASE)
    return dedupe([clean_text(item, limit=120) for item in values if clean_text(item, limit=120)])[:15]


def split_name(value: str) -> tuple[str, str]:
    parts = value.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def background_bullets(value: str) -> list[str]:
    if not value:
        return ["[Add relevant work, projects, education, and measurable outcomes]"]
    items = re.split(r"\n+|(?<=[.!?])\s+", value)
    cleaned = [clean_text(re.sub(r"^[-•]\s*", "", item), limit=600) for item in items]
    return [item for item in cleaned if item][:12] or ["[Add relevant experience]"]


def clean_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def load_config(workspace: Path) -> dict[str, Any]:
    path = workspace / "config.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return raw if isinstance(raw, dict) else {}


def write_config(workspace: Path, config: dict[str, Any]) -> None:
    (workspace / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
