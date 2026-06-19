# Architecture

## High-Level Shape

```text
SaaS Dashboard
  account, billing, sync, analytics, premium prompts
        |
        | license + optional encrypted sync
        v
Local Agent
  queues, scoring, unattended run loop, browser connector, provider keys, resume
        |
        +-- CLI
        +-- Desktop app
        +-- MCP server
        +-- ChatGPT/Codex app connector
```

## Why This Split

The risky and private pieces stay local:

- LinkedIn/browser cookies
- resumes
- provider API keys
- local Ollama/Hugging Face models
- actual browser automation

The SaaS handles durable product value:

- subscription and licensing
- multi-device sync if the user opts in
- analytics
- premium prompts and scoring policies
- team dashboards
- hosted model credits for non-BYOK users

## Core Package

`src/applypilot` is the shared local core:

- `models.py`: Job, Preferences, Evaluation
- `storage.py`: local queue and evaluation persistence
- `agent.py`: unattended local run loop
- `connectors/`: source-specific importers
- `providers/`: scoring/LLM provider boundary
- `cli.py`: command surface
- `mcp/`: future MCP wrapper around stable core functions

## Provider Layer

The product must support:

- rules provider for free/local scoring
- Ollama local models
- OpenAI-compatible BYOK
- Anthropic BYOK
- Gemini BYOK
- Hugging Face local/API models
- managed SaaS provider for paid users

Every provider should return the same structured `Evaluation` object. Provider-specific behavior must not leak into browser automation or UI code.

## Connector Layer

Connectors normalize external sources into `Job` objects.

Initial connectors:

- `legacy_linkedin`: imports JSON from the current working agent

Future connectors:

- local browser LinkedIn connector
- CSV upload
- manual paste
- Greenhouse/Lever job pages
- Gmail job alerts

## Automation Boundary

Automation should be a connector/action layer, not the core.

Core can say:

- shortlisted
- review
- reject
- draft answer
- prepare application

Automation can do:

- open browser
- fill form
- stop at review screen
- submit the application when `auto-submit` policy is enabled

## Data Flow

```text
Import jobs -> normalize -> queue -> score -> draft -> policy check -> local fill/apply/submit -> log outcome
```

## Unattended Desktop Mode

The unattended agent runs on the user's own desktop:

```text
timer/service -> applypilot run -> score queue -> policy gate -> local browser connector -> application history
```

This is the core paid workflow. SaaS can configure and monitor it, but the actual browser session remains local.

## Product Rule

The system should never need a user's LinkedIn password on the SaaS server.
