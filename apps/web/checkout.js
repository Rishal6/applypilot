const checkoutState = {
  plan: "pro_byok",
  aiMode: "byok_local",
  provider: "razorpay",
};

const planAmounts = {
  pro_byok: 99900,
  pro_managed: 199900,
  team: 499900,
};

const checkoutElements = {
  planGrid: document.getElementById("planGrid"),
  form: document.getElementById("checkoutForm"),
  email: document.getElementById("checkoutEmail"),
  name: document.getElementById("checkoutName"),
  company: document.getElementById("checkoutCompany"),
  seats: document.getElementById("checkoutSeats"),
  phone: document.getElementById("checkoutPhone"),
  phoneField: document.querySelector(".phone-field"),
  submit: document.getElementById("checkoutSubmit"),
  summaryPlan: document.getElementById("summaryPlan"),
  summaryMode: document.getElementById("summaryMode"),
  summarySeats: document.getElementById("summarySeats"),
  summaryAmount: document.getElementById("summaryAmount"),
  paymentResult: document.getElementById("paymentResult"),
  paymentStatus: document.getElementById("paymentStatus"),
  paymentReference: document.getElementById("paymentReference"),
  claimButton: document.getElementById("claimButton"),
  licenseResult: document.getElementById("licenseResult"),
  licenseKey: document.getElementById("licenseKey"),
  copyLicense: document.getElementById("copyLicense"),
  toast: document.getElementById("toast"),
};

checkoutElements.planGrid.querySelectorAll(".plan-option").forEach((button) => {
  button.addEventListener("click", () => {
    checkoutElements.planGrid.querySelectorAll(".plan-option").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    checkoutState.plan = button.dataset.plan;
    checkoutState.aiMode = button.dataset.aiMode;
    renderCheckoutSummary();
  });
});

document.querySelectorAll("[data-provider]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-provider]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    checkoutState.provider = button.dataset.provider;
    renderProviderState();
  });
});

checkoutElements.seats.addEventListener("input", renderCheckoutSummary);

checkoutElements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (checkoutState.provider === "razorpay") {
    await startRazorpayStandardCheckout();
    return;
  }
  checkoutElements.submit.disabled = true;
  checkoutElements.submit.textContent = "Creating secure checkout...";
  try {
    const response = await fetch(`/api/v1/billing/checkout/${checkoutState.provider}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        email: checkoutElements.email.value,
        name: checkoutElements.name.value,
        company: checkoutElements.company.value,
        seats: Number(checkoutElements.seats.value || 1),
        phone: checkoutElements.phone.value,
        plan: checkoutState.plan,
        ai_mode: checkoutState.aiMode,
        success_url: `${window.location.origin}/checkout.html?paid=1&session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: `${window.location.origin}/checkout.html?cancelled=1`,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    localStorage.setItem("applypilot.billing.claim_token", data.claim_token);
    localStorage.setItem("applypilot.billing.provider", data.provider);
    window.location.assign(data.checkout_url);
  } catch (error) {
    showCheckoutToast(error.message);
    checkoutElements.submit.disabled = false;
    checkoutElements.submit.textContent = `Continue to ${formatLabel(checkoutState.provider)}`;
  }
});

async function startRazorpayStandardCheckout() {
  checkoutElements.submit.disabled = true;
  checkoutElements.submit.textContent = "Creating Razorpay order...";
  hidePaymentResult();
  hideLicenseResult();
  try {
    await ensureRazorpayLoaded();
    const orderResponse = await fetch("/api/create-order", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        currency: "INR",
        email: checkoutElements.email.value,
        name: checkoutElements.name.value,
        company: checkoutElements.company.value,
        phone: checkoutElements.phone.value,
        seats: Number(checkoutElements.seats.value || 1),
        plan: checkoutState.plan,
        ai_mode: checkoutState.aiMode,
      }),
    });
    const order = await orderResponse.json();
    if (!orderResponse.ok) {
      throw new Error(order.detail || `HTTP ${orderResponse.status}`);
    }
    localStorage.setItem("applypilot.billing.claim_token", order.claim_token || "");
    localStorage.setItem("applypilot.billing.provider", "razorpay_standard");

    let completed = false;
    const razorpay = new window.Razorpay({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      name: "ApplyPilot",
      description: `${formatLabel(checkoutState.plan)} · ${checkoutElements.seats.value || 1} seat(s)`,
      order_id: order.order_id,
      prefill: {
        name: checkoutElements.name.value,
        email: checkoutElements.email.value,
        contact: checkoutElements.phone.value,
      },
      notes: {
        plan: checkoutState.plan,
        ai_mode: checkoutState.aiMode,
        seats: String(Number(checkoutElements.seats.value || 1)),
      },
      theme: {
        color: "#111820",
      },
      handler: async (payment) => {
        completed = true;
        await verifyRazorpayPayment(payment);
      },
      modal: {
        ondismiss: () => {
          if (!completed) {
            checkoutElements.submit.disabled = false;
            checkoutElements.submit.textContent = "Continue to Razorpay";
            showCheckoutToast("Payment cancelled");
          }
        },
      },
    });
    razorpay.on("payment.failed", (response) => {
      completed = true;
      checkoutElements.submit.disabled = false;
      checkoutElements.submit.textContent = "Continue to Razorpay";
      const description = response?.error?.description || response?.error?.reason || "Payment failed";
      showPaymentResult("Payment failed", description);
      showCheckoutToast(description);
    });
    checkoutElements.submit.textContent = "Waiting for payment...";
    razorpay.open();
  } catch (error) {
    checkoutElements.submit.disabled = false;
    checkoutElements.submit.textContent = "Continue to Razorpay";
    showCheckoutToast(error.message);
  }
}

