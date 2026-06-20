import json
import tempfile
import unittest
from pathlib import Path

from applypilot.career import load_career_profile, resume_markdown, save_career_profile, tailored_resume_markdown


class CareerProfileTest(unittest.TestCase):
    def test_saves_profile_for_scoring_and_form_filling(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            saved = save_career_profile(workspace, {
                "name": "Rishal V S",
                "email": "rishal@example.com",
                "phone": "+91 99900 01111",
                "target": "AI Engineer and Python Backend Developer",
                "background": "Built RAG assistants and ERP automation.",
                "skills": ["Python", "FastAPI", "RAG"],
                "location": "Remote India or Bengaluru",
                "yearsExperience": "3",
                "noticePeriod": "15 days",
                "currentCtc": "7 LPA",
                "expectedCtc": "15 LPA",
            })
            config = json.loads((workspace / "config.json").read_text(encoding="utf-8"))
            profile_text = (workspace / "profile.md").read_text(encoding="utf-8")

        self.assertEqual(saved["name"], "Rishal V S")
        self.assertIn("AI Engineer", config["preferences"]["target_roles"])
        self.assertEqual(config["profile_answers"]["first_name"], "Rishal")
        self.assertEqual(config["profile_answers"]["last_name"], "V S")
        self.assertEqual(config["profile_answers"]["phone"], "+91 99900 01111")
        self.assertEqual(config["profile_answers"]["years_experience"], "3")
        self.assertEqual(config["profile_answers"]["notice_period"], "15 days")
        self.assertEqual(config["profile_answers"]["current_ctc"], "7 LPA")
        self.assertEqual(config["profile_answers"]["expected_ctc"], "15 LPA")
        self.assertIn("Built RAG assistants", profile_text)
        self.assertIn("Saved Application Answers", profile_text)
        self.assertIn("Years of experience: 3", profile_text)

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

    def test_tailors_resume_to_jd_without_inventing_missing_skills(self):
        profile = {
            "name": "Candidate",
            "target": "Python Backend Developer",
            "background": "Built FastAPI services for internal workflow automation.",
            "skills": ["Python", "FastAPI", "SQL"],
            "location": "Remote",
        }
        job = {
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Remote",
            "description": "Build Python FastAPI APIs on Kubernetes and AWS.",
        }

        resume = tailored_resume_markdown(profile, job)

        self.assertIn("ATS Target", resume)
        self.assertIn("Backend Engineer", resume)
        self.assertIn("FastAPI", resume)
        self.assertIn("Python", resume)
        self.assertIn("Missing or not evidenced", resume)
        self.assertIn("Kubernetes", resume)
        self.assertNotIn("Worked at Acme", resume)


if __name__ == "__main__":
    unittest.main()
