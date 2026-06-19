# Migration From The Working Agent

Source repo:

`/Users/rishal/Desktop/bed_rock/linkedin-agent`

New product repo:

`/Users/rishal/Desktop/bed_rock/applypilot`

## What To Keep

- job search query ideas
- Claude scoring prompt concepts
- form-answering concepts
- feed lead scanning concept
- daily report concept
- application tracker concept
- local browser execution model

## What Not To Copy Directly

- hardcoded credentials
- personal profile constants
- direct LinkedIn cookie handling in shared product code
- AppleScript-only automation as the cross-platform base
- unlimited auto-submit defaults with no policy checks
- repo-local logs and output files with private data

## Extraction Plan

1. Move profile/resume data into workspace config.
2. Move provider keys into environment variables or OS keychain.
3. Keep job scoring in provider modules.
4. Keep job queue and application history in storage modules.
5. Wrap browser automation behind a connector/action interface.
6. Add review-before-submit as the default.
7. Add desktop UI after CLI behavior is stable.
8. Add MCP server after core functions are stable.
9. Add SaaS license/sync after local product is useful.

## First Code To Migrate

Start with read-only or low-risk logic:

- job normalization
- scoring
- report generation
- answer drafting
- outreach drafting

Migrate later:

- browser automation
- resume upload
- final application submit

## Product Safety Defaults

- default provider: `rules`
- default action: review queue, fill-only, or auto-submit depending on user policy
- default submit behavior: controlled by `AutomationPolicy`
- default storage: local
- default SaaS data: metadata only

## Auto-Submit Migration

The old working agent already contains submit behavior. When migrating it:

1. move the final submit click behind `AutomationPolicy.can_auto_submit`
2. stop before submit when mode is `fill-only`
3. refuse submit below `min_score_to_submit`
4. stop after `max_applications_per_day`
5. write every submit result to application history
