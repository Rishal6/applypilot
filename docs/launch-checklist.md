# ApplyPilot launch checklist

Use this checklist before sharing ApplyPilot with a real buyer.

## 1. Code and landing page

- Confirm CI is green on `main`.
- Confirm the landing page is live at `https://rishal6.github.io/applypilot/`.
- Confirm legal pages are reachable:
  - `https://rishal6.github.io/applypilot/privacy.html`
  - `https://rishal6.github.io/applypilot/terms.html`
  - `https://rishal6.github.io/applypilot/refund.html`
- Keep landing CTAs on email/manual sales until the Render checkout backend is deployed and smoke-tested.

## 2. Render SaaS backend

- Deploy the Docker service from `render.yaml`.
- Set required Render secrets:
  - `APPLYPILOT_ADMIN_TOKEN`
  - `APPLYPILOT_FULFILLMENT_SECRET`
  - `RAZORPAY_KEY_ID`
  - `RAZORPAY_KEY_SECRET`
- Keep `APPLYPILOT_FULFILLMENT_SECRET` stable after the first real payment. It encrypts one-time license recovery records.
- Open the health URL:

```text
https://YOUR_RENDER_SERVICE.onrender.com/api/v1/health
```

Expected response:

```json
{"status":"ok","version":"0.1.0"}
```

## 3. Checkout smoke test

- Open:

```text
https://YOUR_RENDER_SERVICE.onrender.com/checkout.html?plan=pro_byok&provider=razorpay
```

- Create a Razorpay test order.
- Use Razorpay test card or netbanking flows. Do not scan UPI QR with a real bank app in test mode.
- Confirm the checkout page shows a desktop license key after payment verification.
- Copy the license and activate locally:

```bash
PYTHONPATH=src python3 -m applypilot --workspace . saas-activate \
  --endpoint https://YOUR_RENDER_SERVICE.onrender.com \
  --license-key ap_live_...
```

## 4. Live Razorpay readiness

- Switch Render from `rzp_test_...` credentials to live Razorpay credentials only after Razorpay account/KYC/bank activation is complete.
- Make one low-risk live payment.
- Confirm:
  - Razorpay payment captured successfully
  - ApplyPilot issued one license
  - license activation works from the desktop app
  - refund/cancellation process is understood

## 5. Customer handoff

Send early customers:

1. landing page link;
2. checkout link or manual payment instructions;
3. license key after payment;
4. install command:

```bash
pip install applypilot-ai
```

5. activation endpoint:

```text
https://YOUR_RENDER_SERVICE.onrender.com
```

## 6. Do not ship without these

- No secret committed to Git.
- `APPLYPILOT_FULFILLMENT_SECRET` configured before accepting payments.
- Render persistent disk attached at `/data`.
- At least one end-to-end test payment creates a license.
- Legal pages linked from landing and checkout.
