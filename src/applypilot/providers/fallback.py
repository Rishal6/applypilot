from __future__ import annotations

import logging
import os
from typing import List

from .base import ScoringProvider
from ..models import Evaluation, Job, Preferences

logger = logging.getLogger(__name__)


class FallbackProvider:
    """Tries providers in order: Groq -> Gemini -> OpenAI.

    Skips providers whose API keys are not set. Falls back to the next
    provider on any error (rate limit, network, parsing).
    """

    name = "auto"

    def __init__(self) -> None:
        self._providers: List[ScoringProvider] = []
        self._build_chain()
        if not self._providers:
            raise SystemExit(
                "No AI providers available for --provider auto. "
                "Set at least one of: GROQ_API_KEY, GEMINI_API_KEY, "
                "or (OPENAI_API_KEY + OPENAI_MODEL)."
            )

    def _build_chain(self) -> None:
        if os.environ.get("GROQ_API_KEY"):
            from .groq_provider import GroqProvider

            self._providers.append(GroqProvider())
            logger.debug("FallbackProvider: Groq available")

        if os.environ.get("GEMINI_API_KEY"):
            from .gemini_provider import GeminiProvider

            self._providers.append(GeminiProvider())
            logger.debug("FallbackProvider: Gemini available")

        if os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_MODEL"):
            from .openai_compatible import OpenAICompatibleProvider

            self._providers.append(OpenAICompatibleProvider())
            logger.debug("FallbackProvider: OpenAI available")

    def evaluate(self, profile_text: str, preferences: Preferences, job: Job) -> Evaluation:
        errors: list[str] = []
        for provider in self._providers:
            try:
                logger.info("FallbackProvider: trying %s", provider.name)
                result = provider.evaluate(profile_text, preferences, job)
                logger.info("FallbackProvider: success with %s", provider.name)
                return result
            except Exception as exc:
                logger.warning(
                    "FallbackProvider: %s failed (%s), trying next", provider.name, exc
                )
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError(
            f"All providers failed in fallback chain: {'; '.join(errors)}"
        )
