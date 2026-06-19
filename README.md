# ApplyPilot

Local-first AI job search copilot.

Live landing page: https://rishal6.github.io/applypilot/

ApplyPilot is the product-grade rewrite of the working LinkedIn agent. The core idea is simple: keep risky browser/session work on the user's machine, put paid product value in the SaaS layer, and expose the same agent through CLI, desktop, MCP, and ChatGPT/Codex distribution.

## Product Positioning

ApplyPilot is not a spam auto-apply bot. It is a job-hunt operating system:

- import jobs from local connectors
- score fit against a user's resume and preferences
- build a review queue
- draft application answers and outreach
- track applications and outcomes
- run local browser automation, including auto-submit, when explicitly enabled

## Why Local-First

Users should not give a random SaaS their LinkedIn password. The local agent keeps cookies, browser sessions, resumes, and API keys on the user's device. The SaaS handles subscription, sync, analytics, premium prompts, and product UX.

## Current MVP

This first slice is intentionally useful without touching LinkedIn:

- imports job JSON from the existing working agent
- normalizes jobs into a queue
- scores jobs with a safe local rules provider
- prints a review queue
- exports a markdown report
- exports SaaS dashboard data for the web control plane

## Quick Start

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
applypilot init
applypilot import-linkedin --source /Users/rishal/Desktop/bed_rock/linkedin-agent/output/linkedin_jobs.json
applypilot score
applypilot review --limit 20
applypilot report
```

No API key is required for the default `rules` provider.

## Working Agent Replica Mode

ApplyPilot includes a native copy of the current production-grade local agent. This is the fastest path to making the SaaS product match the tool already working on this desktop while keeping logs and outputs inside the ApplyPilot workspace.

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
PYTHONPATH=src python3 -m applypilot --workspace . status
PYTHONPATH=src python3 -m applypilot --workspace . sync-legacy
PYTHONPATH=src python3 -m applypilot --workspace . dashboard
PYTHONPATH=src python3 -m applypilot --workspace . daily --mode apply
```

Replica modes:

- `daily --mode linkedin`: run LinkedIn Easy Apply
- `daily --mode naukri`: run Naukri Apply
- `daily --mode leads`: run Lead Hunter
- `daily --mode apply`: run LinkedIn + Naukri
- `daily --mode all`: run LinkedIn + Naukri + Lead Hunter

By default `daily` runs native ApplyPilot modules copied from the working agent:

- `applypilot.working_agent.auto_apply_chrome`
- `applypilot.working_agent.auto_apply_naukri`
- `applypilot.working_agent.lead_hunter`

Use `--use-legacy` only when you intentionally want to run the old sibling folder:

`/Users/rishal/Desktop/bed_rock/linkedin-agent`

## SaaS Dashboard

The dashboard is a static web control plane fed by local ApplyPilot data. It shows applied totals, policy gates, source performance, AI provider mix, review queue, and recent run audit history.

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
PYTHONPATH=src python3 -m applypilot --workspace . dashboard
cd apps/web
python3 -m http.server 4173
```

## SaaS MVP Flow

ApplyPilot now has a real SaaS spine for the protected product model:

```text
SaaS account/license -> desktop activation -> local agent run -> dashboard sync -> SaaS dashboard
```

Run the API and hosted dashboard:

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
pip install -e '.[server]'
PYTHONPATH=src python3 -m applypilot --workspace . serve --host 127.0.0.1 --port 8787
```

Create a customer/license in the dev database:

```bash
PYTHONPATH=src python3 -m applypilot --workspace . saas-create-customer \
  --email user@example.com \
  --name "Test User" \
  --plan pro_byok \
  --ai-mode byok_local \
  --seats 1
```

Activate the desktop and sync local data:

```bash
PYTHONPATH=src python3 -m applypilot --workspace . saas-activate \
  --endpoint http://127.0.0.1:8787 \
  --license-key ap_live_...

PYTHONPATH=src python3 -m applypilot --workspace . saas-sync
PYTHONPATH=src python3 -m applypilot --workspace . saas-me
```

Production billing can replace `saas-create-customer` with a Stripe/Razorpay webhook that creates the customer and license after payment.

