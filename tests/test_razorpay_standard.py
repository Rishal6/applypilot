import hashlib
import hmac
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from applypilot.razorpay_standard import (
    create_standard_order,
    expected_standard_amount_paise,
    parse_amount,
    verify_standard_payment,
)
from applypilot.server import create_app


class RazorpayStandardTest(unittest.TestCase):
    def test_create_standard_order_uses_server_credentials_and_validates_amount(self):
        class FakeOrder:
            payload = {}

            def create(self, data):
                self.payload = data
                return {
                    "id": "order_test_123",
                    "amount": data["amount"],
                    "currency": data["currency"],
                    "receipt": data["receipt"],
                }

        fake_order = FakeOrder()

        class FakeClient:
            order = fake_order

        def factory(key_id, key_secret):
            self.assertEqual(key_id, "rzp_test_key")
            self.assertEqual(key_secret, "rzp_test_secret")
            return FakeClient()

        with patch.dict(
            os.environ,
            {"RAZORPAY_KEY_ID": "rzp_test_key", "RAZORPAY_KEY_SECRET": "rzp_test_secret"},
        ):
            order = create_standard_order(
                {"amount": 99900, "currency": "INR", "receipt": "rcpt_test"},
                client_factory=factory,
            )

        self.assertEqual(order["order_id"], "order_test_123")
        self.assertEqual(order["amount"], 99900)
        self.assertEqual(order["currency"], "INR")
        self.assertEqual(order["key_id"], "rzp_test_key")
        self.assertEqual(fake_order.payload["amount"], 99900)
        with self.assertRaises(ValueError):
            parse_amount(99)
        self.assertEqual(expected_standard_amount_paise("team", 2), 999800)

    def test_verify_standard_payment_signature(self):
        order_id = "order_test_123"
        payment_id = "pay_test_123"
        secret = "rzp_test_secret"
        fulfillment_secret = "fulfillment-secret-test"
        signature = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        with patch.dict(os.environ, {"RAZORPAY_KEY_SECRET": secret}):
            verified = verify_standard_payment(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
            self.assertTrue(verified["success"])
            with self.assertRaises(PermissionError):
                verify_standard_payment(
                    {
                        "razorpay_order_id": order_id,
                        "razorpay_payment_id": payment_id,
                        "razorpay_signature": "bad",
                    }
                )

    def test_standard_checkout_api_endpoints(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("server dependencies are not installed")

        order_id = "order_test_123"
        payment_id = "pay_test_123"
        secret = "rzp_test_secret"
        fulfillment_secret = "fulfillment-secret-test"
        signature = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "RAZORPAY_KEY_SECRET": secret,
                "APPLYPILOT_FULFILLMENT_SECRET": fulfillment_secret,
            },
        ):
            client = TestClient(create_app(db_path=Path(tmp) / "saas.sqlite3"))
            with patch("applypilot.server.create_standard_order") as create_order:
                create_order.return_value = {
                    "order_id": order_id,
                    "amount": 99900,
                    "currency": "INR",
                    "key_id": "rzp_test_key",
                }
                response = client.post(
                    "/api/create-order",
                    json={
                        "amount": 100,
                        "currency": "INR",
                        "email": "paid@example.com",
                        "name": "Paid User",
                        "company": "Acme",
                        "plan": "pro_byok",
                        "ai_mode": "byok_local",
                        "seats": 1,
                    },
                )
                create_order.assert_called_once()
                self.assertEqual(create_order.call_args.args[0]["amount"], 99900)
            verify_response = client.post(
                "/api/verify-payment",
                json={
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                },
            )
            bad_response = client.post(
                "/api/verify-payment",
                json={
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": "bad",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order_id"], order_id)
        self.assertEqual(response.json()["plan"], "pro_byok")
        self.assertTrue(response.json()["claim_token"].startswith("ap_claim_"))
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.json()["success"])
        self.assertTrue(verify_response.json()["license_key"].startswith("ap_live_"))
        self.assertEqual(verify_response.json()["email"], "paid@example.com")
        self.assertEqual(bad_response.status_code, 400)

    def test_create_order_requires_fulfillment_secret_before_calling_razorpay(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("server dependencies are not installed")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "APPLYPILOT_ENV_FILE": str(Path(tmp) / "missing.env"),
                "APPLYPILOT_FULFILLMENT_SECRET": "",
                "RAZORPAY_KEY_ID": "rzp_test_key",
                "RAZORPAY_KEY_SECRET": "rzp_test_secret",
            },
        ):
            client = TestClient(create_app(db_path=Path(tmp) / "saas.sqlite3"))
            with patch("applypilot.server.create_standard_order") as create_order:
                response = client.post(
                    "/api/create-order",
                    json={
                        "currency": "INR",
                        "email": "blocked@example.com",
                        "name": "Blocked User",
                        "plan": "pro_byok",
                        "ai_mode": "byok_local",
                        "seats": 1,
                    },
                )

        self.assertEqual(response.status_code, 503)
        self.assertIn("APPLYPILOT_FULFILLMENT_SECRET", response.json()["detail"])
        create_order.assert_not_called()

    def test_verify_unknown_order_does_not_issue_license(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("server dependencies are not installed")

        order_id = "order_missing"
        payment_id = "pay_test_123"
        secret = "rzp_test_secret"
        signature = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "RAZORPAY_KEY_SECRET": secret,
                "APPLYPILOT_FULFILLMENT_SECRET": "fulfillment-secret-test",
            },
        ):
            client = TestClient(create_app(db_path=Path(tmp) / "saas.sqlite3"))
            response = client.post(
                "/api/verify-payment",
                json={
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown Razorpay order", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
