const PROFILE_KEY = "applypilot.career.profile";
const MESSAGE_KEY = "applypilot.career.messages";
const startupQuery = new URLSearchParams(window.location.search);

if (startupQuery.get("fresh") === "1" || startupQuery.get("reset") === "1") {
  resetLocalCareerStorage();
  removeStartupResetQuery();
}

const state = {
  data: null,
  jobs: [],
  desktop: Boolean(window.APPLYPILOT_DESKTOP),
  connection: loadConnection(),
  profile: loadProfile(),
  messages: Boolean(window.APPLYPILOT_DESKTOP) ? [] : loadMessages(),
  onboardingStep: "",
  profileSave: Promise.resolve(),
  providerStatus: null,
};

const onboardingSteps = [
  {
    key: "target",
    question: "What kind of work do you want next? A role, field, or even a rough direction is enough.",
    placeholder: "For example: AI engineer, remote Python roles, product design…",
  },
  {
    key: "background",
    question: "Tell me what you’ve done so far. Jobs, freelance work, projects, education, or things you built all count.",
    placeholder: "For example: I built a RAG assistant and worked two years as a Python developer…",
  },
  {
    key: "skills",
    question: "Which skills or tools are you comfortable using? You can write them naturally or separate them with commas.",
    placeholder: "Python, FastAPI, AWS, customer support, Excel…",
  },
  {
    key: "location",
    question: "Where do you want to work, and are you open to remote or relocation?",
    placeholder: "Bengaluru, remote India, willing to relocate…",
  },
  {
    key: "name",
    question: "What name should I put on your career profile and resume?",
    placeholder: "Your name",
  },
  {
    key: "email",
    question: "What email should employers use? You can type “skip” if you want to add it later.",
    placeholder: "you@example.com or skip",
  },
];

const elements = {
  accountPlan: document.getElementById("accountPlan"),
  accountMode: document.getElementById("accountMode"),
  syncState: document.getElementById("syncState"),
  chatFeed: document.getElementById("chatFeed"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  newConversation: document.getElementById("newConversation"),
  refreshButton: document.getElementById("refreshButton"),
  connectButton: document.getElementById("connectButton"),
  connectModal: document.getElementById("connectModal"),
  connectForm: document.getElementById("connectForm"),
  closeConnect: document.getElementById("closeConnect"),
  clearConnection: document.getElementById("clearConnection"),
  apiEndpoint: document.getElementById("apiEndpoint"),
  apiToken: document.getElementById("apiToken"),
  connectTitle: document.getElementById("connectTitle"),
  connectTokenLabel: document.getElementById("connectTokenLabel"),
  connectSubmit: document.getElementById("connectSubmit"),
  toast: document.getElementById("toast"),
  profileName: document.getElementById("profileName"),
  profileProgress: document.getElementById("profileProgress"),
  profilePercent: document.getElementById("profilePercent"),
  sidebarProfilePercent: document.getElementById("sidebarProfilePercent"),
  sidebarJobCount: document.getElementById("sidebarJobCount"),
  sidebarProvider: document.getElementById("sidebarProvider"),
  profileTarget: document.getElementById("profileTarget"),
  profileBackground: document.getElementById("profileBackground"),
  profileLocation: document.getElementById("profileLocation"),
  todayApplied: document.getElementById("todayApplied"),
  shortlistCount: document.getElementById("shortlistCount"),
  dailyLimit: document.getElementById("dailyLimit"),
  policyMode: document.getElementById("policyMode"),
  agentState: document.getElementById("agentState"),
  topMatch: document.getElementById("topMatch"),
  aiModal: document.getElementById("aiModal"),
  aiForm: document.getElementById("aiForm"),
  aiProvider: document.getElementById("aiProvider"),
  aiBaseUrl: document.getElementById("aiBaseUrl"),
  aiModel: document.getElementById("aiModel"),
  aiApiKey: document.getElementById("aiApiKey"),
  aiStatusText: document.getElementById("aiStatusText"),
  closeAiModal: document.getElementById("closeAiModal"),
  aiCancel: document.getElementById("aiCancel"),
  aiSubmit: document.getElementById("aiSubmit"),
};

async function loadDashboard() {
  if (state.desktop) {
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.data = await response.json();
      state.jobs = state.data.jobs || [];
      renderContext();
      return;
    } catch (error) {
      elements.syncState.innerHTML = `<span class="connection-dot warning" aria-hidden="true"></span>Desktop unavailable`;
      showToast(`Local dashboard unavailable: ${error.message}`);
      return;
    }
  }
  if (window.location.protocol === "file:" && !state.connection.endpoint) {
    state.data = emptyDashboardData();
    state.jobs = [];
    renderContext();
    elements.syncState.innerHTML = `<span class="connection-dot" aria-hidden="true"></span>Local chat mode`;
    return;
  }
  if (!state.connection.endpoint || !state.connection.token) {
    state.data = emptyDashboardData();
    state.jobs = [];
    renderContext();
    elements.syncState.innerHTML = `<span class="connection-dot" aria-hidden="true"></span>Private local mode`;
    return;
  }
  try {
    const response = await fetchDashboard();
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.data = await response.json();
    state.jobs = state.data.jobs || [];
    renderContext();
  } catch (error) {
    elements.syncState.innerHTML = `<span class="connection-dot warning" aria-hidden="true"></span>Data unavailable`;
    renderContext();
    showToast(`Dashboard data unavailable: ${error.message}`);
  }
}

function bootConversation() {
  if (!state.messages.length) {
    addAssistantMessage(welcomeMessage());
  } else {
    renderMessages();
  }
  renderProfile();
}

function welcomeMessage() {
  const firstName = state.profile.name ? `, ${escapeHtml(firstWord(state.profile.name))}` : "";
  return `
    <div class="assistant-intro">
      <span class="assistant-spark" aria-hidden="true">✦</span>
      <div>
        <h2>Hi${firstName}. I’m your ApplyPilot career agent.</h2>
        <p>Tell me what you’ve done and what you want next. I can build your profile, draft a truthful resume, find matching jobs, explain decisions, and prepare safe application runs.</p>
      </div>
    </div>
    <div class="capability-grid">
      <button type="button" data-action="onboard">
        <span>01</span>
        <strong>Understand my background</strong>
        <small>Start with a conversation—no forms required.</small>
      </button>
      <button type="button" data-action="resume">
        <span>02</span>
        <strong>Create my resume</strong>
        <small>Build a draft only from facts you provide.</small>
      </button>
      <button type="button" data-action="jobs">
        <span>03</span>
        <strong>Find my best jobs</strong>
        <small>Review scored matches and why they fit.</small>
      </button>
      <button type="button" data-action="apply">
        <span>04</span>
        <strong>Run my job search</strong>
        <small>Prepare applications with explicit approval.</small>
      </button>
      <button type="button" data-action="ai-setup">
        <span>05</span>
        <strong>Set up AI</strong>
        <small>Use local Ollama, BYOK APIs, or managed preview.</small>
      </button>
    </div>
  `;
}