function ensureRazorpayLoaded() {
  if (window.Razorpay) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const timer = window.setTimeout(() => {
      script.remove();
      reject(new Error("Razorpay Checkout script did not load. Please refresh and try again."));
    }, 8000);
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => {
      window.clearTimeout(timer);
      if (window.Razorpay) {
        resolve();
      } else {
        reject(new Error("Razorpay Checkout script did not load. Please refresh and try again."));
      }
    };
    script.onerror = () => {
      window.clearTimeout(timer);
      reject(new Error("Could not load Razorpay Checkout. Check your connection and try again."));
    };
    document.head.appendChild(script);
  });
}

async function verifyRazorpayPayment(payment) {
  try {
    const response = await fetch("/api/verify-payment", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        razorpay_payment_id: payment.razorpay_payment_id,
        razorpay_order_id: payment.razorpay_order_id,
        razorpay_signature: payment.razorpay_signature,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    showPaymentResult("Payment verified", `Payment: ${data.payment_id}`);
    if (data.license_key) {
      checkoutElements.licenseKey.textContent = data.license_key;
      checkoutElements.licenseResult.hidden = false;
    }
    showCheckoutToast("Payment verified");
  } catch (error) {
    showPaymentResult("Verification failed", error.message);
    showCheckoutToast(error.message);
  } finally {
    checkoutElements.submit.disabled = false;
    checkoutElements.submit.textContent = "Continue to Razorpay";
  }
}

checkoutElements.claimButton.addEventListener("click", claimLicense);
checkoutElements.copyLicense.addEventListener("click", async () => {
  await navigator.clipboard.writeText(checkoutElements.licenseKey.textContent || "");
  showCheckoutToast("License copied");
});

async function claimLicense() {
  const claimToken = localStorage.getItem("applypilot.billing.claim_token") || "";
  if (!claimToken) {
    showCheckoutToast("No checkout claim found in this browser");
    return;
  }
  checkoutElements.claimButton.disabled = true;
  checkoutElements.claimButton.textContent = "Checking...";
  try {
    const response = await fetch("/api/v1/billing/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ claim_token: claimToken }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    if (data.status !== "paid" || !data.license_key) {
      showCheckoutToast("Payment is not confirmed yet");
      return;
    }
    checkoutElements.licenseKey.textContent = data.license_key;
    checkoutElements.licenseResult.hidden = false;
    showCheckoutToast("License ready");
  } catch (error) {
    showCheckoutToast(error.message);
  } finally {
    checkoutElements.claimButton.disabled = false;
    checkoutElements.claimButton.textContent = "Check payment";
  }
}

function renderCheckoutSummary() {
  checkoutElements.summaryPlan.textContent = formatLabel(checkoutState.plan);
  checkoutElements.summaryMode.textContent = formatLabel(checkoutState.aiMode);
  checkoutElements.summarySeats.textContent = String(Number(checkoutElements.seats.value || 1));
  checkoutElements.summaryAmount.textContent = formatCurrency(selectedAmount());
}

function formatLabel(value) {
  const acronyms = new Set(["ai", "api", "byok", "cli"]);
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      return acronyms.has(lower) ? lower.toUpperCase() : lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
}

function showCheckoutToast(message) {
  checkoutElements.toast.textContent = message;
  checkoutElements.toast.classList.add("show");
  window.clearTimeout(showCheckoutToast.timer);
  showCheckoutToast.timer = window.setTimeout(() => checkoutElements.toast.classList.remove("show"), 2600);
}

function selectedAmount() {
  return (planAmounts[checkoutState.plan] || planAmounts.pro_byok) * Number(checkoutElements.seats.value || 1);
}

function formatCurrency(amountPaise) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amountPaise / 100);
}

function showPaymentResult(status, reference) {
  checkoutElements.paymentStatus.textContent = status;
  checkoutElements.paymentReference.textContent = reference;
  checkoutElements.paymentResult.hidden = false;
}

function hidePaymentResult() {
  checkoutElements.paymentResult.hidden = true;
  checkoutElements.paymentReference.textContent = "";
}

function hideLicenseResult() {
  checkoutElements.licenseResult.hidden = true;
  checkoutElements.licenseKey.textContent = "";
}

const query = new URLSearchParams(window.location.search);
applyInitialCheckoutQuery(query);
if (query.get("paid") === "1") {
  claimLicense();
}
if (query.get("cancelled") === "1") {
  showCheckoutToast("Checkout cancelled");
}
renderCheckoutSummary();
renderProviderState();

function renderProviderState() {
  checkoutElements.phoneField.hidden = checkoutState.provider !== "razorpay";
  checkoutElements.submit.textContent = `Continue to ${formatLabel(checkoutState.provider)}`;
}

function applyInitialCheckoutQuery(queryParams) {
  const requestedPlan = queryParams.get("plan");
  if (requestedPlan) {
    checkoutElements.planGrid.querySelectorAll(".plan-option").forEach((button) => {
      if (button.dataset.plan === requestedPlan) {
        checkoutElements.planGrid.querySelectorAll(".plan-option").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        checkoutState.plan = button.dataset.plan;
        checkoutState.aiMode = button.dataset.aiMode;
      }
    });
  }

  const requestedProvider = queryParams.get("provider");
  if (requestedProvider) {
    document.querySelectorAll("[data-provider]").forEach((button) => {
      if (button.dataset.provider === requestedProvider) {
        document.querySelectorAll("[data-provider]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        checkoutState.provider = button.dataset.provider;
      }
    });
  }
}
