# Render deployment guide

This deploys the ApplyPilot SaaS API, hosted checkout page, license issuing, and dashboard static files.

## Deploy from GitHub

1. Push the repo to GitHub.
2. In Render, choose **New +** → **Blueprint**.
3. Connect `github.com/Rishal6/applypilot`.
4. Render should detect `render.yaml` and create `applypilot-saas`.
5. Keep the persistent disk mounted at `/data`.

## Required environment variables

The non-secret defaults are already in `render.yaml`:

```text
APPLYPILOT_WEB_DIR=/app/apps/web
APPLYPILOT_SAAS_DB=/data/applypilot.sqlite3
APPLYPILOT_ALLOWED_ORIGINS=https://rishal6.github.io,https://applypilot.vercel.app
```

Set these as Render secrets:

```text
APPLYPILOT_ADMIN_TOKEN=long-random-admin-token
APPLYPILOT_FULFILLMENT_SECRET=long-random-fulfillment-secret
RAZORPAY_KEY_ID=rzp_test_or_live_...
RAZORPAY_KEY_SECRET=...
```

Optional Stripe/subscription variables can stay blank while Razorpay Standard Checkout is the active payment path.

## Health check

After deploy, open:

```text
https://YOUR_RENDER_SERVICE.onrender.com/api/v1/health
```

Expected:

```json
{"status":"ok","version":"0.1.0"}
```

## Hosted checkout

Open:

```text
https://YOUR_RENDER_SERVICE.onrender.com/checkout.html?plan=pro_byok&provider=razorpay
```

The backend creates the Razorpay order server-side. The browser only receives the public Razorpay key ID and order ID.

## Landing page update after backend is live

Once checkout is smoke-tested, update the landing pricing CTAs from email links to hosted checkout links:

```text
https://YOUR_RENDER_SERVICE.onrender.com/checkout.html?plan=pro_byok&provider=razorpay
https://YOUR_RENDER_SERVICE.onrender.com/checkout.html?plan=pro_managed&provider=razorpay
```

Keep the Team plan as contact/manual sales until seat onboarding is smooth.

## Razorpay test-mode notes

- `rzp_test_...` credentials are test mode.
- Real bank/UPI apps should not be used to scan test-mode QR codes.
- Use Razorpay test card or netbanking flows for test-mode verification.
- Switch to live credentials only after Razorpay KYC, bank account, and account activation are complete.

## Rollback

If checkout breaks after deploy:

1. move landing CTAs back to email/manual sales;
2. keep the Render service online for existing license activation;
3. inspect `/api/v1/health`;
4. restore the previous Git commit and redeploy.
