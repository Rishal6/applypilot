from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Lead:
    name: str
    headline: str = ""
    email: str = ""
    phone: str = ""
    profile_url: str = ""
    source: str = "hashtag"
    draft_email: str = ""
    post_snippet: str = ""
    found_at: str = field(default_factory=utc_now)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "headline": self.headline,
            "email": self.email,
            "phone": self.phone,
            "profile_url": self.profile_url,
            "source": self.source,
            "draft_email": self.draft_email,
            "post_snippet": self.post_snippet,
            "found_at": self.found_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Lead":
        return cls(
            name=str(raw.get("name") or ""),
            headline=str(raw.get("headline") or ""),
            email=str(raw.get("email") or ""),
            phone=str(raw.get("phone") or ""),
            profile_url=str(raw.get("profile_url") or ""),
            source=str(raw.get("source") or "hashtag"),
            draft_email=str(raw.get("draft_email") or ""),
            post_snippet=str(raw.get("post_snippet") or ""),
            found_at=str(raw.get("found_at") or utc_now()),
            status=str(raw.get("status") or "pending"),
        )


@dataclass(slots=True)
class Job:
    id: str
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    description: str = ""
    source: str = "manual"
    easy_apply: bool = False
    found_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], source: str = "manual") -> "Job":
        job_id = str(raw.get("job_id") or raw.get("id") or raw.get("url") or "").strip()
        title = str(raw.get("title") or "").strip()
        company = str(raw.get("company") or "").strip()
        fallback_id = f"{title.lower()}::{company.lower()}::{raw.get('location', '')}".strip(":")
        return cls(
            id=job_id or fallback_id,
            title=title,
            company=company,
            location=str(raw.get("location") or "").strip(),
            url=str(raw.get("url") or "").strip(),
            description=str(raw.get("description") or raw.get("content") or "").strip(),
            source=str(raw.get("source") or source),
            easy_apply=bool(raw.get("easy_apply")),
            found_at=str(raw.get("found_at") or utc_now()),
            metadata={k: v for k, v in raw.items() if k not in {
                "job_id", "id", "title", "company", "location", "url",
                "description", "content", "source", "easy_apply", "found_at",
            }},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "description": self.description,
            "source": self.source,
            "easy_apply": self.easy_apply,
            "found_at": self.found_at,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class Preferences:
    target_roles: list[str]
    preferred_skills: list[str]
    avoid_keywords: list[str]
    preferred_locations: list[str]
    min_score_to_shortlist: int = 70
    min_score_to_review: int = 45

    @classmethod
    def defaults(cls) -> "Preferences":
        return cls(
            target_roles=[
                "GenAI Engineer",
                "AI Engineer",
                "LLM Engineer",
                "AI Agent Developer",
                "RAG Engineer",
                "Applied AI Engineer",
                "AI Platform Engineer",
                "MLOps Engineer",
                "Prompt Engineer",
                "NLP Engineer",
            ],
            preferred_skills=[
                "Python",
                "LLM",
                "GenAI",
                "RAG",
                "LangChain",
                "LangGraph",
                "MCP",
                "AWS",
                "Bedrock",
                "FastAPI",
                "Docker",
                "Kubernetes",
                "Vector DB",
                "Pinecone",
                "FAISS",
                "Prompt Engineering",
                "Agent",
            ],
            avoid_keywords=[
                "Intern",
                "Fresher",
                "Junior",
                "Sales",
                "Marketing",
                "Customer Support",
                "Data Entry",
                "Manual Testing",
            ],
            preferred_locations=["Remote", "India", "Chennai", "Bangalore", "Hyderabad"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_roles": self.target_roles,
            "preferred_skills": self.preferred_skills,
            "avoid_keywords": self.avoid_keywords,
            "preferred_locations": self.preferred_locations,
            "min_score_to_shortlist": self.min_score_to_shortlist,
            "min_score_to_review": self.min_score_to_review,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Preferences":
        defaults = cls.defaults()
        return cls(
            target_roles=list(raw.get("target_roles") or defaults.target_roles),
            preferred_skills=list(raw.get("preferred_skills") or defaults.preferred_skills),
            avoid_keywords=list(raw.get("avoid_keywords") or defaults.avoid_keywords),
            preferred_locations=list(raw.get("preferred_locations") or defaults.preferred_locations),
            min_score_to_shortlist=int(raw.get("min_score_to_shortlist", defaults.min_score_to_shortlist)),
            min_score_to_review=int(raw.get("min_score_to_review", defaults.min_score_to_review)),
        )


@dataclass(slots=True)
class Evaluation:
    job_id: str
    score: int
    decision: str
    reason: str
    matching_terms: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    provider: str = "rules"
    evaluated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "score": self.score,
            "decision": self.decision,
            "reason": self.reason,
            "matching_terms": self.matching_terms,
            "missing_terms": self.missing_terms,
            "provider": self.provider,
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Evaluation":
        return cls(
            job_id=str(raw["job_id"]),
            score=int(raw["score"]),
            decision=str(raw["decision"]),
            reason=str(raw["reason"]),
            matching_terms=list(raw.get("matching_terms") or []),
            missing_terms=list(raw.get("missing_terms") or []),
            provider=str(raw.get("provider") or "unknown"),
            evaluated_at=str(raw.get("evaluated_at") or utc_now()),
        )

