import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import applypilot.legacy_agent as legacy_agent
from applypilot.legacy_agent import (
    modules_for_mode,
    parse_legacy_log,
    parse_legacy_logs,
    run_native_agent,
    totals_for_runs,
)


class LegacyAgentLogTest(unittest.TestCase):
    def test_parses_linkedin_session_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "apply_20260617_071113.log"
            log.write_text(
                "[10:33:29] SESSION COMPLETE - Applied: 23, Skipped: 119\n",
                encoding="utf-8",
            )

            summary = parse_legacy_log(log)

        self.assertEqual(summary.source, "linkedin")
        self.assertEqual(summary.applied, 23)
        self.assertEqual(summary.skipped, 119)
        self.assertEqual(summary.completed_at, "2026-06-17T07:11:13")
        self.assertEqual(summary.status, "complete")

    def test_parses_naukri_session_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "naukri_20260617_103416.log"
            log.write_text("[12:26:25] SESSION COMPLETE - Applied: 47\n", encoding="utf-8")

            summary = parse_legacy_log(log)

        self.assertEqual(summary.source, "naukri")
        self.assertEqual(summary.applied, 47)
        self.assertEqual(summary.status, "complete")

    def test_parses_lead_hunter_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "leads_20260617_120000.log"
            log.write_text(
                "Total leads found: 9\nWith email: 3\nWith profile: 8\nDrafts written: 3\n",
                encoding="utf-8",
            )

            summary = parse_legacy_log(log)

        self.assertEqual(summary.source, "leads")
        self.assertEqual(summary.leads, 9)
        self.assertEqual(summary.with_email, 3)
        self.assertEqual(summary.with_profile, 8)
        self.assertEqual(summary.drafts, 3)

    def test_totals_for_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apply_20260617_071113.log").write_text(
                "SESSION COMPLETE - Applied: 23, Skipped: 119\n",
                encoding="utf-8",
            )
            (root / "naukri_20260617_103416.log").write_text(
                "SESSION COMPLETE - Applied: 47\n",
                encoding="utf-8",
            )
            (root / "leads_20260617_120000.log").write_text(
                "Total leads found: 9\nWith email: 3\n",
                encoding="utf-8",
            )

            totals = totals_for_runs(parse_legacy_logs(root))

        self.assertEqual(totals["linkedin_applied"], 23)
        self.assertEqual(totals["naukri_applied"], 47)
        self.assertEqual(totals["leads"], 9)
        self.assertEqual(totals["lead_emails"], 3)

    def test_ignores_unknown_log_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cron.log").write_text(
                "SESSION COMPLETE - Applied: 100, Skipped: 6\n",
                encoding="utf-8",
            )

            summaries = parse_legacy_logs(root)

        self.assertEqual(summaries, [])

    def test_native_daily_mapping_matches_working_agent_order(self):
        self.assertEqual(
            modules_for_mode("all"),
            [
                "applypilot.working_agent.auto_apply_chrome",
                "applypilot.working_agent.auto_apply_naukri",
                "applypilot.working_agent.lead_hunter",
            ],
        )

    def test_native_daily_dry_run_does_not_execute_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = run_native_agent("apply", Path(tmp), dry_run=True)

        self.assertEqual(
            results,
            [
                ("applypilot.working_agent.auto_apply_chrome", 0),
                ("applypilot.working_agent.auto_apply_naukri", 0),
            ],
        )

    def test_compiled_native_agent_runs_modules_in_process(self):
        calls = []
        legacy_agent.__dict__["__compiled__"] = True
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with patch.object(
                    legacy_agent.importlib,
                    "import_module",
                    return_value=SimpleNamespace(main=lambda: calls.append("ran")),
                ):
                    results = run_native_agent("linkedin", Path(tmp))
        finally:
            legacy_agent.__dict__.pop("__compiled__", None)

        self.assertEqual(calls, ["ran"])
        self.assertEqual(results, [("applypilot.working_agent.auto_apply_chrome", 0)])


if __name__ == "__main__":
    unittest.main()
