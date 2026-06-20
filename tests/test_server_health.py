import os
import tempfile
import unittest
from pathlib import Path

from applypilot.server import create_app


class ServerHealthTest(unittest.TestCase):
    def test_health_exposes_render_commit_metadata_when_available(self):
        previous = {key: os.environ.get(key) for key in ["RENDER_GIT_COMMIT", "RENDER_GIT_BRANCH", "RENDER_SERVICE_NAME"]}
        try:
            os.environ["RENDER_GIT_COMMIT"] = "2b3a09aa0f4d20b305ba24b5536caf340dd2f4b7"
            os.environ["RENDER_GIT_BRANCH"] = "main"
            os.environ["RENDER_SERVICE_NAME"] = "applypilot-saas"
            try:
                from fastapi.testclient import TestClient
            except ImportError:
                self.skipTest("server dependencies are not installed")

            with tempfile.TemporaryDirectory() as tmp:
                client = TestClient(create_app(db_path=Path(tmp) / "saas.sqlite3"))
                response = client.get("/api/v1/health")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["commit"], "2b3a09a")
        self.assertEqual(response.json()["commit_full"], "2b3a09aa0f4d20b305ba24b5536caf340dd2f4b7")
        self.assertEqual(response.json()["branch"], "main")
        self.assertEqual(response.json()["service"], "applypilot-saas")


if __name__ == "__main__":
    unittest.main()
