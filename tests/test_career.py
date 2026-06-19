import json
import tempfile
import unittest
from pathlib import Path

from applypilot.career import load_career_profile, resume_markdown, save_career_profile


class CareerProfileTest(unittest.TestCase):
    def test_saves_profile_for_scoring_and_form_filling(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            saved = save_career_profile(workspace, {
                "name": "Rishal V S",
                "email": "rishal@example.com",
                "target": "AI Engineer and Python Backend Developer",
                "background": "Built RAG assistants and ERP automation.",
                "skills": ["Python", "FastAPI", "RAG"],
                "location": "Remote India or Bengaluru",
            })
            config = json.loads((workspace / "config.json").read_text(encoding="utf-8"))
            profile_text = (workspace / "profile.md").read_text(encoding="utf-8")

        self.assertEqual(saved["name"], "Rishal V S")
        self.assertIn("AI Engineer", config["preferences"]["target_roles"])
        self.assertEqual(config["profile_answers"]["first_name"], "Rishal")
        self.assertEqual(config["profile_answers"]["last_name"], "V S")
        self.assertIn("Built RAG assistants", profile_text)

    def test_loads_saved_profile_and_builds_truthful_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "name": "Candidate",
                "target": "Data Analyst",
                "background": "Built a sales dashboard.",
                "skills": "Excel, SQL",
                "location": "Remote",
            })

            profile = load_career_profile(workspace)
            resume = resume_markdown(profile)

        self.assertEqual(profile["skills"], ["Excel", "SQL"])
        self.assertIn("Built a sales dashboard.", resume)
        self.assertNotIn("Acme", resume)


if __name__ == "__main__":
    unittest.main()
