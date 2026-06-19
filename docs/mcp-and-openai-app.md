# MCP, Claude Code, Codex, And ChatGPT Apps

## One Core, Many Surfaces

The MCP server should wrap the same local core used by the CLI and desktop app. Do not create separate logic for each host.

## MCP Tools

Initial tools:

- `import_jobs`
- `score_jobs`
- `review_queue`
- `draft_application_answer`
- `export_report`

Later guarded tools:

- `open_job_in_browser`
- `fill_application`
- `submit_application`

Guarded tools should be marked as write/open-world actions and require approval.

## Claude Code And Codex

Developer users can install the MCP server locally and ask:

- "Score the jobs I imported today"
- "Show me the top five roles and why"
- "Draft answers for this application"
- "Create a daily job hunt report"

## ChatGPT App

The ChatGPT App should not start with "auto-apply." It should start with safe, review-first value:

- resume/job match review
- job fit scoring
- answer drafting
- outreach drafting
- connect local agent

Paid conversion:

1. user finds app in ChatGPT
2. app gives useful free analysis
3. app offers desktop/local agent for automation and tracking
4. user pays on our website
5. local agent unlocks with license

## OpenAI/Codex Plugin Distribution

When public distribution is available, package:

- MCP server manifest
- skill docs
- app metadata
- privacy and terms links
- screenshots

The app/plugin is a distribution channel. The subscription is the business.