function handleUserMessage(rawMessage) {
  const message = rawMessage.trim();
  if (!message) return;
  addUserMessage(message);
  elements.chatInput.value = "";
  resizeComposer();

  if (state.onboardingStep) {
    handleOnboardingAnswer(message);
    return;
  }

  const normalized = message.toLowerCase();
  if (/(don'?t|do not|no)\s+have\s+(a\s+)?(resume|cv)/i.test(message)) {
    state.profile.resumeStatus = "none";
    saveProfile();
    startOnboarding();
    return;
  }
  if (/\b(resume|cv)\b/.test(normalized)) {
    showResume();
    return;
  }
  if (/\b(why|explain)\b/.test(normalized)) {
    explainJob(message);
    return;
  }
  if (/\b(job|jobs|match|matches|role|roles|opportunit)/.test(normalized)) {
    showJobs();
    return;
  }
  if (/\b(status|today|result|results|progress|activity)\b/.test(normalized)) {
    showStatus();
    return;
  }
  if (/\b(ai setup|api key|api keys|openai|ollama|local model|groq|gemini|managed ai|byok)\b/.test(normalized)) {
    showAISetup();
    return;
  }
  if (/\b(apply|start|run agent|auto.?apply)\b/.test(normalized)) {
    showApplyConfirmation();
    return;
  }
  if (/\b(profile|about me|what do you know)\b/.test(normalized)) {
    showProfileSummary();
    return;
  }

  if (
    !state.profile.background &&
    /\b(i am|i'm|worked|built|studied|experience|developer|engineer|designer|manager)\b/.test(normalized)
  ) {
    state.profile.background = message;
    saveProfile();
    addAssistantMessage(`
      <p>That gives me a useful first picture of your background. I’ve saved it without adding or changing any claims.</p>
      <p><strong>What kind of role do you want next?</strong></p>
    `);
    state.onboardingStep = "target";
    setComposerPlaceholder(onboardingSteps[0].placeholder);
    return;
  }

  addAssistantMessage(`
    <p>I can work with that. The fastest way to make this useful is to learn your career story, then turn it into concrete outputs.</p>
    <div class="inline-actions">
      <button type="button" data-action="onboard">Tell you about me</button>
      <button type="button" data-action="jobs">Show job matches</button>
      <button type="button" data-action="status">Check activity</button>
    </div>
  `);
}

function startOnboarding() {
  const firstMissing = onboardingSteps.find((step) => !profileValue(step.key));
  const step = firstMissing || onboardingSteps[0];
  state.onboardingStep = step.key;
  addAssistantMessage(`
    <p>No problem—we’ll build the foundation together. I won’t invent employers, dates, qualifications, or achievements.</p>
    <p><strong>${escapeHtml(step.question)}</strong></p>
  `);
  setComposerPlaceholder(step.placeholder);
  elements.chatInput.focus();
}

function handleOnboardingAnswer(message) {
  const stepIndex = onboardingSteps.findIndex((step) => step.key === state.onboardingStep);
  const step = onboardingSteps[stepIndex];
  if (!step) {
    state.onboardingStep = "";
    return;
  }

  const value = message.trim();
  if (step.key === "skills") {
    state.profile.skills = splitSkills(value);
  } else if (step.key === "email") {
    state.profile.emailSkipped = /^skip|later$/i.test(value);
    state.profile.email = state.profile.emailSkipped ? "" : value;
  } else {
    state.profile[step.key] = value;
  }
  saveProfile();

  const nextStep = onboardingSteps.slice(stepIndex + 1).find((item) => !profileValue(item.key));
  if (nextStep) {
    state.onboardingStep = nextStep.key;
    addAssistantMessage(`<p>Got it.</p><p><strong>${escapeHtml(nextStep.question)}</strong></p>`);
    setComposerPlaceholder(nextStep.placeholder);
    return;
  }

  state.onboardingStep = "";
  setComposerPlaceholder("Ask me to build your resume, show matches, or plan your next move…");
  if (state.desktop) {
    queueProfileSave(true).then(loadDashboard);
  }
  addAssistantMessage(`
    <p>I have enough to create your first career profile. You can refine it anytime by talking to me.</p>
    ${profileSummaryCard()}
    <div class="resume-ready-card">
      <span class="resume-icon" aria-hidden="true">▤</span>
      <div>
        <strong>Your first resume draft is ready</strong>
        <p>It uses only the information you provided and clearly leaves missing details for you to complete.</p>
      </div>
      <button type="button" data-action="download-resume">Download draft</button>
    </div>
  `);
}

function showResume() {
  if (profileCompletion() < 45) {
    addAssistantMessage(`
      <p>I can build it, but I need a few honest facts first. A thin truthful draft is better than a polished fictional one.</p>
      <div class="inline-actions">
        <button type="button" data-action="onboard">Build my profile</button>
      </div>
    `);
    return;
  }
  addAssistantMessage(`
    <p>Here’s the resume structure I can produce from your current profile.</p>
    <div class="resume-preview">
      <div class="resume-preview-header">
        <div>
          <span>Resume draft</span>
          <strong>${escapeHtml(state.profile.name || "Candidate name needed")}</strong>
        </div>
        <span>${profileCompletion()}% profile</span>
      </div>
      <pre>${escapeHtml(generateResume())}</pre>
      <div class="inline-actions">
        <button type="button" data-action="download-resume">Download .md</button>
        <button type="button" data-action="copy-resume">Copy resume</button>
        <button type="button" data-action="onboard">Improve profile</button>
      </div>
    </div>
  `);
}

function showJobs() {
  if (!state.jobs.length) {
    addAssistantMessage(`
      <p>I don’t have any scored jobs yet. I can search LinkedIn through your existing logged-in Chrome session and score the results against this profile.</p>
      <div class="inline-actions">
        ${
          state.desktop
            ? `<button type="button" data-action="search-jobs">Search LinkedIn now</button>`
            : `<button type="button" data-action="connect">Connect data</button>
               <button type="button" data-action="open-desktop">Open desktop agent</button>`
        }
      </div>
    `);
    return;
  }

  const jobs = rankedJobs()
    .filter((job) => ["shortlist", "review"].includes(String(job.decision || "").toLowerCase()))
    .slice(0, 5);
  if (!jobs.length) {
    addAssistantMessage(`
      <p>I scored ${formatNumber(state.jobs.length)} jobs, but none currently meet the profile’s review threshold.</p>
      <p>I’ll keep them out of your recommended list. You can improve the profile, change preferences, or run a new profile-aligned search.</p>
      <div class="inline-actions">
        <button type="button" data-action="onboard">Improve my profile</button>
        ${state.desktop ? `<button type="button" data-action="search-jobs">Search again</button>` : ""}
      </div>
    `);
    return;
  }
  addAssistantMessage(`
    <p>I scored <strong>${formatNumber(state.jobs.length)} jobs</strong> and found <strong>${formatNumber(jobs.length)} worth reviewing</strong>${state.profile.target ? ` for ${escapeHtml(state.profile.target)}` : ""}.</p>
    <div class="job-card-list">
      ${jobs.map(jobCard).join("")}
    </div>
    <div class="inline-actions">
      <button type="button" data-action="apply">Prepare an application run</button>
      <button type="button" data-action="resume">Tailor my foundation</button>
      ${state.desktop ? `<button type="button" data-action="score-jobs">Rescore with my profile</button>` : ""}
    </div>
  `);
}

function explainJob(message) {
  if (!state.jobs.length) {
    showJobs();
    return;
  }
  const normalized = message.toLowerCase();
  const job =
    rankedJobs().find((item) => normalized.includes(String(item.company || "").toLowerCase())) ||
    rankedJobs().find((item) => titleWords(item.title).some((word) => normalized.includes(word))) ||
    rankedJobs()[0];
  addAssistantMessage(`
    <div class="explanation-card">
      <div class="job-score">${number(job.score)}</div>
      <div>
        <span>${escapeHtml(job.company || "Unknown company")}</span>
        <h3>${escapeHtml(cleanTitle(job.title))}</h3>
        <p>${escapeHtml(job.reason || "This job was scored using your configured profile and job preferences.")}</p>
        <dl>
          <div><dt>Decision</dt><dd>${escapeHtml(formatLabel(job.decision || "unscored"))}</dd></div>
          <div><dt>Source</dt><dd>${escapeHtml(formatLabel(job.source || "manual"))}</dd></div>
          <div><dt>Easy Apply</dt><dd>${job.easy_apply ? "Yes" : "No"}</dd></div>
        </dl>
      </div>
    </div>
  `);
}

function showStatus() {
  const data = state.data || {};
  const summary = data.summary || {};
  const policy = data.policy || {};
  const profileApplied =
    summary.profile_applied_total ??
    number(summary.native_linkedin_applied) + number(summary.native_naukri_applied);
  const importedHistory =
    summary.imported_history_total ??
    number(summary.legacy_linkedin_applied) + number(summary.legacy_naukri_applied);
  const latestProfileRun = (data.runs || []).find((run) => run.origin === "native");
  const desktop = data.desktop || {};
  const recentLogs = (desktop.logs || []).slice(-8);
  const searchPlan = data.search_plan || [];
  addAssistantMessage(`
    <p>Here’s the current job-search picture.</p>
    <div class="status-summary-grid">
      <div><strong>${formatNumber(profileApplied)}</strong><span>This profile applied</span></div>
      <div><strong>${formatNumber(summary.shortlisted)}</strong><span>Current strong matches</span></div>
      <div><strong>${formatNumber(summary.applied_today)}</strong><span>Applied today</span></div>
      <div><strong>${formatNumber(policy.max_applications_per_day)}</strong><span>Maximum per day</span></div>
    </div>
    ${
      importedHistory
        ? `<div class="history-notice"><strong>${formatNumber(importedHistory)} imported historical applications</strong><span>These came from the old agent (${formatNumber(summary.legacy_linkedin_applied)} LinkedIn + ${formatNumber(summary.legacy_naukri_applied)} Naukri) and are not results from this candidate profile.</span></div>`
        : ""
    }
    ${
      latestProfileRun
        ? `<p class="muted-copy">Latest profile run: ${escapeHtml(formatLabel(latestProfileRun.source || "agent"))} · ${formatNumber(latestProfileRun.applied)} applied · ${formatNumber(latestProfileRun.skipped)} skipped · ${escapeHtml(formatTimestamp(latestProfileRun.completed_at))}</p>`
        : `<p class="muted-copy">This profile has no completed application runs yet.</p>`
    }
    ${
      state.desktop
        ? `<div class="desktop-activity-card">
             <div><span>Local agent</span><strong>${desktop.running ? `Running ${escapeHtml(formatLabel(desktop.mode || "agent"))}` : "Idle"}</strong></div>
             ${
               searchPlan.length
                 ? `<div class="search-plan-card">
                      <span>Next search plan</span>
                      ${searchPlan
                        .map(
                          (item) =>
                            `<strong>${escapeHtml(item.keyword)}${item.remote_only ? " · Remote" : item.location ? ` · ${escapeHtml(item.location)}` : ""}</strong>`,
                        )
                        .join("")}
                    </div>`
                 : ""
             }
             ${recentLogs.length ? `<pre>${escapeHtml(recentLogs.join("\n"))}</pre>` : ""}
             <div class="inline-actions">
               ${desktop.running ? `<button type="button" data-action="stop-run">Stop agent</button>` : ""}
               <button type="button" data-action="search-jobs">Search for jobs</button>
             </div>
           </div>`
        : ""
    }
  `);
}

async function showAISetup() {
  if (!state.desktop) {
    addAssistantMessage(`
      <p>AI setup happens on the customer's own desktop, not on this public website. That keeps API keys and local model settings off ApplyPilot's server.</p>
      <div class="ai-choice-grid">
        <article>
          <strong>Local model</strong>
          <p>Install Ollama, run <code>ollama pull llama3.1</code>, then choose Ollama inside the desktop app.</p>
        </article>
        <article>
          <strong>Bring your own API key</strong>
          <p>Use OpenAI-compatible, Groq, or Gemini. Keys are saved locally in the desktop workspace only.</p>
        </article>
        <article>
          <strong>ApplyPilot managed</strong>
          <p>No customer key. In this MVP it is a managed preview path until hosted model routing is enabled.</p>
        </article>
      </div>
      <div class="inline-actions">
        <button type="button" data-action="open-desktop">Open desktop app</button>
        <a class="inline-link" href="./checkout.html?plan=pro_byok&provider=razorpay">Choose BYOK plan</a>
        <a class="inline-link" href="./checkout.html?plan=pro_managed&provider=razorpay">Choose Managed plan</a>
      </div>
    `);
    return;
  }
  await loadProviderStatus();
  openAiModal();
}

function showApplyConfirmation() {
  const policy = state.data?.policy || {};
  const summary = state.data?.summary || {};
  const eligibleJobs = rankedJobs().filter(
    (job) =>
      number(job.score) >= number(policy.min_score_to_submit || 70) &&
      (!policy.require_easy_apply || job.easy_apply),
  );
  const autoSubmitEnabled = policy.mode === "auto-submit";
  addAssistantMessage(`
    <p>${autoSubmitEnabled ? "I can prepare the local agent, but submitting applications changes your external accounts, so this confirmation is required." : "Your safety policy currently stops before submission. Enable auto-submit first, then I’ll ask once more before starting the run."}</p>
    <div class="confirmation-card">
      <div class="confirmation-title">
        <span aria-hidden="true">!</span>
        <div>
          <strong>Application run</strong>
          <small>LinkedIn + Naukri</small>
        </div>
      </div>
      <dl>
        <div><dt>Eligible now</dt><dd>${formatNumber(eligibleJobs.length)} jobs</dd></div>
        <div><dt>Minimum score</dt><dd>${formatNumber(policy.min_score_to_submit || 70)}</dd></div>
        <div><dt>Today</dt><dd>${formatNumber(summary.applied_today)}/${formatNumber(policy.max_applications_per_day || 0)}</dd></div>
        <div><dt>Mode</dt><dd>${escapeHtml(formatLabel(policy.mode || "review-only"))}</dd></div>
      </dl>
      <div class="confirmation-warning">${autoSubmitEnabled ? "This run can submit applications through your logged-in browser session." : "Enabling auto-submit changes future application runs until you switch back to review-only."}</div>
      <button class="confirm-action-button" type="button" data-action="${
        state.desktop
          ? autoSubmitEnabled
            ? "confirm-run"
            : "enable-auto-submit"
          : "open-desktop"
      }">${
        state.desktop
          ? autoSubmitEnabled
            ? "Confirm and start local agent"
            : "Enable auto-submit"
          : "Open desktop to review"
      }</button>
    </div>
  `);
}

function showProfileSummary() {
  if (profileCompletion() === 0) {
    startOnboarding();
    return;
  }
  addAssistantMessage(`
    <p>This is what I currently understand. I keep uncertain or missing information visible instead of filling gaps with guesses.</p>
    ${profileSummaryCard()}
    <div class="inline-actions">
      <button type="button" data-action="onboard">Update profile</button>
      <button type="button" data-action="resume">Build resume</button>
    </div>
  `);
}

function profileSummaryCard() {
  return `
    <div class="profile-summary-card">
      <div><span>Name</span><strong>${escapeHtml(state.profile.name || "Not provided")}</strong></div>
      <div><span>Target</span><strong>${escapeHtml(state.profile.target || "Not provided")}</strong></div>
      <div><span>Location</span><strong>${escapeHtml(state.profile.location || "Not provided")}</strong></div>
      <div class="wide"><span>Skills</span><strong>${escapeHtml((state.profile.skills || []).join(", ") || "Not provided")}</strong></div>
      <div class="wide"><span>Background</span><p>${escapeHtml(state.profile.background || "Not provided")}</p></div>
    </div>
  `;
}

function jobCard(job, index) {
  return `
    <article class="chat-job-card">
      <div class="job-rank">${String(index + 1).padStart(2, "0")}</div>
      <div class="job-card-copy">
        <span>${escapeHtml(job.company || "Unknown company")} · ${escapeHtml(job.location || formatLabel(job.source || "Job source"))}</span>
        <h3>${escapeHtml(cleanTitle(job.title))}</h3>
        <p>${escapeHtml(job.reason || "Scored against the current candidate profile.")}</p>
      </div>
      <div class="job-score">${number(job.score)}</div>
    </article>
  `;
}

function renderContext() {
  const data = state.data || {};
  const summary = data.summary || {};
  const policy = data.policy || {};
  const saas = data.saas || {};
  const topJob = rankedJobs()[0];

  elements.syncState.innerHTML = `<span class="connection-dot" aria-hidden="true"></span>${formatTimestamp(data.generated_at)}`;
  const desktopConnected = Boolean(data.desktop?.connected);
  elements.accountPlan.textContent =
    state.desktop && !desktopConnected ? "Not activated" : formatLabel(saas.plan || data.desktop?.customer?.plan || "Founder Preview");
  elements.accountMode.textContent =
    state.desktop && !desktopConnected
      ? "Profile and resume available"
      : saas.ai_mode
        ? formatLabel(saas.ai_mode)
        : "Local-first agent";
  elements.todayApplied.textContent = formatNumber(summary.applied_today);
  elements.shortlistCount.textContent = formatNumber(summary.shortlisted);
  elements.dailyLimit.textContent = formatNumber(policy.max_applications_per_day);
  elements.policyMode.textContent = formatLabel(policy.mode || "review-only");
  elements.agentState.textContent = policy.can_auto_submit ? "Armed" : "Review";
  if (data.desktop?.running) {
    elements.agentState.textContent = `Running ${formatLabel(data.desktop.mode || "agent")}`;
  }
  elements.sidebarJobCount.textContent = formatNumber(summary.jobs || state.jobs.length);
  renderProviderBadge(data.desktop?.provider || state.providerStatus);

  if (topJob) {
    elements.topMatch.innerHTML = `
      <div class="top-match-score">${number(topJob.score)}</div>
      <h2>${escapeHtml(cleanTitle(topJob.title))}</h2>
      <p>${escapeHtml(topJob.company || "Unknown company")}</p>
      <button type="button" data-prompt="Why is ${escapeAttr(topJob.company || cleanTitle(topJob.title))} a match?">Why this match?</button>
    `;
  } else {
    elements.topMatch.innerHTML = `
      <h2>No jobs synced yet</h2>
      <p>Connect ApplyPilot or import jobs to see recommendations.</p>
    `;
  }
}

function renderProviderBadge(status) {
  if (!elements.sidebarProvider) return;
  const selected = status?.selected || "rules";
  const provider = (status?.providers || []).find((item) => item.name === selected);
  elements.sidebarProvider.textContent = provider ? provider.label.split(" ")[0] : formatLabel(selected);
}

function renderProfile() {
  const completion = profileCompletion();
  elements.profileName.textContent = state.profile.name || "Getting to know you";
  elements.profileProgress.style.width = `${completion}%`;
  elements.profilePercent.textContent = `${completion}%`;
  elements.sidebarProfilePercent.textContent = `${completion}%`;
  elements.profileTarget.textContent = state.profile.target || "Not set";
  elements.profileBackground.textContent = state.profile.background
    ? truncate(state.profile.background, 72)
    : "Tell me what you do";
  elements.profileLocation.textContent = state.profile.location || "Not set";
}

function addUserMessage(content) {
  state.messages.push({ role: "user", content: escapeHtml(content), createdAt: Date.now() });
  persistMessages();
  renderMessages();
}

function addAssistantMessage(content) {
  state.messages.push({ role: "assistant", content, createdAt: Date.now() });
  persistMessages();
  renderMessages();
}

function renderMessages() {
  elements.chatFeed.innerHTML = state.messages
    .map(
      (message) => `
        <article class="chat-message ${message.role}">
          ${
            message.role === "assistant"
              ? `<div class="message-avatar" aria-hidden="true">AP</div>`
              : `<div class="message-avatar user-avatar" aria-hidden="true">${escapeHtml(firstWord(state.profile.name || "You").charAt(0).toUpperCase())}</div>`
          }
          <div class="message-body">${message.role === "assistant" ? message.content : `<p>${message.content}</p>`}</div>
        </article>
      `,
    )
    .join("");
  window.requestAnimationFrame(() => {
    elements.chatFeed.scrollTop = elements.chatFeed.scrollHeight;
  });
}

function generateResume() {
  const profile = state.profile;
  const contact = [profile.email, profile.location].filter(Boolean).join(" · ");
  const skills = (profile.skills || []).join(" · ") || "[Add your skills]";
  const backgroundLines = sentenceList(profile.background || "");
  const summary = profile.background
    ? `Candidate targeting ${profile.target || "new opportunities"}, with experience described below.`
    : `[Add a short professional summary for ${profile.target || "your target role"}]`;

  return [
    `# ${profile.name || "[Your Name]"}`,
    contact || "[Email] · [Location]",
    "",
    "## Target Role",
    profile.target || "[Add target role]",
    "",
    "## Professional Summary",
    summary,
    "",
    "## Skills",
    skills,
    "",
    "## Experience, Projects & Education",
    ...(backgroundLines.length
      ? backgroundLines.map((line) => `- ${line}`)
      : ["- [Add relevant work, projects, education, and measurable outcomes]"]),
    "",
    "## Preferences",
    `- Preferred location/work style: ${profile.location || "[Add preference]"}`,
    "",
    "---",
    "Draft generated by ApplyPilot from candidate-provided information only. Verify and add dates, employers, qualifications, and measurable outcomes before applying.",
  ].join("\n");
}

async function downloadResume() {
  if (state.desktop) {
    const response = await fetch("/api/resume", { cache: "no-store" });
    if (!response.ok) {
      showToast(`Resume download failed: HTTP ${response.status}`);
      return;
    }
    const blob = await response.blob();
    downloadBlob(blob, "applypilot-resume-draft.md");
    showToast("Resume draft downloaded");
    return;
  }
  const blob = new Blob([generateResume()], { type: "text/markdown;charset=utf-8" });
  downloadBlob(blob, `${slugify(state.profile.name || "candidate")}-resume-draft.md`);
  showToast("Resume draft downloaded");
}

function downloadBlob(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  URL.revokeObjectURL(link.href);
  link.remove();
}

async function copyResume() {
  await navigator.clipboard.writeText(generateResume());
  showToast("Resume copied");
}

function rankedJobs() {
  const roleWords = titleWords(state.profile.target || "");
  return [...state.jobs].sort((a, b) => {
    const aBoost = roleWords.filter((word) => `${a.title} ${a.company}`.toLowerCase().includes(word)).length * 4;
    const bBoost = roleWords.filter((word) => `${b.title} ${b.company}`.toLowerCase().includes(word)).length * 4;
    return number(b.score) + bBoost - (number(a.score) + aBoost);
  });
}

function handleAction(action) {
  if (action === "onboard" || action === "profile") startOnboarding();
  if (action === "resume") showResume();
  if (action === "jobs") showJobs();
  if (action === "status") showStatus();
  if (action === "ai-setup") showAISetup();
  if (action === "apply") showApplyConfirmation();
  if (action === "download-resume") downloadResume();
  if (action === "copy-resume") copyResume();
  if (action === "connect") openConnectModal();
  if (action === "score-jobs") scoreJobs();
  if (action === "search-jobs") startDesktopSearch();
  if (action === "enable-auto-submit") enableAutoSubmit();
  if (action === "confirm-run") startDesktopRun();
  if (action === "stop-run") stopDesktopRun();
  if (action === "open-desktop") {
    window.open("http://127.0.0.1:8765", "_blank", "noopener");
    showToast("Opening the local desktop agent");
  }
}

function defaultProfile() {
  return {
    name: "",
    email: "",
    target: "",
    background: "",
    skills: [],
    location: "",
    resumeStatus: "",
    emailSkipped: false,
  };
}

function loadProfile() {
  try {
    return { ...defaultProfile(), ...JSON.parse(safeStorageGet("local", PROFILE_KEY) || "{}") };
  } catch {
    return defaultProfile();
  }
}

function saveProfile() {
  safeStorageSet("local", PROFILE_KEY, JSON.stringify(state.profile));
  renderProfile();
  if (state.desktop) queueProfileSave(false);
}

function resetCandidateProfile(options = {}) {
  const { confirmReset = true, showMessage = true } = options;
  if (
    confirmReset &&
    (profileCompletion() > 0 || state.messages.length > 1 || state.connection.endpoint || state.connection.token) &&
    !window.confirm("Start a fresh candidate profile in this browser? This clears the saved profile, chat, and SaaS connection for this browser.")
  ) {
    return;
  }

  resetLocalCareerStorage();
  state.profile = defaultProfile();
  state.messages = [];
  state.onboardingStep = "";
  state.connection = { endpoint: "", token: "" };
  state.data = emptyDashboardData();
  state.jobs = [];
  setComposerPlaceholder("Tell me what kind of work you want, or what you’ve done so far…");
  renderProfile();
  renderContext();
  addAssistantMessage(welcomeMessage());
  if (state.desktop) {
    queueProfileSave(false).then(loadDashboard).catch(() => undefined);
  }
  if (showMessage) {
    showToast("Started a fresh person profile");
  }
}

function queueProfileSave(rescore) {
  const profile = { ...state.profile, skills: [...(state.profile.skills || [])] };
  state.profileSave = state.profileSave
    .catch(() => undefined)
    .then(async () => {
      const response = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ profile, rescore }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      return data;
    })
    .catch((error) => {
      showToast(`Could not save local profile: ${error.message}`);
      throw error;
    });
  return state.profileSave;
}

async function loadDesktopProfile() {
  if (!state.desktop) return;
  try {
    const response = await fetch("/api/profile", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const profile = await response.json();
    state.profile = {
      ...defaultProfile(),
      ...profile,
      resumeStatus: profile.resume_status || profile.resumeStatus || "",
    };
    safeStorageSet("local", PROFILE_KEY, JSON.stringify(state.profile));
  } catch (error) {
    showToast(`Could not load local profile: ${error.message}`);
  }
}

async function scoreJobs() {
  if (!state.desktop) return;
  const response = await fetch("/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ provider: state.providerStatus?.selected || "" }),
  });
  const data = await response.json();
  if (!response.ok) {
    showToast(data.detail || `HTTP ${response.status}`);
    return;
  }
  showToast(data.scored ? `Rescored ${data.scored} jobs` : "No jobs are queued yet");
  await loadDashboard();
}

async function loadProviderStatus() {
  if (!state.desktop) {
    state.providerStatus = {
      selected: "rules",
      providers: [
        { name: "rules", label: "Rules", configured: true },
        { name: "ollama", label: "Ollama local model", configured: false },
        { name: "openai", label: "OpenAI-compatible API", configured: false },
        { name: "groq", label: "Groq API", configured: false },
        { name: "gemini", label: "Gemini API", configured: false },
        { name: "managed_preview", label: "ApplyPilot managed preview", configured: true },
      ],
    };
    return state.providerStatus;
  }
  const response = await fetch("/api/provider/status", { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  state.providerStatus = data;
  renderProviderBadge(data);
  return data;
}

function openAiModal() {
  const status = state.providerStatus || {};
  elements.aiProvider.value = status.selected || "rules";
  applyAiProviderDefaults();
  renderAiStatus(status);
  elements.aiApiKey.value = "";
  elements.aiModal.hidden = false;
  elements.aiProvider.focus();
}

function closeAiModal() {
  elements.aiModal.hidden = true;
}

function applyAiProviderDefaults() {
  const provider = elements.aiProvider.value;
  const status = state.providerStatus || {};
  const row = (status.providers || []).find((item) => item.name === provider) || {};
  elements.aiModel.value = row.model || defaultModelForProvider(provider);
  elements.aiBaseUrl.value = row.base_url || defaultBaseUrlForProvider(provider);
  document.querySelectorAll(".ai-config-field").forEach((field) => {
    const name = field.dataset.aiField;
    const show =
      (name === "base_url" && ["ollama", "openai"].includes(provider)) ||
      (name === "model" && ["ollama", "openai", "groq", "gemini"].includes(provider)) ||
      (name === "api_key" && ["openai", "groq", "gemini"].includes(provider));
    field.hidden = !show;
  });
  renderAiStatus(status);
}

function renderAiStatus(status) {
  const selected = elements.aiProvider.value || status.selected || "rules";
  const row = (status.providers || []).find((item) => item.name === selected);
  if (!row) {
    elements.aiStatusText.textContent = "Choose a provider. Settings are saved on this machine only.";
    return;
  }
  const configured = row.configured ? "Configured" : "Needs setup";
  const reachable = row.reachable === undefined ? "" : row.reachable ? " · Ollama reachable" : " · Ollama not reachable";
  const model = row.model ? ` · ${row.model}` : "";
  elements.aiStatusText.textContent = `${configured}${model}${reachable}. ${row.description || ""}`;
}

async function saveAiProviderConfig() {
  if (!state.desktop) return;
  elements.aiSubmit.disabled = true;
  elements.aiSubmit.textContent = "Saving…";
  try {
    const response = await fetch("/api/provider/config", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        provider: elements.aiProvider.value,
        base_url: elements.aiBaseUrl.value,
        model: elements.aiModel.value,
        api_key: elements.aiApiKey.value,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    state.providerStatus = data;
    renderProviderBadge(data);
    closeAiModal();
    showToast("AI setup saved locally");
    addAssistantMessage(`
      <p><strong>AI setup saved.</strong> ApplyPilot will use ${escapeHtml(formatLabel(data.selected))} for local scoring. API keys stay on this machine.</p>
      <div class="inline-actions">
        <button type="button" data-action="score-jobs">Score jobs with this setup</button>
        <button type="button" data-action="jobs">Show matches</button>
      </div>
    `);
  } catch (error) {
    showToast(error.message);
  } finally {
    elements.aiSubmit.disabled = false;
    elements.aiSubmit.textContent = "Save local AI setup";
  }
}

function defaultModelForProvider(provider) {
  return {
    ollama: "llama3.1",
    openai: "gpt-4o-mini",
    groq: "llama-3.1-8b-instant",
    gemini: "gemini-1.5-flash",
  }[provider] || "";
}

function defaultBaseUrlForProvider(provider) {
  return {
    ollama: "http://localhost:11434",
    openai: "https://api.openai.com",
  }[provider] || "";
}

async function startDesktopRun() {
  if (!requireDesktopActivation()) return;
  const response = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ mode: "apply", confirmed: true }),
  });
  const data = await response.json();
  if (!response.ok) {
    showToast(data.detail || `HTTP ${response.status}`);
    return;
  }
  addAssistantMessage(`
    <p><strong>The local agent has started.</strong> It will use the profile saved in your ApplyPilot workspace and sync results when the run finishes.</p>
    <div class="inline-actions">
      <button type="button" data-action="status">Show live status</button>
    </div>
  `);
  await loadDashboard();
}

