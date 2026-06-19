from __future__ import annotations

import json
import os
import urllib.request

from .llm import build_scoring_prompt, parse_llm_evaluation
from ..models import Evaluation, Job, Preferences


class OllamaProvider:
    name = "ollama"

    def __init__(self) -> None:
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", "llama3.1")

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        prompt = build_scoring_prompt(profile_text, preferences, job)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return parse_llm_evaluation(raw.get("response", ""), job, preferences, self.name)

