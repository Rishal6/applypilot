import json
import os
from pathlib import Path
from typing import Any

from .billing import DEFAULT_AI_MODE, BillingService, CheckoutRequest
from .config import workspace_path
from .razorpay_standard import (
    RazorpayApiError,
    RazorpayAuthenticationError,
    RazorpayConfigurationError,
    create_standard_order,
    expected_standard_amount_paise,
    load_dotenv_once,
    verify_standard_payment,
)
from .saas_store import SaasStore, default_saas_db


def create_app(db_path: str | Path | None = None, web_dir: str | Path | None = None):
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install server dependencies with: pip install -e '.[server]'") from exc

    load_dotenv_once()
    db = Path(db_path or os.environ.get("APPLYPILOT_SAAS_DB") or default_saas_db(workspace_path(".")))
    store = SaasStore(db)
    billing = BillingService(store)
    app = FastAPI(title="ApplyPilot SaaS", version="0.1.0")
    allowed_origins = [
        item.strip()
        for item in os.environ.get(
            "APPLYPILOT_ALLOWED_ORIGINS",
            "http://127.0.0.1:8787,http://localhost:8787",
        ).split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def require_admin(request: Request) -> None:
        expected = os.environ.get("APPLYPILOT_ADMIN_TOKEN", "")
        if not expected:
            raise HTTPException(status_code=503, detail="Admin API is disabled.")
        if request.headers.get("x-admin-token") != expected:
            raise HTTPException(status_code=403, detail="Admin token required.")

    def auth_context(authorization: str = Header(default="")) -> dict[str, Any]:
        token = bearer_token(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="Bearer token required.")
        context = store.authenticate_any_token(token)
        if not context:
            raise HTTPException(status_code=401, detail="Invalid or inactive token.")
        return context

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/api/v1/customers")
    async def create_customer(request: Request) -> dict[str, Any]:
        require_admin(request)
        body = await request.json()
        try:
            customer = store.create_customer(
                email=str(body.get("email") or ""),
                name=str(body.get("name") or ""),
                company=str(body.get("company") or ""),
                plan=str(body.get("plan") or "pro_byok"),
                ai_mode=str(body.get("ai_mode") or "byok_local"),
            )
            issued = store.issue_license(
                customer["id"],
                seats=int(body.get("seats") or 1),
                expires_at=str(body.get("expires_at") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"customer": customer, **issued}

    @app.post("/api/v1/devices/activate")
    async def activate_device(request: Request) -> dict[str, Any]:
        body = await request.json()
        try:
            return store.activate_device(
                license_key=str(body.get("license_key") or ""),
                device_id=str(body.get("device_id") or ""),
                name=str(body.get("device_name") or body.get("name") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/v1/billing/checkout/{provider}")
    async def create_billing_checkout(provider: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        try:
            return billing.create_checkout(CheckoutRequest(
                provider=provider,
                email=str(body.get("email") or ""),
                name=str(body.get("name") or ""),
                company=str(body.get("company") or ""),
                plan=str(body.get("plan") or ""),
                ai_mode=str(body.get("ai_mode") or ""),
                seats=int(body.get("seats") or 1),
                success_url=str(body.get("success_url") or ""),
                cancel_url=str(body.get("cancel_url") or ""),
                phone=str(body.get("phone") or ""),
            ))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/billing/claim")
    async def claim_billing_checkout(request: Request) -> dict[str, Any]:
        body = await request.json()
        try:
            return billing.claim_checkout(str(body.get("claim_token") or ""))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/create-order")
    async def create_razorpay_standard_order(request: Request) -> dict[str, Any]:
        body = await request.json()
        try:
            plan = str(body.get("plan") or "pro_byok")
            seats = int(body.get("seats") or 1)
            ai_mode = str(body.get("ai_mode") or DEFAULT_AI_MODE.get(plan, "byok_local"))
            amount = expected_standard_amount_paise(plan, seats)
            created = store.create_billing_checkout(
                provider="razorpay_standard",
                email=str(body.get("email") or ""),
                name=str(body.get("name") or ""),
                company=str(body.get("company") or ""),
                plan=plan,
                ai_mode=ai_mode,
                seats=seats,
            )
            order = create_standard_order({
                "amount": amount,
                "currency": str(body.get("currency") or "INR"),
                "receipt": created["checkout"]["id"],
            })
            store.set_billing_checkout_reference(created["checkout"]["id"], order["order_id"])
            return {
                **order,
                "checkout_id": created["checkout"]["id"],
                "claim_token": created["claim_token"],
                "plan": plan,
                "ai_mode": ai_mode,
                "seats": seats,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (RazorpayConfigurationError, RazorpayAuthenticationError) as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RazorpayApiError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/verify-payment")
    async def verify_razorpay_standard_payment(request: Request) -> dict[str, Any]:
        body = await request.json()
        try:
            verified = verify_standard_payment(body)
            checkout = store.get_billing_checkout_by_reference(
                "razorpay_standard",
                str(verified["order_id"]),
            )
            if not checkout:
                raise ValueError("Unknown Razorpay order.")
            return billing.fulfill_standard_checkout(
                checkout_id=str(checkout["id"]),
                external_reference=str(verified["order_id"]),
                payment_id=str(verified["payment_id"]),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/v1/webhooks/stripe")
    async def stripe_webhook(request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        signature = request.headers.get("stripe-signature", "")
        try:
            return billing.handle_stripe_webhook(raw_body, signature)
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/webhooks/razorpay")
    async def razorpay_webhook(request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        signature = request.headers.get("x-razorpay-signature", "")
        event_id = request.headers.get("x-razorpay-event-id", "")
        try:
            return billing.handle_razorpay_webhook(raw_body, signature, event_id=event_id)
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/me")
    def me(context: dict[str, Any] = Depends(auth_context)) -> dict[str, Any]:
        return {
            "customer_id": context.get("customer_id"),
            "email": context.get("customer_email", ""),
            "name": context.get("customer_name", ""),
            "company": context.get("customer_company", ""),
            "plan": context.get("customer_plan") or context.get("license_plan", ""),
            "ai_mode": context.get("customer_ai_mode", ""),
            "device_id": context.get("device_id", ""),
            "device_name": context.get("name", ""),
        }

    @app.post("/api/v1/sync/dashboard")
    async def sync_dashboard(
        request: Request,
        context: dict[str, Any] = Depends(auth_context),
    ) -> dict[str, Any]:
        if str(context.get("auth_type") or "") == "license":
            raise HTTPException(status_code=403, detail="Activate a device before syncing dashboard data.")
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Dashboard payload must be a JSON object.")
        return store.sync_dashboard(context, body)

    @app.get("/api/v1/dashboard")
    def dashboard(context: dict[str, Any] = Depends(auth_context)) -> dict[str, Any]:
        return store.dashboard_for_context(context)

    static_raw = web_dir or os.environ.get("APPLYPILOT_WEB_DIR")
    static_dir = Path(static_raw).expanduser().resolve() if static_raw else None
    if static_dir and static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="web")

    return app


def run_server(host: str, port: int, db_path: Path, web_dir: Path | None = None) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install server dependencies with: pip install -e '.[server]'") from exc
    uvicorn.run(create_app(db_path=db_path, web_dir=web_dir), host=host, port=port)


def bearer_token(authorization: str) -> str:
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix):].strip()
    return ""
