# Billing

ApplyPilot supports Razorpay Standard Checkout for the current hosted checkout flow, plus the earlier Stripe/Razorpay subscription webhook spine for future recurring billing.

## Current Razorpay Standard Checkout flow

```text
customer opens /checkout.html
-> backend creates billing checkout row
-> backend creates Razorpay order
-> Razorpay Checkout modal collects payment
-> frontend sends payment id/order id/signature to backend
-> backend verifies HMAC signature
-> customer + license provisioned
-> encrypted license stored
-> license key returned once to the checkout page
-> desktop activates with license
```

Important safety rule: `APPLYPILOT_FULFILLMENT_SECRET` must be configured before `/api/create-order` creates a Razorpay order. This prevents collecting payment when the server cannot issue a license.

## Subscription webhook flow

```text
checkout created
-> claim token saved in the customer's browser
-> Stripe/Razorpay subscription payment
-> signed webhook verifies raw request body
-> customer + license provisioned
-> encrypted license stored
-> customer claims license from checkout page
-> desktop activates with license
```

## Required Environment

Set a long random secret:

```bash
APPLYPILOT_FULFILLMENT_SECRET=...
```

This encrypts fulfilled license keys. Do not change it after accepting payments unless existing fulfillment records are migrated.

### Stripe

```bash
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
APPLYPILOT_STRIPE_PRICE_PRO_BYOK=price_...
APPLYPILOT_STRIPE_PRICE_PRO_MANAGED=price_...
APPLYPILOT_STRIPE_PRICE_TEAM=price_...
```

Webhook URL:

```text
https://your-domain.example/api/v1/webhooks/stripe
```

Subscribe to:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`

### Razorpay

```bash
RAZORPAY_KEY_ID=rzp_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
APPLYPILOT_RAZORPAY_PLAN_PRO_BYOK=plan_...
APPLYPILOT_RAZORPAY_PLAN_PRO_MANAGED=plan_...
APPLYPILOT_RAZORPAY_PLAN_TEAM=plan_...
```

For Standard Checkout, only `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `APPLYPILOT_FULFILLMENT_SECRET` are required. `RAZORPAY_WEBHOOK_SECRET` and plan IDs are for subscription webhooks.

Webhook URL:

```text
https://your-domain.example/api/v1/webhooks/razorpay
```

Subscribe to:

- `subscription.activated`
- `subscription.charged`
- `subscription.cancelled`
- `subscription.completed`
- `subscription.halted`

Razorpay webhook verification uses the raw request body and `X-Razorpay-Signature`. Duplicate events are identified by `X-Razorpay-Event-Id`.

## Local Test

Start the SaaS server with test secrets:

```bash
APPLYPILOT_FULFILLMENT_SECRET=local-development-secret \
STRIPE_WEBHOOK_SECRET=whsec_test \
RAZORPAY_WEBHOOK_SECRET=razorpay_test \
PYTHONPATH=src python3 -m applypilot --workspace . serve
```

The automated tests generate correctly signed synthetic Stripe and Razorpay events without making a real payment.

For Razorpay test mode, avoid scanning UPI QR codes with a real banking app. Use Razorpay test card or netbanking flows, then confirm the checkout page returns a desktop license key.