async function startDesktopSearch() {
  if (!requireDesktopActivation()) return;
  const planResponse = await fetch("/api/search-plan", { cache: "no-store" });
  const planData = await planResponse.json();
  if (!planResponse.ok || !(planData.queries || []).length) {
    showToast(planData.detail || "Complete your target role before searching");
    return;
  }
  const response = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ mode: "search", confirmed: false }),
  });
  const data = await response.json();
  if (!response.ok) {
    showToast(data.detail || `HTTP ${response.status}`);
    return;
  }
  addAssistantMessage(`
    <p><strong>LinkedIn search started.</strong> Keep your normal Chrome window open and logged in. I’ll store and score the jobs locally as they arrive.</p>
    <div class="search-plan-card">
      <span>Profile-derived searches</span>
      ${(planData.queries || [])
        .map(
          (item) =>
            `<strong>${escapeHtml(item.keyword)}${item.remote_only ? " · Remote" : item.location ? ` · ${escapeHtml(item.location)}` : ""}</strong>`,
        )
        .join("")}
    </div>
    <div class="inline-actions">
      <button type="button" data-action="status">Show live status</button>
      <button type="button" data-action="stop-run">Stop search</button>
    </div>
  `);
  await loadDashboard();
}

async function enableAutoSubmit() {
  if (!requireDesktopActivation()) return;
  const current = state.data?.policy || {};
  const response = await fetch("/api/policy", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      mode: "auto-submit",
      daily_limit: number(current.max_applications_per_day) || 10,
      min_score: number(current.min_score_to_submit) || 70,
      require_easy_apply: current.require_easy_apply !== false,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    showToast(data.detail || `HTTP ${response.status}`);
    return;
  }
  await loadDashboard();
  addAssistantMessage(`
    <p><strong>Auto-submit is enabled.</strong> Daily limit: ${formatNumber(data.max_applications_per_day)}. Minimum score: ${formatNumber(data.min_score_to_submit)}. Easy Apply required: ${data.require_easy_apply ? "yes" : "no"}.</p>
    <p>Please confirm the actual application run separately.</p>
  `);
  showApplyConfirmation();
}

