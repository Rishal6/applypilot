# SaaS MVP Flow

ApplyPilot is a local-first SaaS. The desktop app executes browser automation on the user's machine; the SaaS owns account state, licensing, dashboard sync, and paid AI modes.

## Product Flow

```text
1. Customer pays on website
2. Billing webhook creates SaaS customer + license
3. Customer installs desktop app
4. Desktop activates with license and receives a device token
5. Desktop runs the local agent against logged-in Chrome
6. Desktop syncs normalized dashboard data to SaaS
7. Customer views dashboard from web
```

## AI Modes

- `byok_local`: user API keys stay on desktop; SaaS sells software, dashboard, and updates.
- `byok_cloud`: user provides API key to SaaS for server-side scoring and form answers.
- `managed_api`: user pays us for included AI credits; we route to provider APIs.
- `hosted_model`: we run our own model for scoring/extraction.
- `hybrid`: hosted model first, premium API fallback when confidence is low.

## Protected Code Boundary

Desktop app should contain only the local executor:

- browser connection
- DOM/page reader
- local queue
- click/type/submit executor
- device token sync client

SaaS should contain the paid product brain:

- license and billing status
- premium scoring policies
- managed model routing
- analytics and dashboards
- team/cohort features

## Current Implementation

- `applypilot serve`: runs FastAPI SaaS API and serves the web dashboard.
- `applypilot saas-create-customer`: creates a dev customer/license.
- `applypilot saas-activate`: activates a desktop device and stores `.applypilot/saas_auth.json`.
- `applypilot saas-sync`: pushes local dashboard data to SaaS.
- `applypilot saas-me`: verifies the active SaaS account.

## Production Swap

Replace `saas-create-customer` with a Stripe/Razorpay webhook:

```text
checkout.paid -> create customer -> issue license -> email activation link
```

Keep plaintext license/device secrets one-time only. The database stores hashes.
