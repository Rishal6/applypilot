import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from applypilot.models import Job, Preferences
from applypilot.provider_config import provider_status, save_provider_config
from applypilot.providers import get_provider
from applypilot.providers.openai_compatible import chat_completions_base


class ProviderConfigTest(unittest.TestCase):
    def test_saves_ollama_config_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            status = save_provider_config(
                workspace,
                {
                    "provider": "ollama",
                    "base_url": "http://localhost:11434",
                    "model": "mistral",
                },
            )
            env_file = workspace / "provider.env"
            env_text = env_file.read_text(encoding="utf-8")

        self.assertEqual(status["selected"], "ollama")
        self.assertTrue(env_text)
        self.assertIn("APPLYPILOT_PROVIDER=ollama", env_text)
        self.assertIn("OLLAMA_MODEL=mistral", env_text)

    def test_byok_status_redacts_api_key(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            workspace = Path(tmp) / ".applypilot"
            status = save_provider_config(
                workspace,
                {
                    "provider": "openai",
                    "api_key": "sk-test-secret",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini",
                },
            )
            status_text = repr(provider_status(workspace))

        self.assertEqual(status["selected"], "openai")
        self.assertIn("'OPENAI_API_KEY': True", status_text)
        self.assertNotIn("sk-test-secret", status_text)

    def test_managed_preview_provider_scores_without_key(self):
        provider = get_provider("managed_preview")
        evaluation = provider.evaluate(
            "Python FastAPI developer",
            Preferences(target_roles=["Python Developer"], preferred_skills=["FastAPI"], avoid_keywords=[], preferred_locations=["Remote"]),
            Job(id="1", title="Python Developer", company="Acme", location="Remote", description="FastAPI services"),
        )

        self.assertEqual(evaluation.provider, "managed_preview")
        self.assertIn("Managed preview", evaluation.reason)

    def test_openai_base_url_accepts_v1_or_root(self):
        self.assertEqual(chat_completions_base("https://api.openai.com"), "https://api.openai.com/v1")
        self.assertEqual(chat_completions_base("https://api.openai.com/v1"), "https://api.openai.com/v1")


if __name__ == "__main__":
    unittest.main()
