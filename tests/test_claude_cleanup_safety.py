import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from applypilot.career import save_career_profile
from applypilot.connectors.naukri_browser import NaukriBrowserConnector
from applypilot.connectors.naukri_search import NaukriSearcher
from applypilot.leads import LeadHunter
from applypilot.models import Evaluation, Job, Lead
from applypilot.policy import AutomationPolicy
from applypilot.premium import PremiumFeatures


FORBIDDEN_DEVELOPER_FACTS = ["Rishal", "Amazon", "97154", "10,000"]


class ClaudeCleanupSafetyTest(unittest.TestCase):
    def test_lead_draft_uses_customer_profile_not_developer_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "+91 99900 01111",
                "target": "Python Backend Developer",
                "background": "Built FastAPI services for logistics automation.",
                "skills": ["Python", "FastAPI", "PostgreSQL"],
                "location": "Remote India",
            })
            hunter = LeadHunter(workspace, max_searches=0)
            captured: dict[str, str] = {}

            def fake_ai(prompt: str) -> str:
                captured["prompt"] = prompt
                return "draft"

            hunter._ask_ai = fake_ai  # type: ignore[method-assign]
            draft = hunter._draft_email(Lead(
                name="Alex Recruiter",
                headline="Hiring Manager",
                email="alex@example.com",
                post_snippet="We are hiring Python backend developers for API work.",
            ))

        self.assertEqual(draft, "draft")
        prompt = captured["prompt"]
        self.assertIn("Jane Doe", prompt)
        self.assertIn("Python Backend Developer", prompt)
        self.assertIn("jane@example.com", prompt)
        for forbidden in FORBIDDEN_DEVELOPER_FACTS:
            self.assertNotIn(forbidden, prompt)

    def test_premium_drafts_are_customer_profile_driven_and_sending_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "target": "Data Analyst",
                "background": "Built SQL dashboards for sales reporting.",
                "skills": ["SQL", "Excel", "Power BI"],
                "location": "Bengaluru",
            })
            premium = PremiumFeatures(workspace)
            note = premium._generate_connect_note({"name": "Alex Recruiter", "headline": "Talent recruiter"})
            inmail = premium._generate_inmail({"name": "Alex Recruiter", "headline": "Talent recruiter"})

        combined = f"{note}\n{inmail}"
        self.assertIn("Jane Doe", combined)
        self.assertIn("Data Analyst", combined)
        self.assertIn("jane@example.com", combined)
        self.assertEqual(premium._connect_with_viewer({"name": "Alex Recruiter"}), "blocked")
        self.assertEqual(premium._send_inmail({"name": "Alex Recruiter"}), "blocked")
        for forbidden in FORBIDDEN_DEVELOPER_FACTS:
            self.assertNotIn(forbidden, combined)

    def test_premium_processes_viewers_as_drafts_not_sent_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "name": "Jane Doe",
                "target": "Python Backend Developer",
                "skills": ["Python"],
            })
            premium = PremiumFeatures(workspace, max_connects=2)

            with patch("applypilot.premium.human_pause", lambda *_args: None):
                premium._process_viewers([
                    {"name": "Alex Recruiter", "headline": "Python recruiter", "profile_url": "https://linkedin.com/in/alex"},
                    {"name": "Unrelated Person", "headline": "Chef", "profile_url": "https://linkedin.com/in/chef"},
                ])

            drafts = workspace / "premium" / "connection_drafts.csv"
            sent = workspace / "premium" / "connections_sent.csv"

            self.assertEqual(premium._connect_drafts, 1)
            self.assertTrue(drafts.exists())
            self.assertFalse(sent.exists())

    def test_naukri_fill_only_stops_before_clicking_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            connector = NaukriBrowserConnector(workspace)
            calls: list[str] = []

            connector._navigate = lambda url: calls.append(f"navigate:{url}")  # type: ignore[method-assign]
            connector._is_already_applied = lambda: False  # type: ignore[method-assign]
            connector._click_apply = lambda: self.fail("fill-only must not click Apply")  # type: ignore[method-assign]
            job = Job(id="1", title="Python Developer", url="https://www.naukri.com/job")
            evaluation = Evaluation(job_id="1", score=90, decision="shortlist", reason="match")
            policy = AutomationPolicy(mode="fill-only", min_score_to_submit=70)

            with patch("applypilot.connectors.naukri_browser.platform.system", return_value="Darwin"):
                with patch("applypilot.connectors.naukri_browser.human_pause", lambda *_args: None):
                    record = connector.apply(job, evaluation, policy)

        self.assertEqual(record.status, "prepared")
        self.assertIn("stopped before clicking Apply", record.reason)
        self.assertEqual(calls, ["navigate:https://www.naukri.com/job"])

    def test_naukri_has_no_personal_answer_defaults_and_profile_search_has_no_experience_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "name": "Jane Doe",
                "target": "Simulation Engineer",
                "skills": ["Ansys", "MATLAB"],
                "location": "Pune",
            })
            connector = NaukriBrowserConnector(workspace)
            searcher = NaukriSearcher(workspace)
            url = searcher._build_url("Simulation Engineer")
            queries = searcher._profile_queries()

        self.assertNotIn("current ctc", connector._chatbot_answers)
        self.assertNotIn("expected ctc", connector._chatbot_answers)
        self.assertNotIn("experience", connector._chatbot_answers)
        self.assertIn("Simulation Engineer", queries)
        self.assertIn("k=Simulation+Engineer", url)
        self.assertNotIn("experience=3", url)

    def test_naukri_reuses_saved_application_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "name": "Jane Doe",
                "target": "Simulation Engineer",
                "skills": ["Ansys"],
                "yearsExperience": "4",
                "noticePeriod": "30 days",
                "currentCtc": "8 LPA",
                "expectedCtc": "14 LPA",
                "willingToRelocate": "No",
            })
            connector = NaukriBrowserConnector(workspace)

        self.assertEqual(connector._chatbot_answers["experience"], "4")
        self.assertEqual(connector._chatbot_answers["notice period"], "30 days")
        self.assertEqual(connector._chatbot_answers["current ctc"], "8 LPA")
        self.assertEqual(connector._chatbot_answers["expected ctc"], "14 LPA")
        self.assertEqual(connector._chatbot_answers["relocate"], "No")


if __name__ == "__main__":
    unittest.main()
