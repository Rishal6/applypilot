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


ATS_STOPWORDS = {
    "about",
    "above",
    "across",
    "after",
    "again",
    "against",
    "also",
    "and",
    "apply",
    "based",
    "before",
    "being",
    "build",
    "business",
    "candidate",
    "company",
    "degree",
    "description",
    "develop",
    "employee",
    "engineer",
    "engineering",
    "experience",
    "full",
    "have",
    "help",
    "hiring",
    "including",
    "india",
    "knowledge",
    "looking",
    "manager",
    "minimum",
    "must",
    "onsite",
    "preferred",
    "requirements",
    "responsibilities",
    "role",
    "should",
    "skills",
    "team",
    "their",
    "this",
    "through",
    "using",
    "with",
    "work",
    "years",
    "your",
}


COMMON_ATS_TERMS = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "Go",
    "Golang",
    "C++",
    "C#",
    "SQL",
    "NoSQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "FastAPI",
    "Django",
    "Flask",
    "React",
    "Next.js",
    "Node.js",
    "Express",
    "REST API",
    "GraphQL",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "Terraform",
    "CI/CD",
    "GitHub Actions",
    "Linux",
    "Machine Learning",
    "ML",
    "AI",
    "GenAI",
    "LLM",
    "RAG",
    "LangChain",
    "LangGraph",
    "Vector DB",
    "Pinecone",
    "FAISS",
    "OpenAI",
    "Gemini",
    "Ollama",
    "MCP",
    "Prompt Engineering",
    "Data Analysis",
    "Excel",
    "Power BI",
    "Tableau",
    "ETL",
    "Airflow",
    "MLOps",
    "API",
    "Backend",
    "Frontend",
    "Full Stack",
    "Automation",
    "Testing",
    "QA",
    "Simulation",
    "Robotics",
    "CAD",
    "FEA",
    "Ansys",
    "SolidWorks",
    "MATLAB",
]

COMMON_ATS_CANONICAL = {term.casefold(): term for term in COMMON_ATS_TERMS}


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


def tailored_resume_markdown(profile: dict[str, Any], job: dict[str, Any]) -> str:
    """Build a truthful ATS-oriented resume draft for one job description.

    The draft highlights only facts already present in the candidate profile. JD
    terms that are not evidenced are listed as review gaps instead of being
    inserted into the resume body as claims.
    """

    normalized_profile = normalize_career_profile(profile)
    job_info = normalize_job(job)
    name = normalized_profile["name"] or "[Your Name]"
    contact = " · ".join(
        item
        for item in [
            normalized_profile["email"],
            normalized_profile["phone"],
            normalized_profile["location"],
            normalized_profile["linkedin_url"],
            normalized_profile["website"],
        ]
        if item
    )
    title = job_info["title"] or normalized_profile["target"] or "[Target role]"
    company = job_info["company"] or "[Company]"
    location = job_info["location"] or "[Location]"
    target = normalized_profile["target"] or title
    background_items = background_bullets(normalized_profile["background"])
    job_keywords = extract_ats_keywords(job_keyword_text(job_info))
    supported, missing = keyword_alignment(normalized_profile, job_keywords)
    skills = dedupe([*normalized_profile["skills"], *supported])
    skills_line = " · ".join(skills) or "[Add skills relevant to this JD]"
    supported_line = ", ".join(supported) or "No JD-specific keywords are clearly evidenced yet."
    missing_line = ", ".join(missing[:12]) or "None from the extracted JD terms."
    summary_terms = ", ".join(supported[:5])
    summary = (
        f"Candidate targeting {target}, aligned to {title}. "
        f"Relevant evidence includes {summary_terms}."
        if summary_terms
        else f"Candidate targeting {target}, aligned to {title}. Add more profile facts to strengthen JD alignment."
    )

    return "\n".join([
        f"# {name}",
        contact or "[Email] · [Phone] · [Location]",
        "",
        f"## Targeted Resume — {title}",
        "",
        "## ATS Target",
        f"- Role: {title}",
        f"- Company: {company}",
        f"- Location: {location}",
        "",
        "## Professional Summary",
        summary,
        "",
        "## Relevant Skills",
        skills_line,
        "",
        "## Experience, Projects & Education",
        *(f"- {item}" for item in background_items),
        "",
        "## JD Keyword Alignment",
        f"- Supported by profile: {supported_line}",
        f"- Missing or not evidenced yet: {missing_line}",
        "",
        "## Work Preferences",
        f"- {normalized_profile['location'] or '[Add location, remote, or relocation preference]'}",
        "",
        "---",
        "Tailored by ApplyPilot from candidate-provided facts and the selected JD. Remove review notes and add only true, evidenced details before submitting.",
        "",
    ])


def normalize_job(job: dict[str, Any]) -> dict[str, str]:
    return {
        "id": clean_text(job.get("id") or job.get("job_id"), limit=300),
        "title": clean_text(job.get("title"), limit=300),
        "company": clean_text(job.get("company"), limit=300),
        "location": clean_text(job.get("location"), limit=300),
        "description": clean_text(job.get("description") or job.get("content"), limit=20_000),
    }


def job_keyword_text(job: dict[str, Any]) -> str:
    return " ".join(
        clean_text(job.get(field), limit=20_000)
        for field in ["title", "description"]
        if clean_text(job.get(field), limit=20_000)
    )


def extract_ats_keywords(text: str) -> list[str]:
    candidates: list[str] = []
    for term in COMMON_ATS_TERMS:
        if keyword_in_text(term, text):
            candidates.append(term)
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9+#.]{2,}\b", text):
        normalized = normalize_keyword(token)
        if normalized.casefold() in ATS_STOPWORDS:
            continue
        candidates.append(normalized)
    return dedupe(candidates)[:30]


def keyword_in_text(keyword: str, text: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9+#.]){re.escape(keyword)}(?![A-Za-z0-9+#.])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def normalize_keyword(value: str) -> str:
    value = value.strip(".,;:()[]{}")
    canonical = COMMON_ATS_CANONICAL.get(value.casefold())
    if canonical:
        return canonical
    if value.isupper() or any(char.isupper() for char in value[1:]):
        return value
    return value.replace("_", " ").title()


def keyword_alignment(profile: dict[str, Any], keywords: list[str]) -> tuple[list[str], list[str]]:
    evidence = profile_evidence_text(profile).casefold()
    supported: list[str] = []
    missing: list[str] = []
    for keyword in keywords:
        key = keyword.casefold()
        if key and key in evidence:
            supported.append(keyword)
        else:
            missing.append(keyword)
    return dedupe(supported)[:18], dedupe(missing)[:18]


def profile_evidence_text(profile: dict[str, Any]) -> str:
    return " ".join([
        str(profile.get("target") or ""),
        str(profile.get("background") or ""),
        str(profile.get("location") or ""),
        " ".join(str(item) for item in profile.get("skills") or []),
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
