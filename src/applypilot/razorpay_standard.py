from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from pathlib import Path
from typing import Any, Callable


MIN_ORDER_AMOUNT_PAISE = 100
DEFAULT_CURRENCY = "INR"
STANDARD_PLAN_AMOUNTS_PAISE = {
    "pro_byok": 99900,
    "pro_managed": 199900,
    "team": 499900,
}
_DOTENV_LOADED = False


class RazorpayConfigurationError(PermissionError):
    """Raised when Razorpay credentials are missing or unusable."""


class RazorpayAuthenticationError(PermissionError):
    """Raised when Razorpay rejects configured credentials."""


class RazorpayApiError(RuntimeError):
    """Raised when Razorpay order creation fails."""


def create_standard_order(
    payload: dict[str, Any],
    client_factory: Callable[[str, str], Any] | None = None,
) -> dict[str, Any]:
    """Create a Razorpay Standard Checkout order.

    The Key Secret stays server-side. The public Key ID is returned because
    Razorpay Checkout needs it in the browser.
    """

    key_id, key_secret = razorpay_credentials()
    amount = parse_amount(payload.get("amount"))
    currency = parse_currency(payload.get("currency"))
    receipt = parse_receipt(payload.get("receipt"))
    request_payload = {
        "amount": amount,
        "currency": currency,
        "receipt": receipt,
    }
    try:
        client = (client_factory or make_razorpay_client)(key_id, key_secret)
        order = client.order.create(data=request_payload)
    except Exception as exc:  # pragma: no cover - concrete SDK errors vary by version
        if looks_like_auth_error(exc):
            raise RazorpayAuthenticationError("Razorpay authentication failed.") from exc
        raise RazorpayApiError("Unable to create Razorpay order.") from exc

    order_id = str(order.get("id") or "")
    if not order_id:
        raise RazorpayApiError("Razorpay did not return an order id.")
    return {
        "order_id": order_id,
        "amount": int(order.get("amount") or amount),
        "currency": str(order.get("currency") or currency),
        "receipt": str(order.get("receipt") or receipt),
        "key_id": key_id,
    }


def verify_standard_payment(payload: dict[str, Any]) -> dict[str, Any]:
    load_dotenv_once()
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
    if not key_secret:
        raise RazorpayConfigurationError("RAZORPAY_KEY_SECRET is not configured.")

    payment_id = str(payload.get("razorpay_payment_id") or "").strip()
    order_id = str(payload.get("razorpay_order_id") or "").strip()
    signature = str(payload.get("razorpay_signature") or "").strip()
    if not payment_id or not order_id or not signature:
        raise ValueError("Missing Razorpay payment id, order id, or signature.")

    expected = hmac.new(
        key_secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PermissionError("Razorpay payment signature mismatch.")
    return {
        "success": True,
        "order_id": order_id,
        "payment_id": payment_id,
    }


def razorpay_credentials() -> tuple[str, str]:
    load_dotenv_once()
    key_id = os.environ.get("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
    if not key_id or not key_secret:
        raise RazorpayConfigurationError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are required.")
    return key_id, key_secret


def make_razorpay_client(key_id: str, key_secret: str) -> Any:
    try:
        import razorpay
    except ImportError as exc:
        raise RazorpayApiError("Install Razorpay SDK with: pip install razorpay") from exc
    return razorpay.Client(auth=(key_id, key_secret))


def parse_amount(value: Any) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Amount must be an integer in paise.") from exc
    if amount < MIN_ORDER_AMOUNT_PAISE:
        raise ValueError("Amount must be at least 100 paise.")
    return amount


def parse_currency(value: Any) -> str:
    currency = str(value or DEFAULT_CURRENCY).strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("Currency must be a 3-letter ISO code.")
    return currency


def parse_receipt(value: Any) -> str:
    receipt = str(value or "").strip()
    if not receipt:
        receipt = f"ap_{uuid.uuid4().hex[:20]}"
    return receipt[:40]


def expected_standard_amount_paise(plan: str, seats: int) -> int:
    if plan not in STANDARD_PLAN_AMOUNTS_PAISE:
        raise ValueError("Choose a paid plan: pro_byok, pro_managed, or team.")
    if seats < 1:
        raise ValueError("Seats must be at least 1.")
    return STANDARD_PLAN_AMOUNTS_PAISE[plan] * seats


def looks_like_auth_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "http_status_code", None)
    message = str(exc).lower()
    return status_code == 401 or "auth" in message or "unauthorized" in message


def load_dotenv_once() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    env_file = Path(os.environ.get("APPLYPILOT_ENV_FILE", ".env")).expanduser()
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
