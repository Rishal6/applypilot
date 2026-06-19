import hashlib
import hmac
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from applypilot.razorpay_standard import (
    create_standard_order,
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

    def test_verify_standard_payment_signature(self):
        order_id = "order_test_123"
        payment_id = "pay_test_123"
        secret = "rzp_test_secret"
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
        signature = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(db_path=Path(tmp) / "saas.sqlite3"))
            with patch("applypilot.server.create_standard_order") as create_order:
                create_order.return_value = {
                    "order_id": order_id,
                    "amount": 99900,
                    "currency": "INR",
                    "key_id": "rzp_test_key",
                }
                response = client.post("/api/create-order", json={"amount": 99900, "currency": "INR"})
            with patch.dict(os.environ, {"RAZORPAY_KEY_SECRET": secret}):
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
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.json()["success"])
        self.assertEqual(bad_response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
