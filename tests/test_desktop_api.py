import tempfile
import unittest
from pathlib import Path

from applypilot.desktop import create_desktop_app
from applypilot.models import Job
from applypilot.storage import Store


class DesktopApiTest(unittest.TestCase):
    def test_profile_persists_and_rescores_jobs(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("desktop dependencies are not installed")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            Store(workspace).save_jobs([
                Job(
                    id="1",
                    title="Python Backend Developer",
                    company="Acme",
                    location="Remote",
                    description="Python FastAPI APIs",
                    easy_apply=True,
                )
            ])
            client = TestClient(create_desktop_app(workspace))

            response = client.put(
                "/api/profile",
                headers={"Origin": "http://127.0.0.1:8765"},
                json={
                    "profile": {
                        "name": "Test Candidate",
                        "target": "Python Backend Developer",
                        "background": "Built FastAPI services.",
                        "skills": ["Python", "FastAPI"],
                        "location": "Remote",
                    },
                    "rescore": True,
                },
            )
            dashboard = client.get("/api/dashboard")
            search_plan = client.get("/api/search-plan")
            resume = client.get("/api/resume")
            policy = client.post(
                "/api/policy",
                headers={"Origin": "http://127.0.0.1:8765"},
                json={
                    "mode": "auto-submit",
                    "daily_limit": 12,
                    "min_score": 80,
                    "require_easy_apply": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scored"], 1)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["jobs"][0]["provider"], "rules")
        self.assertGreater(dashboard.json()["jobs"][0]["score"], 0)
        self.assertEqual(search_plan.json()["queries"][0]["keyword"], "Python Backend Developer")
        self.assertIn("Built FastAPI services.", resume.text)
        self.assertEqual(policy.status_code, 200)
        self.assertEqual(policy.json()["mode"], "auto-submit")
        self.assertEqual(policy.json()["max_applications_per_day"], 12)

    def test_unlicensed_desktop_cannot_start_paid_automation(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("desktop dependencies are not installed")

        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_desktop_app(Path(tmp) / ".applypilot"))
            response = client.post(
                "/api/run",
                headers={"Origin": "http://127.0.0.1:8765"},
                json={"mode": "search", "confirmed": False},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Activate this desktop", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
