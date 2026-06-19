from __future__ import annotations

from .fallback import FallbackProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider
from .rules import RulesProvider
from .managed_preview import ManagedPreviewProvider


def get_provider(name: str):
    normalized = (name or "rules").strip().lower()
    if normalized == "rules":
        return RulesProvider()
    if normalized == "ollama":
        return OllamaProvider()
    if normalized in {"openai", "openai-compatible"}:
        return OpenAICompatibleProvider()
    if normalized == "groq":
        return GroqProvider()
    if normalized == "gemini":
        return GeminiProvider()
    if normalized == "auto":
        return FallbackProvider()
    if normalized in {"managed", "managed-preview", "managed_preview", "managed_api", "hosted_model", "hybrid"}:
        return ManagedPreviewProvider()
    if normalized in {"anthropic", "huggingface"}:
        raise SystemExit(
            f"Provider '{normalized}' is reserved in the architecture but not enabled yet. "
            "Use '--provider rules', '--provider ollama', '--provider openai', "
            "'--provider groq', '--provider gemini', or '--provider auto'."
        )
    raise SystemExit(f"Unknown provider: {name}")
