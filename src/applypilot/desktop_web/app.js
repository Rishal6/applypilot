const desktopElements = {
  status: document.getElementById("agentStatus"),
  policyMode: document.getElementById("policyMode"),
  dailyLimit: document.getElementById("dailyLimit"),
  minScore: document.getElementById("minScore"),
  accountPlan: document.getElementById("accountPlan"),
  accountEmail: document.getElementById("accountEmail"),
  activationForm: document.getElementById("activationForm"),
  endpoint: document.getElementById("endpoint"),
  licenseKey: document.getElementById("licenseKey"),
  mode: document.getElementById("runMode"),
  confirm: document.getElementById("confirmSubmit"),
  run: document.getElementById("runButton"),
  stop: document.getElementById("stopButton"),
  sync: document.getElementById("syncButton"),
  dashboard: document.getElementById("openDashboard"),
  log: document.getElementById("agentLog"),
  toast: document.getElementById("toast"),
};

let desktopStatus = {};

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    desktopStatus = await response.json();
    renderStatus();
  } catch (error) {
    showToast(error.message);
  }
}

function renderStatus() {
  const policy = desktopStatus.policy || {};
  const customer = desktopStatus.customer || {};
  desktopElements.status.textContent = desktopStatus.running ? `Running ${desktopStatus.mode}` : "Idle";
  desktopElements.policyMode.textContent = formatLabel(policy.mode || "review-only");
  desktopElements.dailyLimit.textContent = policy.max_applications_per_day || 0;
  desktopElements.minScore.textContent = policy.min_score_to_submit || 0;
  desktopElements.accountPlan.textContent = customer.plan ? formatLabel(customer.plan) : "Not connected";
  desktopElements.accountEmail.textContent = customer.email || "Activate this device";
  desktopElements.endpoint.value = desktopStatus.endpoint || desktopElements.endpoint.value;
  desktopElements.log.textContent = (desktopStatus.logs || []).join("\n") || "Waiting for agent activity.";
  desktopElements.run.disabled = Boolean(desktopStatus.running);
  desktopElements.stop.disabled = !desktopStatus.running;
}

desktopElements.activationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await send("/api/activate", {
    endpoint: desktopElements.endpoint.value,
    license_key: desktopElements.licenseKey.value,
    device_id: navigator.userAgent,
    device_name: "ApplyPilot Desktop",
  });
  desktopElements.licenseKey.value = "";
  await refreshStatus();
});

desktopElements.run.addEventListener("click", async () => {
  await send("/api/run", {
    mode: desktopElements.mode.value,
    confirmed: desktopElements.confirm.checked,
  });
  await refreshStatus();
});

desktopElements.stop.addEventListener("click", async () => {
  await send("/api/stop", {});
  await refreshStatus();
});

desktopElements.sync.addEventListener("click", async () => {
  await send("/api/sync", {});
  showToast("Dashboard synced");
  await refreshStatus();
});

desktopElements.dashboard.addEventListener("click", () => {
  window.open(desktopStatus.endpoint || "http://127.0.0.1:8787", "_blank", "noopener");
});

async function send(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    showToast(data.detail || `HTTP ${response.status}`);
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

function formatLabel(value) {
  const acronyms = new Set(["ai", "api", "byok"]);
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

function showToast(message) {
  desktopElements.toast.textContent = message;
  desktopElements.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => desktopElements.toast.classList.remove("show"), 2400);
}

refreshStatus();
window.setInterval(refreshStatus, 1800);
