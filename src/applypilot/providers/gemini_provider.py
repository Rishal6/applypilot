from __future__ import annotations

import json
import os
import urllib.request

from .llm import build_scoring_prompt, parse_llm_evaluation
from ..models import Evaluation, Job, Preferences


class GeminiProvider:
    """Provider using Google's Gemini API.

    Uses GEMINI_API_KEY env var. Default model: gemini-1.5-flash.
    """

    name = "gemini"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        if not self.api_key:
            raise SystemExit("Set GEMINI_API_KEY to use --provider gemini.")

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        prompt = build_scoring_prompt(profile_text, preferences, job)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        data = json.dumps(payload).encode("utf-8")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        return parse_llm_evaluation(text, job, preferences, self.name)
