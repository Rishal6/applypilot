import unittest

from applypilot.policy import AutomationPolicy, update_policy


class AutomationPolicyTest(unittest.TestCase):
    def test_auto_submit_mode_can_submit(self):
        policy = AutomationPolicy(mode="auto-submit")

        self.assertTrue(policy.can_auto_submit)
        self.assertFalse(policy.should_stop_before_submit)

    def test_review_mode_stops_before_submit(self):
        policy = AutomationPolicy(mode="review-only")

        self.assertFalse(policy.can_auto_submit)
        self.assertTrue(policy.should_stop_before_submit)

    def test_update_policy_validates_score(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "config.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit):
                update_policy(workspace, mode="auto-submit", min_score=101)


if __name__ == "__main__":
    unittest.main()
