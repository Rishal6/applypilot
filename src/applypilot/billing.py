from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .saas_store import AI_MODES, PLAN_IDS, SaasStore


DEFAULT_AI_MODE = {
    "free_cli": "byok_local",
    "pro_byok": "byok_local",
    "pro_managed": "hybrid",
    "team": "hybrid",
}


@dataclass(slots=True)
class CheckoutRequest:
    provider: str
    email: str
    plan: str
    name: str = ""
    company: str = ""
    ai_mode: str = ""
    seats: int = 1
    success_url: str = ""
    cancel_url: str = ""
    phone: str = ""


class BillingService:
    def __init__(
        self,
        store: SaasStore,
        fulfillment_secret: str | None = None,
        stripe_webhook_secret: str | None = None,
        razorpay_webhook_secret: str | None = None,
    ):
        self.store = store
        self.fulfillment_secret = fulfillment_secret or os.environ.get("APPLYPILOT_FULFILLMENT_SECRET", "")
        self.stripe_webhook_secret = stripe_webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        self.razorpay_webhook_secret = razorpay_webhook_secret or os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    def create_checkout(self, request: CheckoutRequest) -> dict[str, Any]:
        provider = request.provider.strip().lower()
        if provider not in {"stripe", "razorpay"}:
            raise ValueError("Billing provider must be stripe or razorpay.")
        if request.plan not in PLAN_IDS or request.plan == "free_cli":
            raise ValueError("Choose a paid plan: pro_byok, pro_managed, or team.")
        ai_mode = request.ai_mode or DEFAULT_AI_MODE[request.plan]
        if ai_mode not in AI_MODES:
            raise ValueError(f"Invalid AI mode: {ai_mode}")
        if request.seats < 1:
            raise ValueError("Seats must be at least 1.")
        self.require_fulfillment_secret()

        created = self.store.create_billing_checkout(
            provider=provider,
            email=request.email,
            name=request.name,
            company=request.company,
            plan=request.plan,
            ai_mode=ai_mode,
            seats=request.seats,
        )
        checkout = created["checkout"]
        if provider == "stripe":
            provider_checkout = self.create_stripe_checkout(checkout, request)
            external_reference = str(provider_checkout.get("id") or "")
            checkout_url = str(provider_checkout.get("url") or "")
        else:
            provider_checkout = self.create_razorpay_subscription(checkout, request)
            external_reference = str(provider_checkout.get("id") or "")
            checkout_url = str(provider_checkout.get("short_url") or "")
        if not external_reference or not checkout_url:
            raise RuntimeError(f"{provider.title()} did not return a checkout URL.")
        self.store.set_billing_checkout_reference(str(checkout["id"]), external_reference)
        return {
            "provider": provider,
            "checkout_id": checkout["id"],
            "checkout_url": checkout_url,
            "claim_token": created["claim_token"],
        }

    def create_stripe_checkout(
        self,
        checkout: dict[str, Any],
        request: CheckoutRequest,
    ) -> dict[str, Any]:
        api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        price_id = plan_external_id("STRIPE_PRICE", request.plan)
        if not api_key or not price_id:
            raise RuntimeError("Configure STRIPE_SECRET_KEY and the Stripe price ID for this plan.")
        success_url = request.success_url or os.environ.get(
            "APPLYPILOT_CHECKOUT_SUCCESS_URL",
            "http://127.0.0.1:8787/checkout.html?paid=1&session_id={CHECKOUT_SESSION_ID}",
        )
        cancel_url = request.cancel_url or os.environ.get(
            "APPLYPILOT_CHECKOUT_CANCEL_URL",
            "http://127.0.0.1:8787/checkout.html?cancelled=1",
        )
        metadata = billing_metadata(checkout)
        fields: list[tuple[str, str]] = [
            ("mode", "subscription"),
            ("customer_email", str(checkout["email"])),
            ("client_reference_id", str(checkout["id"])),
            ("line_items[0][price]", price_id),
            ("line_items[0][quantity]", str(checkout["seats"])),
            ("success_url", success_url),
            ("cancel_url", cancel_url),
        ]
        for key, value in metadata.items():
            fields.append((f"metadata[{key}]", value))
            fields.append((f"subscription_data[metadata][{key}]", value))
        return provider_request(
            "https://api.stripe.com/v1/checkout/sessions",
            fields,
            headers={"Authorization": f"Bearer {api_key}"},
            form_encoded=True,
        )

    def create_razorpay_subscription(
        self,
        checkout: dict[str, Any],
        request: CheckoutRequest,
    ) -> dict[str, Any]:
        key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        plan_id = plan_external_id("RAZORPAY_PLAN", request.plan)
        if not key_id or not key_secret or not plan_id:
            raise RuntimeError("Configure RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, and the Razorpay plan ID.")
        total_count = int(os.environ.get("RAZORPAY_TOTAL_COUNT", "120"))
        payload: dict[str, Any] = {
            "plan_id": plan_id,
            "total_count": total_count,
            "quantity": int(checkout["seats"]),
            "customer_notify": True,
            "notes": billing_metadata(checkout),
            "notify_info": {"email": str(checkout["email"])},
        }
        if request.phone:
            payload["notify_info"]["contact"] = request.phone
        basic = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode("ascii")
        return provider_request(
            "https://api.razorpay.com/v1/subscriptions",
            payload,
            headers={"Authorization": f"Basic {basic}"},
        )

    def handle_stripe_webhook(
        self,
        raw_body: bytes,
        signature: str,
        now: int | None = None,
    ) -> dict[str, Any]:
        if not self.stripe_webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured.")
        verify_stripe_signature(raw_body, signature, self.stripe_webhook_secret, now=now)
        event = json.loads(raw_body)
        return self.process_event("stripe", event, str(event.get("id") or ""))

    def handle_razorpay_webhook(
        self,
        raw_body: bytes,
        signature: str,
        event_id: str = "",
    ) -> dict[str, Any]:
        if not self.razorpay_webhook_secret:
            raise RuntimeError("RAZORPAY_WEBHOOK_SECRET is not configured.")
        verify_razorpay_signature(raw_body, signature, self.razorpay_webhook_secret)
        event = json.loads(raw_body)
        stable_event_id = event_id or hashlib.sha256(raw_body).hexdigest()
        return self.process_event("razorpay", event, stable_event_id)

    def process_event(self, provider: str, event: dict[str, Any], event_id: str) -> dict[str, Any]:
        event_type = str(event.get("type") if provider == "stripe" else event.get("event") or "")
        if not event_id:
            raise ValueError("Webhook event ID is required.")
        if not self.store.reserve_billing_event(provider, event_id, event_type):
            return {"status": "duplicate", "event_id": event_id}
        try:
            if provider == "stripe":
                result = self.process_stripe_event(event_type, event)
            else:
                result = self.process_razorpay_event(event_type, event)
            self.store.complete_billing_event(provider, event_id)
            return {"status": "ok", "event_id": event_id, **result}
        except Exception as exc:
            self.store.fail_billing_event(provider, event_id, str(exc))
            raise

    def process_stripe_event(self, event_type: str, event: dict[str, Any]) -> dict[str, Any]:
        obj = nested(event, "data", "object") or {}
        metadata = dict(obj.get("metadata") or {})
        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            payment_status = str(obj.get("payment_status") or "")
            if payment_status not in {"paid", "no_payment_required"}:
                return {"action": "ignored_unpaid"}
            checkout_id = str(metadata.get("applypilot_checkout_id") or obj.get("client_reference_id") or "")
            subscription_id = string_id(obj.get("subscription"))
            result = self.fulfill_checkout(
                checkout_id=checkout_id,
                external_reference=str(obj.get("id") or ""),
                provider="stripe",
                external_subscription_id=subscription_id,
                external_customer_id=string_id(obj.get("customer")),
                subscription_status="active",
                current_period_end="",
            )
            return {"action": "fulfilled", "checkout_id": checkout_id, "created": result["created"]}

        if event_type.startswith("customer.subscription."):
            subscription_id = str(obj.get("id") or "")
            status = str(obj.get("status") or event_type.rsplit(".", 1)[-1])
            if event_type == "customer.subscription.deleted":
                status = "cancelled"
            updated = self.store.update_billing_subscription_status("stripe", subscription_id, status)
            return {"action": "subscription_status", "updated": bool(updated), "status": status}

        if event_type == "invoice.payment_failed":
            subscription_id = string_id(obj.get("subscription")) or string_id(
                nested(obj, "parent", "subscription_details", "subscription")
            )
            updated = self.store.update_billing_subscription_status("stripe", subscription_id, "past_due")
            return {"action": "payment_failed", "updated": bool(updated)}

        return {"action": "ignored"}

    def process_razorpay_event(self, event_type: str, event: dict[str, Any]) -> dict[str, Any]:
        subscription = nested(event, "payload", "subscription", "entity") or {}
        payment_link = nested(event, "payload", "payment_link", "entity") or {}
        entity = subscription or payment_link
        notes = dict(entity.get("notes") or {})
        checkout_id = str(notes.get("applypilot_checkout_id") or "")

        if event_type in {"subscription.activated", "subscription.charged", "payment_link.paid"}:
            subscription_id = str(subscription.get("id") or "")
            result = self.fulfill_checkout(
                checkout_id=checkout_id,
                external_reference=str(entity.get("id") or ""),
                provider="razorpay",
                external_subscription_id=subscription_id,
                external_customer_id=str(subscription.get("customer_id") or ""),
                subscription_status=str(subscription.get("status") or "active"),
                current_period_end=unix_to_iso(subscription.get("current_end")),
            )
            return {"action": "fulfilled", "checkout_id": checkout_id, "created": result["created"]}

        if event_type.startswith("subscription."):
            subscription_id = str(subscription.get("id") or "")
            status = str(subscription.get("status") or event_type.rsplit(".", 1)[-1])
            updated = self.store.update_billing_subscription_status("razorpay", subscription_id, status)
            return {"action": "subscription_status", "updated": bool(updated), "status": status}

        return {"action": "ignored"}

    def fulfill_checkout(
        self,
        checkout_id: str,
        external_reference: str,
        provider: str,
        external_subscription_id: str,
        external_customer_id: str,
        subscription_status: str,
        current_period_end: str,
    ) -> dict[str, Any]:
        if not checkout_id:
            raise ValueError("Webhook is missing applypilot_checkout_id metadata.")
        self.require_fulfillment_secret()
        result = self.store.fulfill_billing_checkout(
            checkout_id,
            encrypt_license_key=lambda key: encrypt_text(key, self.fulfillment_secret),
            external_reference=external_reference,
        )
        checkout = result["checkout"]
        if external_subscription_id:
            self.store.upsert_billing_subscription(
                customer_id=str(result["customer"]["id"]),
                provider=provider,
                external_subscription_id=external_subscription_id,
                external_customer_id=external_customer_id,
                plan=str(checkout["plan"]),
                ai_mode=str(checkout["ai_mode"]),
                status=subscription_status,
                current_period_end=current_period_end,
            )
        return result

    def claim_checkout(self, claim_token: str) -> dict[str, Any]:
        self.require_fulfillment_secret()
        checkout = self.store.claim_billing_checkout(claim_token)
        if not checkout:
            raise PermissionError("Invalid claim token.")
        response = {
            "status": checkout["status"],
            "provider": checkout["provider"],
            "plan": checkout["plan"],
            "ai_mode": checkout["ai_mode"],
            "email": checkout["email"],
        }
        if checkout["status"] == "paid" and checkout["encrypted_license_key"]:
            response["license_key"] = decrypt_text(
                str(checkout["encrypted_license_key"]),
                self.fulfillment_secret,
            )
        return response

    def fulfill_standard_checkout(
        self,
        checkout_id: str,
        external_reference: str,
        payment_id: str,
    ) -> dict[str, Any]:
        result = self.fulfill_checkout(
            checkout_id=checkout_id,
            external_reference=external_reference,
            provider="razorpay_standard",
            external_subscription_id="",
            external_customer_id="",
            subscription_status="paid",
            current_period_end="",
        )
        checkout = result["checkout"]
        response = {
            "success": True,
            "status": checkout["status"],
            "provider": checkout["provider"],
            "checkout_id": checkout["id"],
            "order_id": external_reference,
            "payment_id": payment_id,
            "plan": checkout["plan"],
            "ai_mode": checkout["ai_mode"],
            "email": checkout["email"],
            "created": result["created"],
        }
        if result.get("license_key"):
            response["license_key"] = result["license_key"]
        elif checkout.get("encrypted_license_key"):
            response["license_key"] = decrypt_text(
                str(checkout["encrypted_license_key"]),
                self.fulfillment_secret,
            )
        return response

    def require_fulfillment_secret(self) -> None:
        if not self.fulfillment_secret:
            raise RuntimeError("APPLYPILOT_FULFILLMENT_SECRET is not configured.")


