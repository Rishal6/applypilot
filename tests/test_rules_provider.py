import unittest

from applypilot.models import Job, Preferences
from applypilot.providers.rules import RulesProvider


class RulesProviderTest(unittest.TestCase):
    def test_shortlists_strong_ai_role(self):
        job = Job(
            id="1",
            title="Senior GenAI Engineer",
            company="Example",
            location="Remote",
            description="Python, RAG, LangChain, AWS Bedrock, FastAPI, agent workflows",
            easy_apply=True,
        )

        evaluation = RulesProvider().evaluate("", Preferences.defaults(), job)

        self.assertGreaterEqual(evaluation.score, 70)
        self.assertEqual(evaluation.decision, "shortlist")

    def test_rejects_avoid_role(self):
        job = Job(
            id="2",
            title="Marketing Intern",
            company="Example",
            location="Remote",
            description="Sales and marketing internship",
            easy_apply=True,
        )

        evaluation = RulesProvider().evaluate("", Preferences.defaults(), job)

        self.assertEqual(evaluation.decision, "reject")

    def test_does_not_reject_relevant_job_for_avoid_word_in_description(self):
        preferences = Preferences(
            target_roles=["Data Analyst"],
            preferred_skills=["Excel", "SQL", "Power BI", "data cleaning"],
            avoid_keywords=["Sales", "Marketing"],
            preferred_locations=["Bengaluru"],
        )
        job = Job(
            id="3",
            title="Data Analyst",
            company="Example",
            location="Bengaluru",
            description="Analyze sales data using Excel, SQL, Power BI, and data cleaning.",
            easy_apply=True,
        )

        evaluation = RulesProvider().evaluate("", preferences, job)

        self.assertEqual(evaluation.decision, "shortlist")
        self.assertGreaterEqual(evaluation.score, 70)


if __name__ == "__main__":
    unittest.main()
