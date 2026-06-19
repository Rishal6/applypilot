import tempfile
import unittest
from pathlib import Path

from applypilot.config import write_default_workspace
from applypilot.dashboard import build_dashboard_data, write_dashboard_data
from applypilot.models import Evaluation, Job
from applypilot.storage import Store


class DashboardDataTest(unittest.TestCase):
    def test_builds_dashboard_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            write_default_workspace(workspace)
            store = Store(workspace)
            store.save_jobs([
                Job(id="1", title="AI Engineer", company="Acme", easy_apply=True),
            ])
            store.save_evaluations([
                Evaluation(job_id="1", score=82, decision="shortlist", reason="fit", provider="rules"),
            ])

            data = build_dashboard_data(workspace)

        self.assertEqual(data["summary"]["jobs"], 1)
        self.assertEqual(data["summary"]["evaluations"], 1)
        self.assertEqual(data["summary"]["shortlisted"], 1)
        self.assertEqual(data["summary"]["profile_applied_total"], 0)
        self.assertEqual(data["summary"]["imported_history_total"], 0)
        self.assertEqual(data["jobs"][0]["title"], "AI Engineer")

    def test_writes_dashboard_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            out = Path(tmp) / "dashboard.json"
            write_default_workspace(workspace)

            data = write_dashboard_data(workspace, out)

            self.assertTrue(out.exists())
            self.assertIn("summary", data)


if __name__ == "__main__":
    unittest.main()