def verify_stripe_signature(
    raw_body: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    parts: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        if "=" not in item:
            continue
        key, value = item.strip().split("=", 1)
        parts.setdefault(key, []).append(value)
    timestamps = parts.get("t") or []
    signatures = parts.get("v1") or []
    if not timestamps or not signatures:
        raise PermissionError("Invalid Stripe signature header.")
    timestamp = int(timestamps[0])
    current = int(time.time() if now is None else now)
    if tolerance_seconds and abs(current - timestamp) > tolerance_seconds:
        raise PermissionError("Stripe webhook timestamp is outside tolerance.")
    signed = str(timestamp).encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise PermissionError("Invalid Stripe webhook signature.")


def verify_razorpay_signature(raw_body: bytes, signature: str, secret: str) -> None:
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise PermissionError("Invalid Razorpay webhook signature.")


def encrypt_text(value: str, secret: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(fernet_key(secret)).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str, secret: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(fernet_key(secret)).decrypt(value.encode("ascii")).decode("utf-8")


def fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def plan_external_id(prefix: str, plan: str) -> str:
    return os.environ.get(f"APPLYPILOT_{prefix}_{plan.upper()}", "")


def billing_metadata(checkout: dict[str, Any]) -> dict[str, str]:
    return {
        "applypilot_checkout_id": str(checkout["id"]),
        "applypilot_plan": str(checkout["plan"]),
        "applypilot_ai_mode": str(checkout["ai_mode"]),
        "applypilot_seats": str(checkout["seats"]),
    }


def provider_request(
    url: str,
    payload: dict[str, Any] | list[tuple[str, str]],
    headers: dict[str, str],
    form_encoded: bool = False,
) -> dict[str, Any]:
    if form_encoded:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode("utf-8")
        content_type = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": content_type, **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Billing provider error {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Billing provider unavailable: {exc.reason}") from exc


def nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def string_id(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return ""


def unix_to_iso(value: Any) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
