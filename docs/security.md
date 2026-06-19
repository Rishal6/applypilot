# Security And Trust

## Product Promise

ApplyPilot should be safer than hosted auto-apply tools because sensitive job-search automation runs locally.

## Never Store In Repo

- API keys
- AWS keys
- LinkedIn cookies
- resumes with personal data
- local logs containing session details
- provider request/response dumps with private profile info

## Immediate Migration From Current Agent

The working source repo has hardcoded AWS credentials. Before using it as product code:

1. rotate the exposed AWS key
2. delete hardcoded credentials
3. read credentials from environment variables or local encrypted settings
4. add secret scanning before any public repo or packaged build

## Review-First Safety Model

Default behavior:

- scan/import jobs
- score jobs
- draft answers
- show review queue
- export report

Explicit opt-in behavior:

- fill application form
- upload resume
- submit application

Submission must require:

- a daily limit
- visible status
- durable logs
- per-job decision record
- an easy kill switch

## Automation Modes

- `review-only`: no form filling or submission
- `fill-only`: fills the form but stops before the final submit button
- `auto-submit`: clicks the final application submit button when score, daily limit, and connector rules pass

Auto-submit is supported, but it should be enabled intentionally per workspace/user.

## SaaS Data Policy

Default SaaS sync should avoid raw browser session data.

Allowed with user consent:

- profile summary
- preferences
- normalized job metadata
- evaluation result
- application status

Avoid sending unless required:

- full resume file
- LinkedIn cookies
- raw page HTML
- private messages
- provider API keys

## Packaging Reality

Executables can be made harder to inspect, but not impossible to reverse engineer. Protect product value by keeping:

- license checks server-side
- premium prompt libraries server-side
- managed model routing server-side
- billing and analytics server-side

Do not rely on obfuscation as the only moat.
