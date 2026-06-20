"""AI-powered form filling for job application questions."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are filling a job application form for this candidate.

CANDIDATE PROFILE:
{profile_text}

Use only the candidate-provided facts above. Do not invent relocation,
authorization, salary, notice period, experience, or sponsorship answers.

Question: {question}
{options_line}

Give ONLY the answer, nothing else. Be concise.
If it asks for years of experience: just the number
If it asks yes/no: just Yes or No
If it asks for a number: just the number"""


class AIFormFiller:
    """Uses LLM to answer job application form questions."""

    def __init__(self, profile_text: str, provider_name: str = "auto"):
        self.profile_text = profile_text
        self.provider_name = provider_name
        self._provider = self._resolve_provider()

    def _resolve_provider(self) -> str | None:
        """Determine which AI provider is available. Returns provider name or None."""
        if self.provider_name != "auto":
            # Specific provider requested
            if self.provider_name == "groq" and os.environ.get("GROQ_API_KEY"):
                return "groq"
            if self.provider_name == "gemini" and os.environ.get("GEMINI_API_KEY"):
                return "gemini"
            if self.provider_name == "openai" and os.environ.get("OPENAI_API_KEY"):
                return "openai"
            return None

        # Auto: try in order Groq -> Gemini -> OpenAI
        if os.environ.get("GROQ_API_KEY"):
            return "groq"
        if os.environ.get("GEMINI_API_KEY"):
            return "gemini"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return None

    def answer(self, question: str, options: list[str] | None = None) -> str:
        """Answer a form question using AI + profile context.

        Returns the answer string, or empty string if AI is unavailable.
        Never raises — falls back gracefully.
        """
        if not self._provider:
            return ""

        options_line = f"Options: {options}" if options else ""
        prompt = _PROMPT_TEMPLATE.format(
            profile_text=self.profile_text,
            question=question,
            options_line=options_line,
        )

        try:
            if self._provider == "groq":
                return self._call_groq(prompt)
            elif self._provider == "gemini":
                return self._call_gemini(prompt)
            elif self._provider == "openai":
                return self._call_openai(prompt)
        except Exception as exc:
            logger.warning("AIFormFiller: %s failed (%s), returning empty", self._provider, exc)
        return ""

    def _call_groq(self, prompt: str) -> str:
        api_key = os.environ["GROQ_API_KEY"]
        model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 50,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return raw["choices"][0]["message"]["content"].strip()

    def _call_gemini(self, prompt: str) -> str:
        api_key = os.environ["GEMINI_API_KEY"]
        model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 50},
        }
        data = json.dumps(payload).encode("utf-8")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return raw["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _call_openai(self, prompt: str) -> str:
        api_key = os.environ["OPENAI_API_KEY"]
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 50,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return raw["choices"][0]["message"]["content"].strip()


def load_profile(workspace: Path) -> str:
    """Load profile.md from the workspace .applypilot directory."""
    profile_path = workspace / ".applypilot" / "profile.md"
    if profile_path.exists():
        return profile_path.read_text(encoding="utf-8")
    # Fallback: check workspace root
    alt = workspace / "profile.md"
    if alt.exists():
        return alt.read_text(encoding="utf-8")
    return ""
