from __future__ import annotations

import json
import os
import ssl
import urllib.request

from .llm import build_scoring_prompt, parse_llm_evaluation
from ..models import Evaluation, Job, Preferences


class GroqProvider:
    """Provider using the Groq API for fast inference.

    Uses GROQ_API_KEY env var. Default model: llama-3.1-8b-instant.
    """

    name = "groq"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        if not self.api_key:
            raise SystemExit("Set GROQ_API_KEY to use --provider groq.")

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        prompt = build_scoring_prompt(profile_text, preferences, job)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 200,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=120, context=ctx) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw["choices"][0]["message"]["content"]
        return parse_llm_evaluation(text, job, preferences, self.name)
