# Product Strategy

## Product Thesis

Job seekers do not need another spray-and-pray auto-apply bot. They need a private agent that turns job hunting into a daily operating system:

1. find relevant jobs
2. score fit
3. draft answers and outreach
4. prepare applications
5. track outcomes
6. improve personal brand
7. auto-submit applications when the user explicitly enables that mode

ApplyPilot should win on trust, control, and quality.

## Target Users

Primary early users:

- AI/tech job seekers applying to 20-100 roles per month
- developers comfortable with local tools, Claude Code, Codex, Cursor, or MCP
- international applicants who want BYOK or local model support to reduce AI cost

Later users:

- non-technical job seekers using a desktop app
- bootcamp/career-coach cohorts
- small recruiting/career-services teams

## Positioning

Short version:

> ApplyPilot is a local-first AI job search copilot that scores jobs, prepares applications, drafts outreach, and runs browser automation safely on your machine.

Avoid positioning:

- "Apply to 500 jobs automatically"
- "Beat LinkedIn"
- "Undetectable bot"

Those create trust, policy, and platform risk.

## Monetization

Recommended pricing:

- Free: local CLI, rules scoring, manual import/export
- Pro BYOK: $15-20/month, desktop app, MCP, queues, templates, local providers
- Pro Managed AI: $30-50/month, hosted model routing and premium scoring prompts
- Team/Cohort: $99+/month, shared dashboards for career coaches

Billing should happen on our website via Stripe. ChatGPT Apps and Codex plugins are distribution channels, not the primary billing system.

## Launch Path

Phase 0: Local useful core

- normalize jobs
- score jobs
- generate review queue
- create reports
- define auto-submit policy before migrating browser automation

Phase 1: Developer distribution

- CLI installer
- MCP server for Claude Code and Codex
- ChatGPT App that sends users to SaaS for paid sync/desktop

Phase 2: Desktop app

- Windows installer
- macOS signed app
- local browser automation connector
- away mode for unattended scoring and auto-submit
- local encrypted settings

Phase 3: SaaS dashboard

- account and subscription
- profile/preferences sync
- run history
- application analytics
- license enforcement
- premium prompt/model routing

## MVP Success Criteria

The MVP is useful if a user can:

- import jobs from an existing source
- see the top 20 roles ranked correctly
- understand why each role is recommended
- export an action plan
- keep secrets and sessions local

The MVP is not required to:

- support all job boards
- have a hosted dashboard
- support every model provider on day one

The paid product does require auto-submit as a supported mode. It should be implemented behind explicit policy, daily limits, and logging instead of being hidden inside browser scripts.
