from __future__ import annotations

import json
import os
import ssl
import urllib.request

from .llm import build_scoring_prompt, parse_llm_evaluation
from ..models import Evaluation, Job, Preferences


class OpenAICompatibleProvider:
    """Provider for OpenAI-compatible chat completions APIs.

    Works for OpenAI and many compatible gateways when configured with:
    OPENAI_API_KEY, OPENAI_MODEL, and optional OPENAI_BASE_URL.
    """

    name = "openai"

    def __init__(self) -> None:
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = os.environ.get("OPENAI_MODEL", "")
        if not self.api_key or not self.model:
            raise SystemExit("Set OPENAI_API_KEY and OPENAI_MODEL to use --provider openai.")

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        prompt = build_scoring_prompt(profile_text, preferences, job)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{chat_completions_base(self.base_url)}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(request, timeout=120, context=ctx) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw["choices"][0]["message"]["content"]
        return parse_llm_evaluation(text, job, preferences, self.name)


def chat_completions_base(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"
