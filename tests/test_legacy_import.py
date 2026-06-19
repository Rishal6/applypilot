import unittest

from applypilot.connectors.legacy_linkedin import load_legacy_jobs


class LegacyImportTest(unittest.TestCase):
    def test_load_legacy_jobs(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "jobs.json"
            source.write_text(
                '{"jobs":[{"job_id":"123","title":"AI Engineer","company":"Acme","easy_apply":true}]}',
                encoding="utf-8",
            )

            jobs = load_legacy_jobs(source)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "123")
        self.assertEqual(jobs[0].title, "AI Engineer")
        self.assertEqual(jobs[0].source, "legacy_linkedin")


if __name__ == "__main__":
    unittest.main()
