import unittest

from applypilot.applications import ApplicationHistory, ApplicationRecord


class ApplicationHistoryTest(unittest.TestCase):
    def test_blocked_jobs_are_retryable(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            history = ApplicationHistory(Path(tmp))
            history.append(ApplicationRecord(job_id="1", status="blocked"))
            history.append(ApplicationRecord(job_id="2", status="applied"))

            completed = history.completed_job_ids()

        self.assertNotIn("1", completed)
        self.assertIn("2", completed)


if __name__ == "__main__":
    unittest.main()
