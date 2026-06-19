import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from applypilot.billing import (
    BillingService,
    verify_razorpay_signature,
    verify_stripe_signature,
)
from applypilot.saas_store import SaasStore


class BillingTest(unittest.TestCase):
    def test_stripe_signature_verification(self):
        payload = b'{"id":"evt_test"}'
        secret = "whsec_test"
        timestamp = 1_800_000_000
        signature = hmac.new(
            secret.encode(),
            str(timestamp).encode() + b"." + payload,
            hashlib.sha256,
        ).hexdigest()

        verify_stripe_signature(
            payload,
            f"t={timestamp},v1={signature}",
            secret,
            now=timestamp,
        )

        with self.assertRaises(PermissionError):
            verify_stripe_signature(payload, f"t={timestamp},v1=bad", secret, now=timestamp)

    def test_razorpay_signature_verification(self):
        payload = b'{"event":"subscription.activated"}'
        secret = "rzp_webhook_test"
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        verify_razorpay_signature(payload, signature, secret)

        with self.assertRaises(PermissionError):
            verify_razorpay_signature(payload, "bad", secret)

    def test_stripe_webhook_fulfills_and_claims_license_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaasStore(Path(tmp) / "saas.sqlite3")
            service = BillingService(
                store,
                fulfillment_secret="fulfillment-test-secret",
                stripe_webhook_secret="stripe-webhook-test",
            )
            created = store.create_billing_checkout(
                provider="stripe",
                email="paid@example.com",
                name="Paid User",
                company="Acme",
                plan="pro_byok",
                ai_mode="byok_local",
                seats=1,
            )
            checkout_id = created["checkout"]["id"]
            event = {
                "id": "evt_checkout_paid",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_paid",
                        "payment_status": "paid",
                        "customer": "cus_stripe",
                        "subscription": "sub_stripe",
                        "client_reference_id": checkout_id,
                        "metadata": {"applypilot_checkout_id": checkout_id},
                    }
                },
            }
            raw = json.dumps(event, separators=(",", ":")).encode()
            timestamp = 1_800_000_000
            signature = hmac.new(
                b"stripe-webhook-test",
                str(timestamp).encode() + b"." + raw,
                hashlib.sha256,
            ).hexdigest()
            header = f"t={timestamp},v1={signature}"

            result = service.handle_stripe_webhook(raw, header, now=timestamp)
            duplicate = service.handle_stripe_webhook(raw, header, now=timestamp)
            claim = service.claim_checkout(created["claim_token"])

            self.assertEqual(result["status"], "ok")
            self.assertEqual(duplicate["status"], "duplicate")
            self.assertEqual(claim["status"], "paid")
            self.assertTrue(claim["license_key"].startswith("ap_live_"))

            with store.connect() as conn:
                row = conn.execute(
                    "SELECT encrypted_license_key FROM billing_checkouts WHERE id = ?",
                    (checkout_id,),
                ).fetchone()
            self.assertNotIn(claim["license_key"], row["encrypted_license_key"])

    def test_razorpay_webhook_fulfills_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaasStore(Path(tmp) / "saas.sqlite3")
            service = BillingService(
                store,
                fulfillment_secret="fulfillment-test-secret",
                razorpay_webhook_secret="razorpay-webhook-test",
            )
            created = store.create_billing_checkout(
                provider="razorpay",
                email="india@example.com",
                name="India User",
                company="",
                plan="pro_managed",
                ai_mode="hybrid",
                seats=1,
            )
            event = {
                "event": "subscription.activated",
                "payload": {
                    "subscription": {
                        "entity": {
                            "id": "sub_razorpay",
                            "customer_id": "cust_razorpay",
                            "status": "active",
                            "current_end": 1_900_000_000,
                            "notes": {"applypilot_checkout_id": created["checkout"]["id"]},
                        }
                    }
                },
            }
            raw = json.dumps(event, separators=(",", ":")).encode()
            signature = hmac.new(b"razorpay-webhook-test", raw, hashlib.sha256).hexdigest()

            result = service.handle_razorpay_webhook(raw, signature, event_id="rzp_evt_1")
            claim = service.claim_checkout(created["claim_token"])

            self.assertEqual(result["status"], "ok")
            self.assertEqual(claim["plan"], "pro_managed")
            self.assertTrue(claim["license_key"].startswith("ap_live_"))


if __name__ == "__main__":
    unittest.main()
