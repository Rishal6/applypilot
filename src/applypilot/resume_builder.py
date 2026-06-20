"""
Resume Builder — generates tailored PDF resumes for specific job descriptions.

Falls back to Markdown output if fpdf2 is not installed.
Usage:
    from applypilot.resume_builder import ResumeBuilder
    builder = ResumeBuilder()
    path = builder.build_resume(profile, job, output_path)
"""

from __future__ import annotations

import json
import os
import re
import textwrap
import urllib.request
from pathlib import Path
from typing import Any

from .models import Job

try:
    from fpdf import FPDF

    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False


# ---------------------------------------------------------------------------
# Profile loader — reads from workspace profile.md or resume_data.json
# ---------------------------------------------------------------------------


def load_profile(workspace: Path) -> dict[str, Any]:
    """Load user profile from workspace resume_data.json or profile.md.

    Returns a dict with keys:
        name, tagline, contact, summary, experience (list), skills (dict),
        projects (list), education (list), certifications (list)
    """
    resume_json = workspace / "resume_data.json"
    if resume_json.exists():
        with resume_json.open() as f:
            return json.load(f)

    # Fallback: parse profile.md into a minimal structure
    profile_md = workspace / "profile.md"
    if profile_md.exists():
        text = profile_md.read_text(encoding="utf-8")
        return {"name": "Candidate", "raw_text": text}

    return {"name": "Candidate", "raw_text": ""}


# ---------------------------------------------------------------------------
# AI tailoring — rewrites resume bullets for a specific JD
# ---------------------------------------------------------------------------


def _call_gemini(prompt: str) -> str:
    """Call Gemini API. Requires GEMINI_API_KEY env var."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    if not api_key:
        return ""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return raw["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(prompt: str) -> str:
    """Call Groq API. Requires GROQ_API_KEY env var."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    model = os.environ.get("GROQ_MODEL", "llama-3.1-70b-versatile")
    if not api_key:
        return ""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return raw["choices"][0]["message"]["content"]


def _call_llm(prompt: str) -> str:
    """Try available LLM providers in order: Gemini, Groq, OpenAI-compatible."""
    for caller in (_call_gemini, _call_groq):
        try:
            result = caller(prompt)
            if result:
                return result
        except Exception:
            continue
    return ""


def tailor_for_job(base_resume_text: str, job_description: str) -> str:
    """Use AI to rewrite resume bullets tailored to a specific job description.

    Returns the tailored resume text as a string. If no LLM is available,
    returns the base text unchanged.
    """
    prompt = f"""You are a resume tailoring expert. Given the candidate's base resume and a job description,
rewrite the resume content to highlight the most relevant experience, skills, and achievements for THIS specific job.

Rules:
- Keep all facts truthful — do NOT invent experience or skills the candidate doesn't have
- Reorder bullets to put most relevant first
- Rewrite bullet language to mirror the JD's terminology where truthful
- Adjust the professional summary to target this specific role
- Keep it concise — max 6 bullets per role
- Return ONLY the rewritten resume content as plain text (no JSON, no markdown headers)

BASE RESUME:
{base_resume_text[:8000]}

JOB DESCRIPTION:
{job_description[:4000]}

TAILORED RESUME:"""

    result = _call_llm(prompt)
    return result if result else base_resume_text


# ---------------------------------------------------------------------------
# PDF generation (fpdf2-based, mirrors the original ResumeBuilder)
# ---------------------------------------------------------------------------


