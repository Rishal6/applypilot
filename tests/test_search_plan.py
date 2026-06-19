import tempfile
import unittest
from pathlib import Path

from applypilot.career import save_career_profile
from applypilot.config import load_preferences, write_default_workspace
from applypilot.models import Job
from applypilot.search_plan import build_search_plan, is_profile_aligned


class SearchPlanTest(unittest.TestCase):
    def test_builds_queries_only_from_saved_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "target": "AI Engineer",
                "skills": ["Python"],
                "location": "Remote",
            })

            plan = build_search_plan(workspace)

        self.assertEqual([item.keyword for item in plan], ["AI Engineer", "AI Engineer"])
        self.assertFalse(plan[0].remote_only)
        self.assertTrue(plan[1].remote_only)
        self.assertNotIn("Simulation Engineer Isaac Sim", [item.keyword for item in plan])

    def test_requires_completed_career_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            write_default_workspace(workspace)

            with self.assertRaises(ValueError):
                build_search_plan(workspace)

    def test_filters_off_profile_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / ".applypilot"
            save_career_profile(workspace, {
                "target": "AI Engineer",
                "skills": ["Python"],
                "location": "Remote",
            })
            preferences = load_preferences(workspace)

        self.assertTrue(is_profile_aligned(Job(id="1", title="AI/ML Engineer"), preferences))
        self.assertTrue(is_profile_aligned(Job(id="2", title="Python AI Developer"), preferences))
        self.assertFalse(is_profile_aligned(Job(id="3", title="Drone Research Engineer"), preferences))
        self.assertFalse(is_profile_aligned(Job(id="4", title="Mechanical Design Engineer"), preferences))


if __name__ == "__main__":
    unittest.main()
