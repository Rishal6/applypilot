from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Callable

from .models import utc_now


PLAN_IDS = {"free_cli", "pro_byok", "pro_managed", "team"}
AI_MODES = {"byok_local", "byok_cloud", "managed_api", "hosted_model", "hybrid"}


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


def default_saas_db(workspace: Path) -> Path:
    return workspace / "saas" / "applypilot.sqlite3"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_secret(prefix: str) -> str:
    return f"{prefix}{secrets.token_urlsafe(32)}"


def public_prefix(secret: str) -> str:
    return secret[:18]


class SaasStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path.expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL DEFAULT '',
                    company TEXT NOT NULL DEFAULT '',
                    plan TEXT NOT NULL,
                    ai_mode TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS licenses (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_prefix TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    seats INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                );

                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    license_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    token_hash TEXT NOT NULL UNIQUE,
                    token_prefix TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_seen_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(license_id, device_id),
                    FOREIGN KEY(customer_id) REFERENCES customers(id),
                    FOREIGN KEY(license_id) REFERENCES licenses(id)
                );

                CREATE TABLE IF NOT EXISTS sync_events (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    device_pk TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                );

                CREATE TABLE IF NOT EXISTS dashboard_snapshots (
                    customer_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                );

                CREATE TABLE IF NOT EXISTS billing_checkouts (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    claim_hash TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    company TEXT NOT NULL DEFAULT '',
                    plan TEXT NOT NULL,
                    ai_mode TEXT NOT NULL,
                    seats INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'created',
                    external_reference TEXT NOT NULL DEFAULT '',
                    customer_id TEXT NOT NULL DEFAULT '',
                    license_id TEXT NOT NULL DEFAULT '',
                    encrypted_license_key TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    claimed_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS billing_events (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    UNIQUE(provider, event_id)
                );

                CREATE TABLE IF NOT EXISTS billing_subscriptions (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    external_customer_id TEXT NOT NULL DEFAULT '',
                    external_subscription_id TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    ai_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_period_end TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider, external_subscription_id),
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                );
                """
            )

    def create_customer(
        self,
        email: str,
        name: str = "",
        company: str = "",
        plan: str = "pro_byok",
        ai_mode: str = "byok_local",
    ) -> dict[str, Any]:
        email = normalize_email(email)
        validate_plan(plan)
        validate_ai_mode(ai_mode)
        customer = {
            "id": f"cus_{secrets.token_urlsafe(12)}",
            "email": email,
            "name": name.strip(),
            "company": company.strip(),
            "plan": plan,
            "ai_mode": ai_mode,
            "status": "active",
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO customers (id, email, name, company, plan, ai_mode, status, created_at)
                    VALUES (:id, :email, :name, :company, :plan, :ai_mode, :status, :created_at)
                    """,
                    customer,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Customer already exists: {email}") from exc
        return customer

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return row_to_dict(row)

    def get_customer_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM customers WHERE email = ?", (normalize_email(email),)).fetchone()
        return row_to_dict(row)

    def list_customers(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
        return [row_to_dict(row) for row in rows if row]

    def upsert_customer(
        self,
        email: str,
        name: str = "",
        company: str = "",
        plan: str = "pro_byok",
        ai_mode: str = "byok_local",
        status: str = "active",
    ) -> dict[str, Any]:
        existing = self.get_customer_by_email(email)
        if not existing:
            return self.create_customer(email, name=name, company=company, plan=plan, ai_mode=ai_mode)
        validate_plan(plan)
        validate_ai_mode(ai_mode)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE customers
                SET name = ?, company = ?, plan = ?, ai_mode = ?, status = ?
                WHERE id = ?
                """,
                (
                    name.strip() or existing["name"],
                    company.strip() or existing["company"],
                    plan,
                    ai_mode,
                    status,
                    existing["id"],
                ),
            )
        return self.get_customer(str(existing["id"]))

    def set_customer_status(self, customer_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE customers SET status = ? WHERE id = ?", (status, customer_id))
            if status != "active":
                conn.execute("UPDATE licenses SET status = 'inactive' WHERE customer_id = ?", (customer_id,))

    def issue_license(
        self,
        customer_id: str,
        plan: str | None = None,
        seats: int = 1,
        expires_at: str = "",
    ) -> dict[str, Any]:
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Unknown customer: {customer_id}")
        chosen_plan = plan or str(customer["plan"])
        validate_plan(chosen_plan)
        if seats < 1:
            raise ValueError("License seats must be at least 1.")

        key = generate_secret("ap_live_")
        license_row = {
            "id": f"lic_{secrets.token_urlsafe(12)}",
            "customer_id": customer_id,
            "key_hash": hash_secret(key),
            "key_prefix": public_prefix(key),
            "plan": chosen_plan,
            "status": "active",
            "seats": seats,
            "expires_at": expires_at,
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO licenses
                    (id, customer_id, key_hash, key_prefix, plan, status, seats, expires_at, created_at)
                VALUES
                    (:id, :customer_id, :key_hash, :key_prefix, :plan, :status, :seats, :expires_at, :created_at)
                """,
                license_row,
            )
        safe_license = dict(license_row)
        safe_license.pop("key_hash", None)
        return {"license": safe_license, "license_key": key}

    def find_license_by_key(self, license_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    licenses.*,
                    customers.email AS customer_email,
                    customers.name AS customer_name,
                    customers.company AS customer_company,
                    customers.ai_mode AS customer_ai_mode,
                    customers.status AS customer_status
                FROM licenses
                JOIN customers ON customers.id = licenses.customer_id
                WHERE licenses.key_hash = ?
                """,
                (hash_secret(license_key),),
            ).fetchone()
        record = row_to_dict(row)
        if not record or not license_is_usable(record):
            return None
        record.pop("key_hash", None)
        return record

    def get_license(self, license_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM licenses WHERE id = ?", (license_id,)).fetchone()
        record = row_to_dict(row)
        return redact_secret_fields(record) if record else None

    def active_license_for_customer(self, customer_id: str, plan: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM licenses
                WHERE customer_id = ? AND plan = ? AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
                """,
                (customer_id, plan),
            ).fetchone()
        record = row_to_dict(row)
        return redact_secret_fields(record) if record else None

    def activate_device(self, license_key: str, device_id: str, name: str = "") -> dict[str, Any]:
        license_row = self.find_license_by_key(license_key)
        if not license_row:
            raise PermissionError("Invalid or inactive license key.")
        normalized_device = device_id.strip()
        if not normalized_device:
            raise ValueError("device_id is required.")

        token = generate_secret("ap_dev_")
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM devices
                WHERE license_id = ? AND device_id = ?
                """,
                (license_row["id"], normalized_device),
            ).fetchone()
            if existing:
                device_pk = existing["id"]
                conn.execute(
                    """
                    UPDATE devices
                    SET token_hash = ?, token_prefix = ?, name = ?, status = 'active', last_seen_at = ?
                    WHERE id = ?
                    """,
                    (hash_secret(token), public_prefix(token), name.strip(), now, device_pk),
                )
            else:
                active_count = conn.execute(
                    "SELECT COUNT(*) FROM devices WHERE license_id = ? AND status = 'active'",
                    (license_row["id"],),
                ).fetchone()[0]
                if active_count >= int(license_row["seats"]):
                    raise PermissionError("License seat limit reached.")
                device_pk = f"dev_{secrets.token_urlsafe(12)}"
                conn.execute(
                    """
                    INSERT INTO devices
                        (id, customer_id, license_id, device_id, name, token_hash, token_prefix, status, last_seen_at, created_at)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        device_pk,
                        license_row["customer_id"],
                        license_row["id"],
                        normalized_device,
                        name.strip(),
                        hash_secret(token),
                        public_prefix(token),
                        now,
                        now,
                    ),
                )
            device = conn.execute("SELECT * FROM devices WHERE id = ?", (device_pk,)).fetchone()

        safe_device = row_to_dict(device)
        safe_device.pop("token_hash", None)
        return {
            "device": safe_device,
            "device_token": token,
            "customer": self.get_customer(str(license_row["customer_id"])),
            "license": redact_secret_fields(license_row),
        }

    def authenticate_device_token(self, token: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    devices.*,
                    customers.email AS customer_email,
                    customers.name AS customer_name,
                    customers.company AS customer_company,
                    customers.ai_mode AS customer_ai_mode,
                    customers.plan AS customer_plan,
                    customers.status AS customer_status,
                    licenses.status AS license_status,
                    licenses.expires_at AS license_expires_at,
                    licenses.plan AS license_plan
                FROM devices
                JOIN customers ON customers.id = devices.customer_id
                JOIN licenses ON licenses.id = devices.license_id
                WHERE devices.token_hash = ?
                """,
                (hash_secret(token),),
            ).fetchone()
        context = row_to_dict(row)
        if not context:
            return None
        if context.get("status") != "active" or context.get("customer_status") != "active":
            return None
        if context.get("license_status") != "active":
            return None
        if is_expired(str(context.get("license_expires_at") or "")):
            return None
        context.pop("token_hash", None)
        return context

    def authenticate_any_token(self, token: str) -> dict[str, Any] | None:
        if token.startswith("ap_dev_"):
            return self.authenticate_device_token(token)
        if token.startswith("ap_live_"):
            license_row = self.find_license_by_key(token)
            if not license_row:
                return None
            return {
                "id": "",
                "customer_id": license_row["customer_id"],
                "license_id": license_row["id"],
                "device_id": "",
                "name": "license",
                "customer_email": license_row.get("customer_email", ""),
                "customer_name": license_row.get("customer_name", ""),
                "customer_company": license_row.get("customer_company", ""),
                "customer_ai_mode": license_row.get("customer_ai_mode", ""),
                "customer_plan": license_row.get("plan", ""),
                "license_plan": license_row.get("plan", ""),
                "auth_type": "license",
            }
        return None

    def sync_dashboard(self, context: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        customer_id = str(context["customer_id"])
        device_pk = str(context.get("id") or "")
        now = utc_now()
        snapshot = dict(payload)
        snapshot["saas"] = account_summary(context, now)
        encoded = json.dumps(snapshot, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dashboard_snapshots (customer_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (customer_id, encoded, now),
            )
            conn.execute(
                """
                INSERT INTO sync_events (id, customer_id, device_pk, kind, payload, created_at)
                VALUES (?, ?, ?, 'dashboard_sync', ?, ?)
                """,
                (f"sync_{secrets.token_urlsafe(12)}", customer_id, device_pk, encoded, now),
            )
            conn.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (now, device_pk))
        return {"status": "ok", "synced_at": now, "customer_id": customer_id}

    def dashboard_for_context(self, context: dict[str, Any]) -> dict[str, Any]:
        customer_id = str(context["customer_id"])
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload, updated_at FROM dashboard_snapshots WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
        if not row:
            return empty_dashboard(context)
        payload = json.loads(row["payload"])
        payload["saas"] = account_summary(context, str(row["updated_at"]))
        return payload

    def create_billing_checkout(
        self,
        provider: str,
        email: str,
        name: str,
        company: str,
        plan: str,
        ai_mode: str,
        seats: int,
    ) -> dict[str, Any]:
        validate_plan(plan)
        validate_ai_mode(ai_mode)
        if seats < 1:
            raise ValueError("Seats must be at least 1.")
        claim_token = generate_secret("ap_claim_")
        checkout = {
            "id": f"chk_{secrets.token_urlsafe(12)}",
            "provider": provider,
            "claim_hash": hash_secret(claim_token),
            "email": normalize_email(email),
            "name": name.strip(),
            "company": company.strip(),
            "plan": plan,
            "ai_mode": ai_mode,
            "seats": seats,
            "status": "created",
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO billing_checkouts
                    (id, provider, claim_hash, email, name, company, plan, ai_mode, seats, status, created_at)
                VALUES
                    (:id, :provider, :claim_hash, :email, :name, :company, :plan, :ai_mode, :seats, :status, :created_at)
                """,
                checkout,
            )
        safe = dict(checkout)
        safe.pop("claim_hash", None)
        return {"checkout": safe, "claim_token": claim_token}

    def set_billing_checkout_reference(self, checkout_id: str, external_reference: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE billing_checkouts SET external_reference = ? WHERE id = ?",
                (external_reference, checkout_id),
            )

    def get_billing_checkout(self, checkout_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM billing_checkouts WHERE id = ?", (checkout_id,)).fetchone()
        record = row_to_dict(row)
        if record:
            record.pop("claim_hash", None)
        return record

    def reserve_billing_event(self, provider: str, event_id: str, event_type: str) -> bool:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT status FROM billing_events WHERE provider = ? AND event_id = ?",
                (provider, event_id),
            ).fetchone()
            if existing and existing["status"] == "complete":
                return False
            if existing:
                conn.execute(
                    """
                    UPDATE billing_events
                    SET event_type = ?, status = 'processing', error = ''
                    WHERE provider = ? AND event_id = ?
                    """,
                    (event_type, provider, event_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO billing_events (id, provider, event_id, event_type, status, created_at)
                    VALUES (?, ?, ?, ?, 'processing', ?)
                    """,
                    (f"evt_{secrets.token_urlsafe(12)}", provider, event_id, event_type, utc_now()),
                )
        return True

    def complete_billing_event(self, provider: str, event_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE billing_events
                SET status = 'complete', completed_at = ?, error = ''
                WHERE provider = ? AND event_id = ?
                """,
                (utc_now(), provider, event_id),
            )

    def fail_billing_event(self, provider: str, event_id: str, error: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE billing_events
                SET status = 'error', completed_at = ?, error = ?
                WHERE provider = ? AND event_id = ?
                """,
                (utc_now(), error[:1000], provider, event_id),
            )

    def fulfill_billing_checkout(
        self,
        checkout_id: str,
        encrypt_license_key: Callable[[str], str],
        external_reference: str = "",
    ) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM billing_checkouts WHERE id = ?", (checkout_id,)).fetchone()
        checkout = row_to_dict(row)
        if not checkout:
            raise ValueError(f"Unknown billing checkout: {checkout_id}")
        if checkout["status"] == "paid" and checkout["license_id"]:
            return {
                "checkout": self.get_billing_checkout(checkout_id),
                "customer": self.get_customer(str(checkout["customer_id"])),
                "license": self.get_license(str(checkout["license_id"])),
                "created": False,
            }

        customer = self.upsert_customer(
            email=str(checkout["email"]),
            name=str(checkout["name"]),
            company=str(checkout["company"]),
            plan=str(checkout["plan"]),
            ai_mode=str(checkout["ai_mode"]),
            status="active",
        )
        license_key = generate_secret("ap_live_")
        encrypted_license_key = encrypt_license_key(license_key)
        license_row = {
            "id": f"lic_{secrets.token_urlsafe(12)}",
            "customer_id": customer["id"],
            "key_hash": hash_secret(license_key),
            "key_prefix": public_prefix(license_key),
            "plan": checkout["plan"],
            "status": "active",
            "seats": int(checkout["seats"]),
            "expires_at": "",
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO licenses
                    (id, customer_id, key_hash, key_prefix, plan, status, seats, expires_at, created_at)
                VALUES
                    (:id, :customer_id, :key_hash, :key_prefix, :plan, :status, :seats, :expires_at, :created_at)
                """,
                license_row,
            )
            conn.execute(
                """
                UPDATE billing_checkouts
                SET status = 'paid', external_reference = ?, customer_id = ?, license_id = ?,
                    encrypted_license_key = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    external_reference or checkout["external_reference"],
                    customer["id"],
                    license_row["id"],
                    encrypted_license_key,
                    utc_now(),
                    checkout_id,
                ),
            )
        return {
            "checkout": self.get_billing_checkout(checkout_id),
            "customer": customer,
            "license": redact_secret_fields(license_row),
            "license_key": license_key,
            "created": True,
        }

    def claim_billing_checkout(self, claim_token: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM billing_checkouts WHERE claim_hash = ?",
                (hash_secret(claim_token),),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE billing_checkouts SET claimed_at = ? WHERE id = ?",
                    (utc_now(), row["id"]),
                )
        record = row_to_dict(row)
        if record:
            record.pop("claim_hash", None)
        return record

    def upsert_billing_subscription(
        self,
        customer_id: str,
        provider: str,
        external_subscription_id: str,
        plan: str,
        ai_mode: str,
        status: str,
        external_customer_id: str = "",
        current_period_end: str = "",
    ) -> dict[str, Any]:
        if not external_subscription_id:
            raise ValueError("External subscription ID is required.")
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO billing_subscriptions
                    (id, customer_id, provider, external_customer_id, external_subscription_id,
                     plan, ai_mode, status, current_period_end, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, external_subscription_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    external_customer_id = excluded.external_customer_id,
                    plan = excluded.plan,
                    ai_mode = excluded.ai_mode,
                    status = excluded.status,
                    current_period_end = excluded.current_period_end,
                    updated_at = excluded.updated_at
                """,
                (
                    f"sub_{secrets.token_urlsafe(12)}",
                    customer_id,
                    provider,
                    external_customer_id,
                    external_subscription_id,
                    plan,
                    ai_mode,
                    status,
                    current_period_end,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM billing_subscriptions
                WHERE provider = ? AND external_subscription_id = ?
                """,
                (provider, external_subscription_id),
            ).fetchone()
        return row_to_dict(row)

    def update_billing_subscription_status(
        self,
        provider: str,
        external_subscription_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE billing_subscriptions SET status = ?, updated_at = ?
                WHERE provider = ? AND external_subscription_id = ?
                """,
                (status, utc_now(), provider, external_subscription_id),
            )
            row = conn.execute(
                """
                SELECT * FROM billing_subscriptions
                WHERE provider = ? AND external_subscription_id = ?
                """,
                (provider, external_subscription_id),
            ).fetchone()
        subscription = row_to_dict(row)
        if subscription and status in {"cancelled", "canceled", "expired", "unpaid"}:
            self.set_customer_status(str(subscription["customer_id"]), "inactive")
        return subscription


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("A valid email is required.")
    return email


def validate_plan(plan: str) -> None:
    if plan not in PLAN_IDS:
        raise ValueError(f"Invalid plan: {plan}. Use one of: {', '.join(sorted(PLAN_IDS))}")


def validate_ai_mode(ai_mode: str) -> None:
    if ai_mode not in AI_MODES:
        raise ValueError(f"Invalid AI mode: {ai_mode}. Use one of: {', '.join(sorted(AI_MODES))}")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def redact_secret_fields(row: dict[str, Any]) -> dict[str, Any]:
    clean = dict(row)
    clean.pop("key_hash", None)
    clean.pop("token_hash", None)
    return clean


def is_expired(expires_at: str) -> bool:
    return bool(expires_at and expires_at < utc_now())


def license_is_usable(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "active"
        and row.get("customer_status") == "active"
        and not is_expired(str(row.get("expires_at") or ""))
    )


def account_summary(context: dict[str, Any], synced_at: str) -> dict[str, Any]:
    return {
        "customer_id": context.get("customer_id"),
        "email": context.get("customer_email", ""),
        "name": context.get("customer_name", ""),
        "company": context.get("customer_company", ""),
        "plan": context.get("customer_plan") or context.get("license_plan", ""),
        "ai_mode": context.get("customer_ai_mode", ""),
        "device_id": context.get("device_id", ""),
        "device_name": context.get("name", ""),
        "synced_at": synced_at,
    }


def empty_dashboard(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "workspace": "",
        "policy": {},
        "summary": {
            "jobs": 0,
            "evaluations": 0,
            "shortlisted": 0,
            "easy_apply_jobs": 0,
            "application_records": 0,
            "completed_jobs": 0,
            "applied_today": 0,
            "native_linkedin_applied": 0,
            "native_naukri_applied": 0,
            "legacy_linkedin_applied": 0,
            "legacy_naukri_applied": 0,
            "leads": 0,
            "lead_emails": 0,
        },
        "sources": [],
        "runs": [],
        "series": [],
        "jobs": [],
        "providers": [],
        "decisions": [],
        "statuses": [],
        "commands": [],
        "saas": account_summary(context, utc_now()),
    }