class _PDFBuilder:
    """Internal PDF builder using fpdf2. Only instantiated when fpdf2 is available."""

    def __init__(self) -> None:
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=10)

    def header_section(self, name: str, tagline: str, contact: str) -> None:
        self.pdf.set_font("Helvetica", "B", 18)
        self.pdf.cell(0, 8, name, new_x="LMARGIN", new_y="NEXT", align="C")
        self.pdf.set_font("Helvetica", "", 10)
        self.pdf.cell(0, 5, tagline, new_x="LMARGIN", new_y="NEXT", align="C")
        self.pdf.set_font("Helvetica", "", 9)
        self.pdf.cell(0, 5, contact, new_x="LMARGIN", new_y="NEXT", align="C")
        self.pdf.ln(4)
        self.pdf.line(10, self.pdf.get_y(), 200, self.pdf.get_y())
        self.pdf.ln(3)

    def section_title(self, title: str) -> None:
        self.pdf.set_font("Helvetica", "B", 11)
        self.pdf.set_fill_color(240, 240, 240)
        self.pdf.cell(0, 7, f"  {title}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.pdf.ln(2)

    def summary_section(self, text: str) -> None:
        self.pdf.set_font("Helvetica", "", 9)
        self.pdf.multi_cell(0, 4.5, text)
        self.pdf.ln(2)

    def experience_entry(
        self, title: str, company: str, duration: str, location: str, bullets: list[str]
    ) -> None:
        self.pdf.set_font("Helvetica", "B", 10)
        self.pdf.cell(0, 5, f"{title} | {company}", new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_font("Helvetica", "I", 9)
        self.pdf.cell(0, 4, f"{duration} | {location}", new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_font("Helvetica", "", 9)
        for bullet in bullets:
            lines = textwrap.wrap(bullet, width=95)
            for i, line in enumerate(lines):
                prefix = "  -  " if i == 0 else "      "
                self.pdf.cell(0, 4.5, prefix + line, new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(2)

    def skills_section(self, skills_dict: dict[str, str]) -> None:
        col_width = 28
        for category, skills in skills_dict.items():
            self.pdf.set_font("Helvetica", "B", 9)
            self.pdf.cell(col_width, 4.5, f"{category}:")
            self.pdf.set_font("Helvetica", "", 9)
            remaining = self.pdf.w - self.pdf.get_x() - self.pdf.r_margin
            self.pdf.multi_cell(remaining, 4.5, skills)
            self.pdf.ln(0.5)
        self.pdf.ln(1)

    def education_entry(self, degree: str, school: str, year: str) -> None:
        self.pdf.set_font("Helvetica", "B", 9)
        self.pdf.cell(0, 4.5, degree, new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_font("Helvetica", "", 9)
        self.pdf.cell(0, 4.5, f"{school} | {year}", new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(1)

    def cert_entry(self, name: str, issuer: str, year: str) -> None:
        self.pdf.set_font("Helvetica", "", 9)
        self.pdf.cell(0, 4.5, f"  -  {name} - {issuer} ({year})", new_x="LMARGIN", new_y="NEXT")

    def project_entry(self, name: str, desc: str) -> None:
        self.pdf.set_font("Helvetica", "B", 9)
        self.pdf.cell(0, 4.5, f"  -  {name}", new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_font("Helvetica", "", 9)
        lines = textwrap.wrap(desc, width=90)
        for line in lines:
            self.pdf.cell(0, 4.5, f"      {line}", new_x="LMARGIN", new_y="NEXT")

    def output(self, path: str | Path) -> None:
        self.pdf.output(str(path))


# ---------------------------------------------------------------------------
# Markdown fallback
# ---------------------------------------------------------------------------


def _build_markdown(profile: dict[str, Any]) -> str:
    """Build a Markdown resume from profile data."""
    lines: list[str] = []
    name = profile.get("name", "Candidate")
    tagline = profile.get("tagline", "")
    contact = profile.get("contact", "")

    lines.append(f"# {name}")
    if tagline:
        lines.append(f"**{tagline}**")
    if contact:
        lines.append(f"\n{contact}")
    lines.append("")

    summary = profile.get("summary", "")
    if summary:
        lines.append("## Professional Summary")
        lines.append(summary)
        lines.append("")

    experiences = profile.get("experience", [])
    if experiences:
        lines.append("## Experience")
        for exp in experiences:
            lines.append(f"### {exp.get('title', '')} | {exp.get('company', '')}")
            lines.append(f"*{exp.get('duration', '')} | {exp.get('location', '')}*")
            for bullet in exp.get("bullets", []):
                lines.append(f"- {bullet}")
            lines.append("")

    skills = profile.get("skills", {})
    if skills:
        lines.append("## Technical Skills")
        for category, skill_text in skills.items():
            lines.append(f"**{category}:** {skill_text}")
        lines.append("")

    projects = profile.get("projects", [])
    if projects:
        lines.append("## Projects")
        for proj in projects:
            lines.append(f"- **{proj.get('name', '')}**: {proj.get('description', '')}")
        lines.append("")

    education = profile.get("education", [])
    if education:
        lines.append("## Education")
        for edu in education:
            lines.append(f"- {edu.get('degree', '')} — {edu.get('school', '')} ({edu.get('year', '')})")
        lines.append("")

    certifications = profile.get("certifications", [])
    if certifications:
        lines.append("## Certifications")
        for cert in certifications:
            lines.append(f"- {cert.get('name', '')} — {cert.get('issuer', '')} ({cert.get('year', '')})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ResumeBuilder:
    """Generates PDF (or Markdown fallback) resumes, optionally tailored to a JD."""

    def build_resume(
        self,
        profile: dict[str, Any],
        job: Job | None = None,
        output_path: Path | None = None,
    ) -> Path:
        """Build a resume PDF (or .md if fpdf2 unavailable).

        Args:
            profile: Dict with name, tagline, contact, summary, experience, skills, etc.
            job: Optional Job to tailor the resume for.
            output_path: Where to write the file. Defaults to cwd.

        Returns:
            Path to the generated file.
        """
        # Determine output path
        if output_path is None:
            ext = ".pdf" if HAS_FPDF else ".md"
            filename = self._safe_filename(profile, job) + ext
            output_path = Path.cwd() / filename
        else:
            output_path = Path(output_path)
            if not HAS_FPDF and output_path.suffix == ".pdf":
                output_path = output_path.with_suffix(".md")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Tailor for job if provided
        working_profile = dict(profile)
        if job and job.description:
            base_text = _build_markdown(profile)
            tailored_text = tailor_for_job(base_text, job.description)
            if tailored_text != base_text:
                working_profile = self._parse_tailored_into_profile(
                    tailored_text, profile
                )

        if HAS_FPDF and output_path.suffix == ".pdf":
            self._build_pdf(working_profile, output_path)
        else:
            md_content = _build_markdown(working_profile)
            output_path.write_text(md_content, encoding="utf-8")

        return output_path

    def _build_pdf(self, profile: dict[str, Any], output_path: Path) -> None:
        """Generate PDF using fpdf2."""
        builder = _PDFBuilder()
        builder.pdf.add_page()

        # Header
        builder.header_section(
            profile.get("name", "Candidate"),
            profile.get("tagline", ""),
            profile.get("contact", ""),
        )

        # Summary
        summary = profile.get("summary", "")
        if summary:
            builder.section_title("PROFESSIONAL SUMMARY")
            builder.summary_section(summary)

        # Experience
        experiences = profile.get("experience", [])
        if experiences:
            builder.section_title("EXPERIENCE")
            for exp in experiences:
                builder.experience_entry(
                    exp.get("title", ""),
                    exp.get("company", ""),
                    exp.get("duration", ""),
                    exp.get("location", ""),
                    exp.get("bullets", [])[:6],
                )

        # Skills
        skills = profile.get("skills", {})
        if skills:
            builder.section_title("TECHNICAL SKILLS")
            builder.skills_section(skills)

        # Projects
        projects = profile.get("projects", [])
        if projects:
            builder.section_title("PROJECTS")
            for proj in projects:
                builder.project_entry(
                    proj.get("name", ""),
                    proj.get("description", ""),
                )

        # Education
        education = profile.get("education", [])
        if education:
            builder.section_title("EDUCATION")
            for edu in education:
                builder.education_entry(
                    edu.get("degree", ""),
                    edu.get("school", ""),
                    edu.get("year", ""),
                )

        # Certifications
        certifications = profile.get("certifications", [])
        if certifications:
            builder.section_title("CERTIFICATIONS")
            for cert in certifications:
                builder.cert_entry(
                    cert.get("name", ""),
                    cert.get("issuer", ""),
                    cert.get("year", ""),
                )

        builder.output(output_path)

    def _parse_tailored_into_profile(
        self, tailored_text: str, base_profile: dict[str, Any]
    ) -> dict[str, Any]:
        """Best-effort parse of AI-tailored text back into profile structure.

        If parsing fails, returns base_profile with updated summary from the tailored text.
        """
        # Use the base profile structure but try to extract an updated summary
        result = dict(base_profile)

        # Try to extract summary (first paragraph after any heading)
        lines = tailored_text.strip().split("\n")
        summary_lines: list[str] = []
        in_summary = False
        for line in lines:
            stripped = line.strip()
            if "summary" in stripped.lower() and (stripped.startswith("#") or stripped.startswith("**")):
                in_summary = True
                continue
            if in_summary:
                if stripped.startswith("#") or stripped.startswith("**") or stripped.startswith("##"):
                    break
                if stripped:
                    summary_lines.append(stripped)

        if summary_lines:
            result["summary"] = " ".join(summary_lines)

        return result

    def _safe_filename(self, profile: dict[str, Any], job: Job | None) -> str:
        """Generate a safe filename from profile name and optional job."""
        name = profile.get("name", "resume").replace(" ", "_")
        if job:
            company = re.sub(r"[^a-zA-Z0-9]", "_", job.company or "company")
            return f"{name}_{company}_resume"
        return f"{name}_resume"
