from __future__ import annotations

import os

from .llm import build_scoring_prompt, parse_llm_evaluation
from ..models import Evaluation, Job, Preferences


class GroqProvider:
    """Provider using the Groq API for fast inference.

    Uses GROQ_API_KEY env var. Default model: llama-3.1-8b-instant.
    Requires: pip install groq
    """

    name = "groq"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        if not self.api_key:
            raise SystemExit("Set GROQ_API_KEY to use --provider groq.")

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        from groq import Groq
        client = Groq(api_key=self.api_key)
        prompt = build_scoring_prompt(profile_text, preferences, job)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        text = resp.choices[0].message.content
        return parse_llm_evaluation(text, job, preferences, self.name)
