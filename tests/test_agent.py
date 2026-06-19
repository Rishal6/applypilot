import unittest
import os
import tempfile
from pathlib import Path

from applypilot.agent import is_eligible
from applypilot.career import save_career_profile
from applypilot.models import Evaluation, Job
from applypilot.policy import AutomationPolicy, update_policy
from applypilot.working_agent.brain import evaluate_job


class AgentEligibilityTest(unittest.TestCase):
    def test_auto_submit_eligible_when_policy_passes(self):
        job = Job(id="1", title="AI Engineer", easy_apply=True)
        evaluation = Evaluation(job_id="1", score=80, decision="shortlist", reason="fit")
        policy = AutomationPolicy(mode="auto-submit", min_score_to_submit=70)

        self.assertTrue(is_eligible(job, evaluation, policy))

    def test_review_only_never_attempts_application(self):
        job = Job(id="1", title="AI Engineer", easy_apply=True)
        evaluation = Evaluation(job_id="1", score=90, decision="shortlist", reason="fit")
        policy = AutomationPolicy(mode="review-only", min_score_to_submit=70)

        self.assertFalse(is_eligible(job, evaluation, policy))

    def test_low_score_is_not_eligible(self):
        job = Job(id="1", title="AI Engineer", easy_apply=True)
        evaluation = Evaluation(job_id="1", score=50, decision="review", reason="partial")
        policy = AutomationPolicy(mode="auto-submit", min_score_to_submit=70)

        self.assertFalse(is_eligible(job, evaluation, policy))

    def test_working_agent_uses_saved_policy_threshold(self):
        previous = os.environ.get("APPLYPILOT_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp) / ".applypilot"
                save_career_profile(workspace, {
                    "target": "AI Engineer",
                    "skills": ["Python"],
                    "location": "Remote",
                })
                update_policy(workspace, mode="auto-submit", min_score=70)
                os.environ["APPLYPILOT_WORKSPACE"] = str(workspace)

                result = evaluate_job(
                    "Drone Research Engineer",
                    "Example",
                    "Mechanical drone design and simulation",
                )

            self.assertFalse(result["apply"])
            self.assertEqual(result["minimum_score"], 70)
        finally:
            if previous is None:
                os.environ.pop("APPLYPILOT_WORKSPACE", None)
            else:
                os.environ["APPLYPILOT_WORKSPACE"] = previous


if __name__ == "__main__":
    unittest.main()
