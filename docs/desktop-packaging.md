# Desktop Packaging

## Implemented Desktop Strategy

ApplyPilot uses a localhost-only web control center around the local Python core:

```text
ApplyPilot desktop executable
  -> starts local control API on 127.0.0.1
  -> opens the desktop control center
  -> launches compiled applypilot-agent sidecar
  -> streams logs and allows stop/sync
```

Nuitka compiles the desktop launcher and agent sidecar. This makes casual inspection harder, but no client-side software can be guaranteed impossible to reverse engineer. Premium prompts, billing, managed model routing, and license state remain server-side.

## Windows

Package as:

- compiled `ApplyPilot.exe`
- compiled `applypilot-agent.exe`
- background local service option
- local encrypted config
- browser automation through Playwright/Chrome

## macOS

Package as:

- compiled and signed/notarized `.app` and `.dmg`
- compiled `applypilot-agent` sidecar inside the app bundle
- local app bundle
- avoid AppleScript dependency long term
- prefer the user's existing logged-in Chrome profile on macOS

## Local Data

Store locally:

- profile
- preferences
- provider keys
- queues
- run logs
- browser session/cookies

## Away Mode

Desktop app should expose an "Away Mode" toggle:

- runs local agent on an interval
- scores jobs automatically
- applies/submits when `auto-submit` policy passes
- shows today's count and last run result
- keeps a pause/stop button visible
- resumes after reboot if the user enables background launch

The current desktop control center exposes start, stop, workflow mode, policy state, activity logs, and explicit auto-submit confirmation.

Use OS keychain where available for secrets.

## UX Principles

The first screen should be the actual work surface:

- today's queue
- top matches
- actions waiting for approval
- run status
- provider status

Avoid a marketing-style landing page inside the app.

## Submission UX

In `fill-only` mode, before submitting an application, show:

- job title/company
- score and reason
- filled answers
- resume selected
- final submit button

In `auto-submit` mode, the app may submit automatically after the local policy check passes. The UI still needs a visible run state, daily cap, pause/stop button, and durable log.
