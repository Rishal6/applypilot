import sqlite3
import tempfile
import unittest
from pathlib import Path

from applypilot.saas_store import SaasStore


class SaasStoreTest(unittest.TestCase):
    def test_license_activation_and_dashboard_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaasStore(Path(tmp) / "saas.sqlite3")
            customer = store.create_customer(
                "founder@example.com",
                name="Founder",
                plan="pro_byok",
                ai_mode="byok_local",
            )
            issued = store.issue_license(customer["id"], seats=1)

            self.assertTrue(issued["license_key"].startswith("ap_live_"))
            self.assertNotIn("key_hash", issued["license"])

            activated = store.activate_device(issued["license_key"], "macbook", "MacBook Pro")
            self.assertTrue(activated["device_token"].startswith("ap_dev_"))
            self.assertNotIn("token_hash", activated["device"])

            context = store.authenticate_device_token(activated["device_token"])
            self.assertIsNotNone(context)
            result = store.sync_dashboard(context, {
                "generated_at": "2026-06-18T00:00:00+00:00",
                "summary": {"jobs": 4, "legacy_linkedin_applied": 7},
                "policy": {"mode": "auto-submit"},
                "jobs": [],
                "runs": [],
                "series": [],
                "sources": [],
                "providers": [],
                "commands": [],
            })
            self.assertEqual(result["status"], "ok")

            dashboard = store.dashboard_for_context(context)
            self.assertEqual(dashboard["summary"]["jobs"], 4)
            self.assertEqual(dashboard["saas"]["email"], "founder@example.com")
            self.assertEqual(dashboard["saas"]["ai_mode"], "byok_local")

    def test_license_and_device_secrets_are_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "saas.sqlite3"
            store = SaasStore(db_path)
            customer = store.create_customer("secure@example.com")
            issued = store.issue_license(customer["id"])
            activated = store.activate_device(issued["license_key"], "desktop")

            with sqlite3.connect(db_path) as conn:
                raw = "\n".join(str(row) for row in conn.execute(
                    "SELECT key_hash FROM licenses UNION ALL SELECT token_hash FROM devices"
                ).fetchall())

            self.assertNotIn(issued["license_key"], raw)
            self.assertNotIn(activated["device_token"], raw)

    def test_seat_limit_blocks_extra_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaasStore(Path(tmp) / "saas.sqlite3")
            customer = store.create_customer("seat@example.com")
            issued = store.issue_license(customer["id"], seats=1)
            store.activate_device(issued["license_key"], "desktop-1")

            with self.assertRaises(PermissionError):
                store.activate_device(issued["license_key"], "desktop-2")


if __name__ == "__main__":
    unittest.main()