async function stopDesktopRun() {
  const response = await fetch("/api/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: "{}",
  });
  const data = await response.json();
  if (!response.ok) {
    showToast(data.detail || `HTTP ${response.status}`);
    return;
  }
  showToast(data.status === "idle" ? "Agent is already idle" : "Stop requested");
  await loadDashboard();
}

function loadMessages() {
  try {
    const messages = JSON.parse(safeStorageGet("session", MESSAGE_KEY) || "[]");
    return Array.isArray(messages) ? messages : [];
  } catch {
    return [];
  }
}

function persistMessages() {
  safeStorageSet("session", MESSAGE_KEY, JSON.stringify(state.messages.slice(-40)));
}

function safeStorageGet(kind, key) {
  try {
    const storage = kind === "session" ? window.sessionStorage : window.localStorage;
    return storage.getItem(key);
  } catch {
    return "";
  }
}

function safeStorageSet(kind, key, value) {
  try {
    const storage = kind === "session" ? window.sessionStorage : window.localStorage;
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function profileCompletion() {
  const weights = { target: 20, background: 25, skills: 20, location: 10, name: 15, email: 10 };
  return Object.entries(weights).reduce((total, [key, weight]) => {
    if (key === "email") return total + (state.profile.email ? weight : 0);
    return total + (profileValue(key) ? weight : 0);
  }, 0);
}

function profileValue(key) {
  if (key === "skills") return (state.profile.skills || []).length > 0;
  if (key === "email") return state.profile.emailSkipped || Boolean(String(state.profile.email || "").trim());
  return Boolean(String(state.profile[key] || "").trim());
}

function splitSkills(value) {
  return value
    .split(/,|\n|·|\band\b/gi)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 30);
}

function sentenceList(value) {
  return value
    .split(/\n+|(?<=[.!?])\s+/)
    .map((item) => item.replace(/^[-•]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 10);
}

function titleWords(value) {
  const stopWords = new Set(["the", "and", "for", "with", "from", "role", "jobs", "job", "engineer", "developer"]);
  return (
    String(value || "")
      .toLowerCase()
      .match(/[a-z0-9+#.]{3,}/g)
      ?.filter((word) => !stopWords.has(word)) || []
  );
}

function cleanTitle(value) {
  const title = String(value || "Untitled role")
    .replace(/\s+with verification$/i, "")
    .trim();
  const middle = Math.floor(title.length / 2);
  for (let offset = -2; offset <= 2; offset += 1) {
    const splitAt = middle + offset;
    const left = title.slice(0, splitAt).trim();
    const right = title.slice(splitAt).trim();
    if (left && left === right) return left;
  }
  return title;
}

function fetchDashboard() {
  if (state.connection.endpoint && state.connection.token) {
    return fetch(`${state.connection.endpoint.replace(/\/$/, "")}/api/v1/dashboard`, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${state.connection.token}`,
      },
    });
  }
  throw new Error("Connect a license or device token to load SaaS dashboard data.");
}

async function initializeApplication() {
  await loadDesktopProfile();
  if (state.desktop) {
    await loadProviderStatus().catch((error) => showToast(`Provider status unavailable: ${error.message}`));
  }
  bootConversation();
  await loadDashboard();
  if (state.desktop) {
    window.setInterval(loadDashboard, 15000);
  }
}

function loadConnection() {
  return {
    endpoint: safeStorageGet("local", "applypilot.api.endpoint") || "",
    token: safeStorageGet("local", "applypilot.api.token") || "",
  };
}

function resetLocalCareerStorage() {
  safeStorageRemove("local", PROFILE_KEY);
  safeStorageRemove("session", MESSAGE_KEY);
  safeStorageRemove("local", "applypilot.api.endpoint");
  safeStorageRemove("local", "applypilot.api.token");
}

function removeStartupResetQuery() {
  const cleanQuery = new URLSearchParams(window.location.search);
  cleanQuery.delete("fresh");
  cleanQuery.delete("reset");
  const query = cleanQuery.toString();
  const cleanUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState({}, document.title, cleanUrl);
}

function emptyDashboardData() {
  return {
    generated_at: "",
    policy: {
      mode: "review-only",
      max_applications_per_day: 0,
      min_score_to_submit: 70,
      require_easy_apply: true,
      require_explicit_opt_in: true,
      can_auto_submit: false,
      should_stop_before_submit: true,
    },
    summary: {
      jobs: 0,
      evaluations: 0,
      shortlisted: 0,
      easy_apply_jobs: 0,
      application_records: 0,
      completed_jobs: 0,
      applied_today: 0,
      native_linkedin_applied: 0,
      native_naukri_applied: 0,
      legacy_linkedin_applied: 0,
      legacy_naukri_applied: 0,
      imported_history_total: 0,
      profile_applied_total: 0,
      leads: 0,
      lead_emails: 0,
    },
    sources: [],
    runs: [],
    series: [],
    jobs: [],
    saas: {
      plan: "free_cli",
      ai_mode: "byok_local",
    },
    desktop: {
      connected: false,
      running: false,
      logs: [],
    },
  };
}

function saveConnection(endpoint, token) {
  state.connection = { endpoint: endpoint.trim(), token: token.trim() };
  if (state.connection.endpoint && state.connection.token) {
    safeStorageSet("local", "applypilot.api.endpoint", state.connection.endpoint);
    safeStorageSet("local", "applypilot.api.token", state.connection.token);
  } else {
    safeStorageRemove("local", "applypilot.api.endpoint");
    safeStorageRemove("local", "applypilot.api.token");
  }
}

function safeStorageRemove(kind, key) {
  try {
    const storage = kind === "session" ? window.sessionStorage : window.localStorage;
    storage.removeItem(key);
  } catch {
    // Direct file mode can disable browser storage. The chat still works in memory.
  }
}

function openConnectModal() {
  elements.apiEndpoint.value = state.connection.endpoint || "http://127.0.0.1:8787";
  elements.apiToken.value = state.connection.token || "";
  elements.connectTitle.textContent = state.desktop ? "Activate this desktop" : "Connect ApplyPilot data";
  elements.connectTokenLabel.textContent = state.desktop ? "License key" : "License or device token";
  elements.connectSubmit.textContent = state.desktop ? "Activate" : "Connect";
  elements.clearConnection.textContent = state.desktop ? "Cancel" : "Use private local mode";
  elements.connectModal.hidden = false;
  elements.apiEndpoint.focus();
}

function closeConnectModal() {
  elements.connectModal.hidden = true;
}

function setComposerPlaceholder(value) {
  elements.chatInput.placeholder = value;
}

function resizeComposer() {
  elements.chatInput.style.height = "auto";
  elements.chatInput.style.height = `${Math.min(elements.chatInput.scrollHeight, 170)}px`;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("show"), 2400);
}

function formatTimestamp(value) {
  if (!value) return "Not synced";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(number(value));
}

function number(value) {
  return Number(value || 0);
}

function firstWord(value) {
  return String(value || "").trim().split(/\s+/)[0] || "";
}

function truncate(value, length) {
  const text = String(value || "");
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function slugify(value) {
  return String(value || "candidate")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  handleUserMessage(elements.chatInput.value);
});

elements.chatInput.addEventListener("input", resizeComposer);
elements.chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});

document.addEventListener("click", (event) => {
  const actionTarget = event.target.closest("[data-action]");
  if (actionTarget) {
    handleAction(actionTarget.dataset.action);
    return;
  }
  const promptTarget = event.target.closest("[data-prompt]");
  if (promptTarget) {
    handleUserMessage(promptTarget.dataset.prompt || "");
  }
});

elements.newConversation.addEventListener("click", () => {
  resetCandidateProfile();
});

elements.refreshButton.addEventListener("click", loadDashboard);
elements.connectButton.addEventListener("click", openConnectModal);
elements.closeConnect.addEventListener("click", closeConnectModal);
elements.connectModal.addEventListener("click", (event) => {
  if (event.target === elements.connectModal) closeConnectModal();
});
elements.connectForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.desktop) {
    activateDesktop();
    return;
  }
  saveConnection(elements.apiEndpoint.value, elements.apiToken.value);
  closeConnectModal();
  loadDashboard();
  showToast("ApplyPilot data connected");
});
elements.clearConnection.addEventListener("click", () => {
  if (state.desktop) {
    closeConnectModal();
    return;
  }
  saveConnection("", "");
  closeConnectModal();
  loadDashboard();
  showToast("Using private local mode");
});
elements.closeAiModal.addEventListener("click", closeAiModal);
elements.aiCancel.addEventListener("click", closeAiModal);
elements.aiModal.addEventListener("click", (event) => {
  if (event.target === elements.aiModal) closeAiModal();
});
elements.aiProvider.addEventListener("change", applyAiProviderDefaults);
elements.aiForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveAiProviderConfig();
});

function requireDesktopActivation() {
  if (!state.desktop || state.data?.desktop?.connected) return true;
  addAssistantMessage(`
    <div class="activation-card">
      <span aria-hidden="true">◇</span>
      <div>
        <strong>Activate ApplyPilot to continue</strong>
        <p>Your profile and resume are ready. Job search and application automation require an active desktop license.</p>
      </div>
      <button type="button" data-action="connect">Enter license key</button>
      <a href="./checkout.html">Choose a plan</a>
    </div>
  `);
  return false;
}

async function activateDesktop() {
  elements.connectSubmit.disabled = true;
  elements.connectSubmit.textContent = "Activating…";
  try {
    const response = await fetch("/api/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        endpoint: elements.apiEndpoint.value,
        license_key: elements.apiToken.value,
        device_id: navigator.userAgent,
        device_name: "ApplyPilot Desktop",
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    elements.apiToken.value = "";
    closeConnectModal();
    await loadDashboard();
    addAssistantMessage(`
      <p><strong>Desktop activated.</strong> Your ${escapeHtml(formatLabel(data.customer?.plan || "ApplyPilot"))} plan is ready.</p>
      <div class="inline-actions">
        <button type="button" data-action="search-jobs">Search for jobs</button>
      </div>
    `);
  } catch (error) {
    showToast(error.message);
  } finally {
    elements.connectSubmit.disabled = false;
    elements.connectSubmit.textContent = "Activate";
  }
}

initializeApplication();