The production billing flow is now implemented. Configure provider products and webhook secrets from `.env.example`, then open:

```text
http://127.0.0.1:8787/checkout.html
```

See `docs/billing.md`.

## Providers

Working now:

- `rules`: no key, local heuristic scoring
- `ollama`: local model through Ollama
- `openai`: OpenAI-compatible chat completions endpoint

Examples:

```bash
applypilot score --provider rules

OLLAMA_MODEL=llama3.1 applypilot score --provider ollama

OPENAI_API_KEY=... OPENAI_MODEL=... applypilot score --provider openai
```

Reserved for the next provider pass:

- Anthropic / Claude
- Gemini
- Hugging Face

## Commands

```bash
applypilot init
applypilot import-linkedin --source path/to/linkedin_jobs.json
applypilot score --provider rules
applypilot score --provider ollama
applypilot score --provider openai
applypilot review --min-score 50 --limit 25
applypilot report --out .applypilot/reports/review.md
applypilot policy
applypilot policy --mode auto-submit --daily-limit 25 --min-score 70
applypilot run --provider rules --connector linkedin-browser --interval-minutes 60
applypilot daily --mode all
applypilot sync-legacy
applypilot status
applypilot dashboard
applypilot serve
applypilot saas-create-customer --email user@example.com
applypilot saas-activate --license-key ap_live_...
applypilot saas-sync
applypilot saas-me
```

## Desktop App

Run the local desktop control center:

```bash
pip install -e '.[desktop]'
applypilot-desktop
```

The desktop opens the functional chat application at `http://127.0.0.1:8765`.
Use this URL instead of opening `apps/web/index.html` with `file://`.

The chat can:

- build and persist the candidate profile into `.applypilot/profile.md`
- update scoring preferences and application form answers in `.applypilot/config.json`
- generate a truthful local resume draft
- search LinkedIn through the user's existing logged-in Chrome session
- derive LinkedIn, Naukri, and lead searches only from the saved target roles and location
- reject off-profile search results before they enter the queue or application flow
- score jobs, explain matches, and show live agent status
- enable auto-submit and start an application run through separate confirmations

Build compiled macOS/Windows artifacts:

```bash
pip install -e '.[desktop,package]'
python3 packaging/build_desktop.py --clean
```

## Deploy SaaS

Run the production-shaped container locally:

```bash
cp .env.example .env
docker compose up --build
```

The SQLite SaaS database is persisted in the `applypilot-data` Docker volume. For public deployment, configure HTTPS, provider secrets, allowed origins, and webhook URLs.

GitHub Actions are included for tests and native macOS/Windows desktop builds.

## Automation Modes

ApplyPilot supports three product modes:

- `review-only`: score and prepare jobs, no form filling
- `fill-only`: fill applications locally, stop before the final submit button
- `auto-submit`: fill and click the final application submit button when policy rules pass

Auto-submit means application submission. It is a real product requirement, but it must be explicit because it changes the user's external accounts.

## Unattended Desktop Agent

The user can run ApplyPilot on their own desktop while away:

```bash
pip install -e '.[desktop]'
applypilot policy --mode auto-submit --daily-limit 25 --min-score 70
applypilot run --provider rules --connector linkedin-browser --interval-minutes 60
```

On macOS, ApplyPilot uses the user's existing logged-in Google Chrome profile. It does not open a separate Chromium profile for submission.

## Product Surfaces

- `src/applypilot`: local core package
- `src/applypilot/server.py`: SaaS API server
- `src/applypilot/saas_store.py`: customers, licenses, devices, sync store
- `src/applypilot/saas_client.py`: desktop activation and sync client
- `docs/architecture.md`: SaaS + local agent architecture
- `docs/product-strategy.md`: launch and monetization plan
- `docs/mcp-and-openai-app.md`: MCP, Claude Code, Codex, and ChatGPT Apps strategy
- `docs/security.md`: trust, secrets, and review-before-submit rules
- `apps/desktop`: desktop packaging plan
- `apps/web`: static SaaS dashboard and command center

## Hard Rule

Application submission must be explicit, limited, logged, and controlled by local policy.
