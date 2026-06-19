const checkoutState = {
  plan: "pro_byok",
  aiMode: "byok_local",
  provider: "razorpay",
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

const query = new URLSearchParams(window.location.search);
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
